"""
Service for creating and managing quiz and question attempts.
"""
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    QuizAttempt,
    QuestionAttempt,
    QuestionAttemptPart,
    UserTaxonomyStats,
    Taxonomy,
)
from app.services.stats_service import update_user_taxonomy_stats


def now():
    """Get current UTC timestamp."""
    return datetime.now(tz=timezone.utc)


async def create_or_get_quiz_attempt(
    db: AsyncSession,
    user_id: UUID,
    quiz_id: UUID | None = None,
    quiz_version_id: UUID | None = None,
) -> QuizAttempt:
    """
    Create a new QuizAttempt.
    
    Supports both:
    - Quiz-based attempts: quiz_id is provided (user takes a specific quiz)
    - Standalone attempts: quiz_id is None (user answers random questions)
    """
    attempt = QuizAttempt(
        quiz_id=quiz_id,
        user_id=user_id,
        quiz_version_id=quiz_version_id,
        started_at=now(),
        status="in_progress",
        meta_data={},
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def save_question_attempt(
    db: AsyncSession,
    quiz_attempt_id: UUID,
    question_id: UUID,
    user_answer_parts: list[dict],
    score: float | None = None,
    max_score: float = 1.0,
    grading_details: dict | None = None,
    attempt_index: int = 1,
    duration_seconds: int | None = None,
    status: str = "attempted",
) -> QuestionAttempt:
    """
    Save a question attempt and its parts to the database.
    
    Args:
        db: Database session
        quiz_attempt_id: ID of the parent QuizAttempt
        question_id: ID of the question being answered
        user_answer_parts: List of dicts with keys like 'selected_option_ids', 'text_response', etc.
        score: Score awarded (0-1 or 0-max_score)
        max_score: Maximum possible score for this question
        grading_details: Dict with grading metadata (e.g., LLM explanation)
        attempt_index: Which attempt this is for this question
    
    Returns:
        QuestionAttempt object
    """
    question_attempt = QuestionAttempt(
        quiz_attempt_id=quiz_attempt_id,
        question_id=question_id,
        attempt_index=attempt_index,
        started_at=now(),
        submitted_at=now(),
        score=Decimal(str(score)) if score is not None else None,
        max_score=Decimal(str(max_score)),
        grading=grading_details or {},
        duration_seconds=duration_seconds,
        status=status,
        meta_data={},
    )
    db.add(question_attempt)
    await db.flush()
    
    # Save parts (user's answers)
    for part_idx, part_data in enumerate(user_answer_parts):
        part = QuestionAttemptPart(
            question_attempt_id=question_attempt.id,
            question_part_id=part_data.get("question_part_id"),
            selected_option_ids=part_data.get("selected_option_ids"),
            text_response=part_data.get("text_response"),
            numeric_response=part_data.get("numeric_response"),
            file_media_id=part_data.get("file_media_id"),
            raw_response=part_data.get("raw_response"),
        )
        db.add(part)
    
    await db.flush()
    return question_attempt


async def finalize_quiz_attempt(
    db: AsyncSession,
    quiz_attempt_id: UUID,
    total_score: float | None = None,
    max_score: float | None = None,
) -> QuizAttempt:
    """
    Mark a quiz attempt as completed.
    """
    stmt = select(QuizAttempt).where(QuizAttempt.id == quiz_attempt_id)
    result = await db.execute(stmt)
    attempt = result.scalar()
    
    if attempt:
        attempt.status = "completed"
        attempt.submitted_at = now()
        if total_score is not None:
            attempt.score = Decimal(str(total_score))
        if max_score is not None:
            attempt.max_score = Decimal(str(max_score))
    
    await db.flush()
    return attempt


async def update_attempt_stats(
    db: AsyncSession,
    user_id: UUID,
    question_id: UUID,
    is_correct: bool,
    score: float,
    max_score: float,
    time_spent: int = 0,
) -> None:
    """
    Update UserTaxonomyStats after a question is answered.
    Delegates to stats_service which handles the taxonomy tree walk.
    """
    score_decimal = Decimal(str(score))
    max_score_decimal = Decimal(str(max_score))
    
    await update_user_taxonomy_stats(
        db=db,
        user_id=user_id,
        question_id=question_id,
        score=score_decimal,
        max_score=max_score_decimal,
        time_spent=time_spent,
    )
