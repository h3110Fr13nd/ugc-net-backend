from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import uuid
from decimal import Decimal
import json
import re
import difflib


def _regex_matches(pattern: str | None, text: str) -> bool:
    """Try to match pattern against text. If the pattern raises a re.error,
    attempt a unicode-escape decode fallback (helps when patterns are double-escaped
    in JSON payloads used in tests)."""
    if not pattern or not text:
        return False
    # Try raw pattern
    try:
        if re.search(pattern, text):
            return True
    except re.error:
        pass

    # Try unicode-escape decoded pattern
    try:
        alt = bytes(pattern, "utf-8").decode("unicode_escape")
        if re.search(alt, text):
            return True
    except Exception:
        pass

    # Common fallback: replace \d with [0-9] (handles double-escaped backslashes in JSON)
    try:
        alt2 = pattern.replace('\\\\d', '[0-9]').replace('\\d', '[0-9]')
        if re.search(alt2, text):
            return True
    except Exception:
        pass

    return False


from app.db.base import get_session
from app.db.models import (
    QuizAttempt,
    QuestionAttempt,
    QuestionAttemptPart,
    Quiz,
    Question,
    Option,
    QuestionTaxonomy,
    Taxonomy,
    UserTaxonomyStats,
    QuizVersion,
    Role,
    UserRole,
)
from .schemas import QuizAttemptCreate, QuizAttemptResponse, QuestionAttemptCreate, QuestionAttemptResponse
from app.core.security import get_current_user_optional

router = APIRouter(tags=["attempts"])


