"""Questions CRUD API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.db.base import get_session
from app.db.models import Question, QuestionPart, Option, OptionPart, Media
from app.api.v1.schemas import (
    QuestionCreate,
    QuestionUpdate,
    QuestionResponse,
    QuestionListResponse,
)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    answer_type: Optional[str] = None,
    difficulty: Optional[int] = None,
    db: AsyncSession = Depends(get_session),
):
    """List questions with pagination and optional filters."""
    # Build base query
    query = select(Question).options(
        selectinload(Question.parts).selectinload(QuestionPart.media),
        selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
    )
    
    # Apply filters
    if answer_type:
        query = query.where(Question.answer_type == answer_type)
    if difficulty is not None:
        query = query.where(Question.difficulty == difficulty)
    
    # Count total
    count_query = select(func.count()).select_from(Question)
    if answer_type:
        count_query = count_query.where(Question.answer_type == answer_type)
    if difficulty is not None:
        count_query = count_query.where(Question.difficulty == difficulty)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Question.created_at.desc())
    
    result = await db.execute(query)
    questions = result.scalars().all()
    
    return QuestionListResponse(
        questions=questions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=QuestionResponse, status_code=201)
async def create_question(
    question_data: QuestionCreate,
    db: AsyncSession = Depends(get_session),
):
    """Create a new question with parts and options."""
    # Create question
    question = Question(
        canonical_id=question_data.canonical_id,
        title=question_data.title,
        description=question_data.description,
        answer_type=question_data.answer_type,
        scoring=question_data.scoring,
        difficulty=question_data.difficulty,
        estimated_time_seconds=question_data.estimated_time_seconds,
        meta_data=question_data.meta_data,
        created_by=question_data.created_by,
    )
    db.add(question)
    await db.flush()  # Get question.id
    
    # Create question parts
    for part_data in question_data.parts:
        part = QuestionPart(
            question_id=question.id,
            index=part_data.index,
            part_type=part_data.part_type,
            content=part_data.content,
            content_json=part_data.content_json,
            media_id=part_data.media_id,
            meta_data=part_data.meta_data,
        )
        db.add(part)
    
    # Create options with their parts
    for option_data in question_data.options:
        option = Option(
            question_id=question.id,
            label=option_data.label,
            index=option_data.index,
            is_correct=option_data.is_correct,
            weight=option_data.weight,
            meta_data=option_data.meta_data,
        )
        db.add(option)
        await db.flush()  # Get option.id
        
        # Create option parts
        for opt_part_data in option_data.parts:
            opt_part = OptionPart(
                option_id=option.id,
                index=opt_part_data.index,
                part_type=opt_part_data.part_type,
                content=opt_part_data.content,
                media_id=opt_part_data.media_id,
            )
            db.add(opt_part)
    
    await db.commit()
    
    # Reload with relationships
    query = select(Question).where(Question.id == question.id).options(
        selectinload(Question.parts).selectinload(QuestionPart.media),
        selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
    )
    result = await db.execute(query)
    question = result.scalar_one()
    
    return question


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_session),
):
    """Get a single question by ID with all parts and options."""
    query = select(Question).where(Question.id == question_id).options(
        selectinload(Question.parts).selectinload(QuestionPart.media),
        selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
    )
    result = await db.execute(query)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return question


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    question_data: QuestionUpdate,
    db: AsyncSession = Depends(get_session),
):
    """Update a question. If parts or options are provided, they replace existing ones."""
    query = select(Question).where(Question.id == question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Update basic fields
    update_data = question_data.model_dump(exclude_unset=True, exclude={"parts", "options"})
    for key, value in update_data.items():
        setattr(question, key, value)
    
    # If parts are provided, replace all parts
    if question_data.parts is not None:
        # Delete existing parts
        await db.execute(select(QuestionPart).where(QuestionPart.question_id == question_id))
        for part in (await db.execute(select(QuestionPart).where(QuestionPart.question_id == question_id))).scalars().all():
            await db.delete(part)
        
        # Create new parts
        for part_data in question_data.parts:
            part = QuestionPart(
                question_id=question.id,
                index=part_data.index,
                part_type=part_data.part_type,
                content=part_data.content,
                content_json=part_data.content_json,
                media_id=part_data.media_id,
                meta_data=part_data.meta_data,
            )
            db.add(part)
    
    # If options are provided, replace all options and their parts
    if question_data.options is not None:
        # Delete existing options (cascade will delete option_parts)
        for option in (await db.execute(select(Option).where(Option.question_id == question_id))).scalars().all():
            await db.delete(option)
        
        # Create new options
        for option_data in question_data.options:
            option = Option(
                question_id=question.id,
                label=option_data.label,
                index=option_data.index,
                is_correct=option_data.is_correct,
                weight=option_data.weight,
                meta_data=option_data.meta_data,
            )
            db.add(option)
            await db.flush()
            
            # Create option parts
            for opt_part_data in option_data.parts:
                opt_part = OptionPart(
                    option_id=option.id,
                    index=opt_part_data.index,
                    part_type=opt_part_data.part_type,
                    content=opt_part_data.content,
                    media_id=opt_part_data.media_id,
                )
                db.add(opt_part)
    
    await db.commit()
    
    # Reload with relationships
    query = select(Question).where(Question.id == question_id).options(
        selectinload(Question.parts).selectinload(QuestionPart.media),
        selectinload(Question.options).selectinload(Option.parts).selectinload(OptionPart.media),
    )
    result = await db.execute(query)
    question = result.scalar_one()
    
    return question


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_session),
):
    """Delete a question (cascade deletes parts and options)."""
    query = select(Question).where(Question.id == question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    await db.delete(question)
    await db.commit()
    
    return None
