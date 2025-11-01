from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.db.base import get_session
from app.db.models import Quiz, QuizVersion, Question, QuestionPart, Option, OptionPart, User, QuestionVersion
from .schemas import QuizCreate, QuizResponse
from app.core.security import require_role

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("", response_model=QuizResponse, status_code=201)
async def create_quiz(payload: QuizCreate, current_user = Depends(require_role("author")), db: AsyncSession = Depends(get_session)):
    quiz = Quiz(
        title=payload.title,
        description=payload.description,
        meta_data=payload.meta_data,
        created_by=payload.created_by,
        status=payload.status,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)
    return quiz


@router.get("", response_model=List[QuizResponse])
async def list_quizzes(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Quiz).order_by(Quiz.created_at.desc()))
    return result.scalars().all()


@router.get("/published", response_model=List[QuizResponse])
async def list_published_quizzes(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Quiz).where(Quiz.status == "published").order_by(Quiz.published_at.desc()))
    return result.scalars().all()


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(quiz_id: UUID, db: AsyncSession = Depends(get_session)):
    q = await db.get(Quiz, quiz_id)
    if not q:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return q


@router.post("/{quiz_id}/questions", status_code=201)
async def add_question_to_quiz(quiz_id: UUID, question_id: UUID, index: Optional[int] = None, current_user = Depends(require_role("author")), db: AsyncSession = Depends(get_session)):
    from app.db.models import QuizQuestion, Question

    quiz = await db.get(Quiz, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Check duplicate
    existing = await db.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.question_id == question_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Question already in quiz")

    qlink = QuizQuestion(quiz_id=quiz_id, question_id=question_id, index=index, meta_data={})
    db.add(qlink)
    await db.commit()
    await db.refresh(qlink)
    return {"id": str(qlink.id), "quiz_id": str(quiz_id), "question_id": str(question_id)}


@router.get("/{quiz_id}/questions")
async def list_quiz_questions(quiz_id: UUID, db: AsyncSession = Depends(get_session)):
    from app.db.models import QuizQuestion, Question

    quiz = await db.get(Quiz, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    qlinks = (await db.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.index))).scalars().all()
    questions = []
    for ql in qlinks:
        q = await db.get(Question, ql.question_id)
        if q:
            questions.append(q)
    return questions


@router.delete("/{quiz_id}/questions/{question_id}", status_code=204)
async def remove_question_from_quiz(quiz_id: UUID, question_id: UUID, current_user = Depends(require_role("author")), db: AsyncSession = Depends(get_session)):
    from app.db.models import QuizQuestion

    stmt = select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id, QuizQuestion.question_id == question_id)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found in quiz")
    await db.delete(existing)
    await db.commit()
    return None


@router.post("/{quiz_id}/publish")
async def publish_quiz(quiz_id: UUID, question_ids: Optional[List[UUID]] = None, created_by: Optional[UUID] = None, current_user = Depends(require_role("author")), db: AsyncSession = Depends(get_session)):
    """Create a QuizVersion snapshot. Provide question_ids explicitly since quizzes don't currently link questions."""
    quiz = await db.get(Quiz, quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # Fetch questions: if question_ids provided use that, otherwise use quiz membership
    questions = []
    if question_ids:
        qstmt = select(Question).where(Question.id.in_(question_ids)).options(
            selectinload(Question.parts).selectinload(QuestionPart.media),
            selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
        )
        res = await db.execute(qstmt)
        questions = res.scalars().all()
    else:
        # Use quiz_questions association
        from app.db.models import QuizQuestion
        qlinks = (await db.execute(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id))).scalars().all()
        qids = [ql.question_id for ql in qlinks]
        if qids:
            qstmt = select(Question).where(Question.id.in_(qids)).options(
                selectinload(Question.parts).selectinload(QuestionPart.media),
                selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
            )
            res = await db.execute(qstmt)
            questions = res.scalars().all()

    # Build snapshot
    snapshot = {
        "quiz": {
            "id": str(quiz.id),
            "title": quiz.title,
            "description": quiz.description,
            "meta_data": quiz.meta_data,
        },
        "questions": [],
    }

    for q in questions:
        q_s = {
            "id": str(q.id),
            "title": q.title,
            "description": q.description,
            "answer_type": q.answer_type,
            "scoring": q.scoring,
            "parts": [],
            "options": [],
            "question_version_id": None,
        }
        for p in q.parts:
            q_s["parts"].append({"index": p.index, "part_type": p.part_type, "content": p.content, "media_id": str(p.media_id) if p.media_id else None})
        for o in q.options:
            q_s["options"].append({"id": str(o.id), "label": o.label, "index": o.index, "is_correct": bool(o.is_correct), "weight": float(o.weight)})
        snapshot["questions"].append(q_s)

        # Create a QuestionVersion snapshot for this question
        # Determine next version number
        existing_qv = await db.execute(select(func.count()).select_from(QuestionVersion).where(QuestionVersion.question_id == q.id))
        qcount = existing_qv.scalar() or 0
        q_version_number = int(qcount) + 1
        q_snapshot = {"id": str(q.id), "title": q.title, "description": q.description, "answer_type": q.answer_type, "scoring": q.scoring, "parts": q_s.get("parts"), "options": q_s.get("options")}
        qver = QuestionVersion(question_id=q.id, version_number=q_version_number, snapshot=q_snapshot, created_by=created_by)
        db.add(qver)
        await db.flush()
        # attach id back into the quiz snapshot
        snapshot["questions"][-1]["question_version_id"] = str(qver.id)

    # Determine version number
    existing = await db.execute(select(func.count()).select_from(QuizVersion).where(QuizVersion.quiz_id == quiz.id))
    count = existing.scalar() or 0
    version_number = int(count) + 1

    qv = QuizVersion(quiz_id=quiz.id, version_number=version_number, snapshot=snapshot, created_by=created_by)
    db.add(qv)
    quiz.published_at = qv.created_at
    quiz.status = "published"
    await db.commit()
    await db.refresh(qv)

    return {"quiz_version_id": str(qv.id), "version_number": version_number}


@router.get("/{quiz_id}/versions")
async def list_quiz_versions(quiz_id: UUID, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(QuizVersion).where(QuizVersion.quiz_id == quiz_id).order_by(QuizVersion.version_number.desc()))
    return result.scalars().all()