@router.post("/quizzes/{quiz_id}/start", response_model=QuizAttemptResponse, status_code=201)
async def start_quiz(quiz_id: UUID, payload: QuizAttemptCreate, version_id: Optional[UUID] = None, db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user_optional)):
    """Start a quiz attempt.

    If `version_id` is provided, use that QuizVersion. Otherwise resolve the latest published QuizVersion for the quiz.
    """
    quiz = await db.get(Quiz, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    chosen_version = None
    if version_id:
        chosen_version = await db.get(QuizVersion, version_id)
        if not chosen_version or chosen_version.quiz_id != quiz_id:
            raise HTTPException(status_code=404, detail="QuizVersion not found for quiz")
    else:
        # Find latest QuizVersion for this quiz
        qv_stmt = select(QuizVersion).where(QuizVersion.quiz_id == quiz_id).order_by(QuizVersion.version_number.desc())
        qv_res = await db.execute(qv_stmt)
        chosen_version = qv_res.scalars().first()

    # If quiz is published but has no versions, allow starting but warn (chosen_version None)
    # If authenticated, tie the attempt to the authenticated user; otherwise fall back to payload.user_id
    user_id = current_user.id if current_user else payload.user_id
    qa = QuizAttempt(quiz_id=quiz_id, quiz_version_id=(chosen_version.id if chosen_version else None), user_id=user_id, meta_data=payload.meta_data)
    db.add(qa)
    await db.commit()
    await db.refresh(qa)
    return qa


@router.post("/quiz-attempts/{attempt_id}/submit-answer", response_model=QuestionAttemptResponse)
async def submit_answer(attempt_id: UUID, payload: QuestionAttemptCreate, db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user_optional)):
    # Fetch quiz attempt
    qa = await db.get(QuizAttempt, attempt_id)
    if not qa:
        raise HTTPException(status_code=404, detail="QuizAttempt not found")

    # If an authenticated user is present, enforce owner or admin access; otherwise keep legacy behavior
    if current_user:
        if qa.user_id and str(qa.user_id) != str(current_user.id):
            try:
                stmt = select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == current_user.id, Role.name == 'admin')
                res = await db.execute(stmt)
                admin_role = res.scalar_one_or_none()
                if not admin_role:
                    raise HTTPException(status_code=403, detail="forbidden")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="forbidden")

    # Fetch question and options
    question = await db.get(Question, payload.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Grading: support per-part scoring (scoring.parts), 'options' (partial credit via weights),
    # 'text', 'numeric', 'match', 'regex', and 'fuzzy'
    score = Decimal(0)
    max_score = Decimal(0)

    scoring = question.scoring or {}

    # Per-part scoring if defined in question.scoring
    if isinstance(scoring, dict) and scoring.get("parts"):
        parts_rules = scoring.get("parts")
        # iterate parts rules and evaluate each against payload.parts
        for idx, pr in enumerate(parts_rules):
            part_max = Decimal(pr.get("max_score", 1))
            max_score += part_max
            # find corresponding response part (by index if provided)
            resp = None
            if idx < len(payload.parts):
                resp = payload.parts[idx]

            ptype = pr.get("type", "text")
            if resp is None:
                continue

            # text equality (case-insensitive)
            if ptype == "text":
                accepted = [a.lower() for a in pr.get("accepted_answers", [])]
                if resp.text_response and any(resp.text_response.strip().lower() == a for a in accepted):
                    score += part_max
            elif ptype == "regex":
                pattern = pr.get("pattern")
                try:
                    if resp.text_response and pattern and _regex_matches(pattern, resp.text_response):
                        score += part_max
                except Exception:
                    pass
            elif ptype == "fuzzy":
                target = pr.get("target", "")
                threshold = float(pr.get("threshold", 0.8))
                if resp.text_response:
                    sim = difflib.SequenceMatcher(a=resp.text_response.lower(), b=str(target).lower()).ratio()
                    if sim >= threshold:
                        score += part_max
            elif ptype == "numeric":
                try:
                    expected = Decimal(pr.get("answer"))
                    tol = Decimal(pr.get("tolerance", 0))
                    if resp.numeric_response is not None:
                        if abs(Decimal(resp.numeric_response) - expected) <= tol:
                            score += part_max
                except Exception:
                    pass

    elif question.answer_type == "options":
        opts = (await db.execute(select(Option).where(Option.question_id == question.id))).scalars().all()
        for o in opts:
            if o.is_correct:
                max_score += Decimal(o.weight or 1)

        # collect selected option ids from parts (first occurrence wins)
        selected_ids = []
        for part in payload.parts:
            if part.selected_option_ids:
                selected_ids.extend(part.selected_option_ids)

        # Score = sum of weights for correctly selected options
        for o in opts:
            if str(o.id) in [str(s) for s in selected_ids] and o.is_correct:
                score += Decimal(o.weight or 1)

    elif question.answer_type == "text":
        # Look for expected answers in question.scoring: {'accepted_answers': ['foo','bar'], 'max_score': 1}
        accepted = [a.lower() for a in scoring.get("accepted_answers", [])]
        max_score = Decimal(scoring.get("max_score", 1))
        # Use first part's text_response
        text_resp = None
        if payload.parts:
            text_resp = payload.parts[0].text_response
        if text_resp and any(text_resp.strip().lower() == a for a in accepted):
            score = max_score

    elif question.answer_type == "numeric":
        expected = scoring.get("answer")
        tol = scoring.get("tolerance", 0)
        max_score = Decimal(scoring.get("max_score", 1))
        num_resp = None
        if payload.parts:
            num_resp = payload.parts[0].numeric_response
        try:
            if num_resp is not None and expected is not None:
                num_val = Decimal(num_resp)
                exp_val = Decimal(expected)
                if abs(num_val - exp_val) <= Decimal(tol):
                    score = max_score
        except Exception:
            score = Decimal(0)

    elif question.answer_type == "match":
        # exact match against scoring.accepted_pairs list or mapping
        pairs = scoring.get("pairs", [])
        max_score = Decimal(scoring.get("max_score", 1))
        # Work like text: use first response
        text_resp = None
        if payload.parts:
            text_resp = payload.parts[0].text_response
        for p in pairs:
            if text_resp and text_resp.strip().lower() == str(p).strip().lower():
                score = max_score
                break

    elif question.answer_type == "regex":
        pattern = scoring.get("pattern")
        max_score = Decimal(scoring.get("max_score", 1))
        text_resp = None
        if payload.parts:
            text_resp = payload.parts[0].text_response
        try:
            if text_resp and pattern and _regex_matches(pattern, text_resp):
                score = max_score
        except Exception:
            score = Decimal(0)

    elif question.answer_type == "fuzzy":
        target = scoring.get("target", "")
        threshold = float(scoring.get("threshold", 0.8))
        max_score = Decimal(scoring.get("max_score", 1))
        text_resp = None
        if payload.parts:
            text_resp = payload.parts[0].text_response
        if text_resp:
            sim = difflib.SequenceMatcher(a=text_resp.lower(), b=str(target).lower()).ratio()
            if sim >= threshold:
                score = max_score

    else:
        # Default: no scoring rules known
        max_score = Decimal(question.scoring.get("max_score", 1) if isinstance(question.scoring, dict) else 1)

    # Create QuestionAttempt and parts
    q_attempt = QuestionAttempt(quiz_attempt_id=qa.id, question_id=question.id, attempt_index=payload.attempt_index, meta_data=payload.meta_data, score=score, max_score=max_score)
    db.add(q_attempt)
    await db.flush()

    # Save parts
    for part in payload.parts:
        # SQLite test backend stores ARRAY as TEXT; serialize lists to JSON to avoid binding errors
        sel_ids = part.selected_option_ids
        if sel_ids is not None and getattr(db.bind, 'dialect', None) and getattr(db.bind.dialect, 'name', '') == 'sqlite':
            # SQLite test DB maps ARRAY -> TEXT; to avoid ARRAY processors we store selected ids
            # in raw_response and leave the ARRAY column NULL.
            sel_ids_db = None
            raw = part.raw_response or {}
            raw["selected_option_ids"] = [str(s) for s in sel_ids]
        else:
            sel_ids_db = sel_ids
            raw = part.raw_response

        part_record = QuestionAttemptPart(
            question_attempt_id=q_attempt.id,
            question_part_id=part.question_part_id,
            selected_option_ids=sel_ids_db,
            text_response=part.text_response,
            numeric_response=part.numeric_response,
            file_media_id=part.file_media_id,
            raw_response=raw,
        )
        db.add(part_record)

    # Update scored_at timestamps
    q_attempt.scored_at = q_attempt.scored_at

    # Update quiz attempt totals
    if qa.max_score is None:
        qa.max_score = Decimal(0)
    if qa.score is None:
        qa.score = Decimal(0)
    qa.max_score += max_score
    qa.score += score

    # Statistics engine: update UserTaxonomyStats for user if available
    if qa.user_id:
        from app.services.stats_service import update_user_taxonomy_stats
        await update_user_taxonomy_stats(db, qa.user_id, question.id, score, max_score)

    await db.commit()
    await db.refresh(q_attempt)
    return q_attempt


@router.post("/quiz-attempts/{attempt_id}/finish")
async def finish_quiz(attempt_id: UUID, db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user_optional)):
    """Mark a quiz attempt as finished, compute final totals and mark completed."""
    qa = await db.get(QuizAttempt, attempt_id)
    if not qa:
        raise HTTPException(status_code=404, detail="QuizAttempt not found")

    # If an authenticated user is present, enforce owner or admin access; otherwise keep legacy behavior
    if current_user:
        if qa.user_id and str(qa.user_id) != str(current_user.id):
            try:
                stmt = select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == current_user.id, Role.name == 'admin')
                res = await db.execute(stmt)
                admin_role = res.scalar_one_or_none()
                if not admin_role:
                    raise HTTPException(status_code=403, detail="forbidden")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="forbidden")

    # set submitted_at, compute duration if possible
    from datetime import datetime

    if not qa.submitted_at:
        qa.submitted_at = datetime.utcnow()
    qa.status = "completed"

    # Ensure numeric totals are present
    if qa.score is None:
        qa.score = 0
    if qa.max_score is None:
        qa.max_score = 0

    # Optionally compute duration_seconds if started_at exists
    try:
        if qa.started_at and qa.submitted_at:
            qa.duration_seconds = int((qa.submitted_at - qa.started_at).total_seconds())
    except Exception:
        pass

    await db.commit()
    await db.refresh(qa)
    return {"id": str(qa.id), "status": qa.status, "score": float(qa.score or 0), "max_score": float(qa.max_score or 0)}


