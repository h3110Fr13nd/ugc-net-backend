from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.db.base import get_session
from app.db.models import QuestionAttempt, QuestionAttemptPart, User
from app.core.security import get_current_user
from app.api.v1.schemas import QuestionAttemptResponse

router = APIRouter(tags=["history"])

@router.get("/questions/{question_id}/attempts", response_model=List[QuestionAttemptResponse])
async def list_question_attempts(
    question_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all attempts for a specific question by the current user."""
    # We need to join with QuizAttempt to filter by user_id
    # But QuestionAttempt doesn't have user_id directly, it's on QuizAttempt
    from app.db.models import QuizAttempt
    
    stmt = (
        select(QuestionAttempt)
        .join(QuizAttempt, QuestionAttempt.quiz_attempt_id == QuizAttempt.id)
        .where(
            QuestionAttempt.question_id == question_id,
            QuizAttempt.user_id == current_user.id
        )
        .order_by(desc(QuestionAttempt.started_at))
    )
    
    result = await db.execute(stmt)
    attempts = result.scalars().all()
    
    # We need to manually load parts if not lazy loaded or use response model to trigger it
    # Ideally we use selectinload in the query
    from sqlalchemy.orm import selectinload
    stmt = (
        select(QuestionAttempt)
        .options(selectinload(QuestionAttempt.parts))
        .join(QuizAttempt, QuestionAttempt.quiz_attempt_id == QuizAttempt.id)
        .where(
            QuestionAttempt.question_id == question_id,
            QuizAttempt.user_id == current_user.id
        )
        .order_by(desc(QuestionAttempt.started_at))
    )
    result = await db.execute(stmt)
    attempts = result.scalars().all()
    
    return attempts

@router.get("/questions/{question_id}/stats")
async def get_question_stats(
    question_id: UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get statistics for a specific question for the current user."""
    from app.db.models import QuizAttempt
    
    # Count total attempts
    count_stmt = (
        select(func.count())
        .select_from(QuestionAttempt)
        .join(QuizAttempt, QuestionAttempt.quiz_attempt_id == QuizAttempt.id)
        .where(
            QuestionAttempt.question_id == question_id,
            QuizAttempt.user_id == current_user.id
        )
    )
    total_attempts = (await db.execute(count_stmt)).scalar() or 0
    
    # Count correct attempts (assuming score == max_score and max_score > 0)
    correct_stmt = (
        select(func.count())
        .select_from(QuestionAttempt)
        .join(QuizAttempt, QuestionAttempt.quiz_attempt_id == QuizAttempt.id)
        .where(
            QuestionAttempt.question_id == question_id,
            QuizAttempt.user_id == current_user.id,
            QuestionAttempt.score == QuestionAttempt.max_score,
            QuestionAttempt.max_score > 0
        )
    )
    correct_attempts = (await db.execute(correct_stmt)).scalar() or 0
    
    return {
        "question_id": str(question_id),
        "total_attempts": total_attempts,
        "correct_attempts": correct_attempts,
        "is_solved": correct_attempts > 0
    }