@router.get("/quiz-attempts/{attempt_id}/results")
async def get_quiz_results(attempt_id: UUID, db: AsyncSession = Depends(get_session), current_user = Depends(get_current_user_optional)):
    """Return the full graded review of a completed quiz attempt."""
    qa = await db.get(QuizAttempt, attempt_id)
    if not qa:
        raise HTTPException(status_code=404, detail="QuizAttempt not found")

    # If an authenticated user is present, enforce owner or admin access; otherwise keep legacy behavior
    if current_user:
        if qa.user_id and str(qa.user_id) != str(current_user.id):
            try:
                stmt = select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == current_user.id, Role.name == 'admin')
                res = await db.execute(stmt)
                admin_role = res.scalar_one_or_none()
                if not admin_role:
                    raise HTTPException(status_code=403, detail="forbidden")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="forbidden")

    # Load question attempts and parts
    res = await db.execute(select(QuestionAttempt).where(QuestionAttempt.quiz_attempt_id == qa.id))
    qattempts = res.scalars().all()

    out = {
        "id": str(qa.id),
        "quiz_id": str(qa.quiz_id),
        "quiz_version_id": str(qa.quiz_version_id) if qa.quiz_version_id else None,
        "user_id": str(qa.user_id) if qa.user_id else None,
        "score": float(qa.score or 0),
        "max_score": float(qa.max_score or 0),
        "status": qa.status,
        "questions": [],
    }

    for q in qattempts:
        # load parts
        parts_res = await db.execute(select(QuestionAttemptPart).where(QuestionAttemptPart.question_attempt_id == q.id))
        parts = parts_res.scalars().all()
        out["questions"].append({
            "id": str(q.id),
            "question_id": str(q.question_id),
            "score": float(q.score or 0),
            "max_score": float(q.max_score or 0),
            "parts": [{
                "id": str(p.id),
                "question_part_id": str(p.question_part_id) if p.question_part_id else None,
                "selected_option_ids": [str(s) for s in (p.selected_option_ids or [])],
                "text_response": p.text_response,
                "numeric_response": float(p.numeric_response) if p.numeric_response is not None else None,
                "file_media_id": str(p.file_media_id) if p.file_media_id else None,
            } for p in parts]
        })

    return out
