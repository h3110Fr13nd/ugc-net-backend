import json
from uuid import UUID
from typing import Literal
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

from app.db.base import get_session, AsyncSessionLocal
from app.db.models import (
    Question,
    Option,
    QuestionTaxonomy,
    Quiz,
)
from app.core.config import key_manager
from app.core.prompts import build_grading_prompt
from app.services.attempt_service import (
    save_question_attempt,
    update_attempt_stats,
    create_or_get_quiz_attempt,
)

router = APIRouter(tags=["ws_attempts"])

# Pydantic models for request/response
class CreateQuizAttemptRequest(BaseModel):
    """Request to create a new quiz attempt."""
    quiz_id: UUID | None = Field(None, description="Optional ID of the quiz. If None, creates standalone attempt for random questions")
    user_id: UUID = Field(description="ID of the user")
    quiz_version_id: UUID | None = Field(None, description="Optional quiz version ID")

class CreateQuizAttemptResponse(BaseModel):
    """Response containing the created quiz attempt."""
    id: UUID = Field(description="ID of the created quiz attempt")
    quiz_id: UUID | None = Field(None, description="ID of the quiz (None if standalone attempt)")
    user_id: UUID = Field(description="ID of the user")
    status: str = Field(description="Status of the attempt")

class ExplanationBlock(BaseModel):
    """A single explanation block."""
    type: Literal["text", "code"] = Field(description="Type of block: 'text' or 'code'")
    content: str = Field(description="Content of the block")

class ScoringResponse(BaseModel):
    """LLM scoring response - score is at the end so LLM generates explanation first."""
    explanation: list[ExplanationBlock] = Field(description="List of explanation blocks explaining the answer")
    score: float = Field(description="Score from 0.0 to 1.0, determined after generating explanation")


@router.post("/quiz-attempts", response_model=CreateQuizAttemptResponse, status_code=201)
async def create_quiz_attempt(
    request: CreateQuizAttemptRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new quiz attempt.
    
    This endpoint must be called before starting to answer questions via WebSocket.
    Returns the attempt ID that should be used in the WebSocket URL.
    
    Supports two modes:
    - With quiz_id: User takes a specific quiz
    - Without quiz_id: User answers random/standalone questions
    """
    try:
        # If quiz_id is provided, validate it exists
        if request.quiz_id:
            from app.db.models import Quiz
            stmt = select(Quiz).where(Quiz.id == request.quiz_id)
            result = await db.execute(stmt)
            quiz = result.scalar()
            
            if not quiz:
                print(f"✗ Quiz {request.quiz_id} not found")
                raise HTTPException(
                    status_code=404,
                    detail=f"Quiz with ID {request.quiz_id} not found"
                )
        
        # Create the quiz attempt (quiz_id can be None for standalone attempts)
        attempt = await create_or_get_quiz_attempt(
            db=db,
            quiz_id=request.quiz_id,
            user_id=request.user_id,
            quiz_version_id=request.quiz_version_id,
        )
        
        # Commit changes
        await db.commit()
        
        quiz_mode = "quiz" if request.quiz_id else "standalone"
        print(f"✓ Created {quiz_mode} attempt {attempt.id} for user {request.user_id}")
        
        return CreateQuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            user_id=attempt.user_id,
            status=attempt.status,
        )
    except ValueError as e:
        await db.rollback()
        print(f"✗ Validation error: {e}")
        raise
    except Exception as e:
        await db.rollback()
        print(f"✗ Error creating quiz attempt: {e}")
        import traceback
        traceback.print_exc()
        raise


@router.websocket("/ws/quiz-attempts/{attempt_id}/question/{question_id}/stream-answer")
async def stream_answer(
    websocket: WebSocket,
    attempt_id: UUID,
    question_id: UUID,
):
    print(f"WS: Connection request for attempt={attempt_id}, question={question_id}")
    await websocket.accept()
    print("WS: Connection accepted")
    
    # Validate that attempt_id is not a zero UUID
    if attempt_id == UUID('00000000-0000-0000-0000-000000000000'):
        print("WS: Error - received zero UUID as attempt_id")
        await websocket.send_json({"error": "Invalid attempt ID - received zero UUID. Ensure quiz attempt is created before answering."})
        await websocket.close()
        return
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"WS: Received data: {data}")
            payload = json.loads(data)
            
            # Create a fresh session for this message
            async with AsyncSessionLocal() as db:
                try:
                    # 1. Fetch Question with eager loading for full context
                    query = (
                        select(Question)
                        .where(Question.id == question_id)
                        .options(
                            selectinload(Question.parts),
                            selectinload(Question.options).selectinload(Option.parts),
                            selectinload(Question.taxonomy_links).selectinload(QuestionTaxonomy.taxonomy_node)
                        )
                    )
                    result = await db.execute(query)
                    question = result.scalars().first()
                    
                    if not question:
                        print(f"WS: Question {question_id} not found")
                        await websocket.send_json({"error": "Question not found"})
                        break
                    
                    print(f"WS: Found question: {question.title}")

                    # 2. Check if explanation is cached
                    cached_explanation = question.explanation
                    
                    needs_llm = False
                    if not cached_explanation:
                        needs_llm = True
                    
                    if question.answer_type == "text" and not question.scoring:
                        needs_llm = True
                    
                    print(f"WS: Needs LLM? {needs_llm}")

                    if not needs_llm:
                        # Stream cached explanation
                        print("WS: Streaming cached explanation")
                        await websocket.send_json({"type": "explanation_start", "cached": True})
                        if cached_explanation:
                            for part in cached_explanation:
                                await websocket.send_json({"type": "explanation_chunk", "chunk": part})
                        await websocket.send_json({"type": "explanation_end"})
                        await websocket.send_json({"type": "result", "score": 0, "status": "saved (mock)"})
                    else:
                        # 4. Stream from LLM using LangChain
                        print("WS: Starting LLM stream")
                        await websocket.send_json({"type": "explanation_start", "cached": False})
                        
                        # Construct Rich Prompt with full taxonomical hierarchy
                        taxonomy_context = ""
                        if question.taxonomy_links:
                            # Build full hierarchy paths for each taxonomy link
                            full_paths = []
                            for link in question.taxonomy_links:
                                if not link.taxonomy_node or not link.taxonomy_node.path:
                                    continue
                                
                                # Parse the path (e.g., "uuid1.uuid2.uuid3")
                                path_ids = link.taxonomy_node.path.split('.')
                                
                                # Fetch all nodes in the path to build hierarchy
                                from uuid import UUID as UUIDType
                                valid_uuids = []
                                for pid in path_ids:
                                    try:
                                        valid_uuids.append(UUIDType(pid))
                                    except (ValueError, AttributeError):
                                        continue
                                
                                if valid_uuids:
                                    # Query all nodes in path
                                    from app.db.models import Taxonomy
                                    nodes_query = select(Taxonomy).where(Taxonomy.id.in_(valid_uuids))
                                    nodes_result = await db.execute(nodes_query)
                                    nodes_map = {str(n.id): n.name for n in nodes_result.scalars().all()}
                                    
                                    # Build readable path
                                    readable_path = []
                                    for pid in path_ids:
                                        if pid in nodes_map:
                                            readable_path.append(nodes_map[pid])
                                    
                                    if readable_path:
                                        full_paths.append(' > '.join(readable_path))
                            
                            if full_paths:
                                taxonomy_context = f"Taxonomical Context (Full Hierarchy): {' | '.join(full_paths)}\\n"
                        
                        parts_content = ""
                        for p in question.parts:
                            if p.content:
                                parts_content += f"Part {p.index}: {p.content}\\n"
                            # TODO: Handle media (images) here
                        
                        options_content = ""
                        option_map = {} # Map ID to text for lookup
                        correct_answers = []
                        if question.options:
                            options_content = "Options:\\n"
                            for o in question.options:
                                opt_text = o.label or ""
                                for op in o.parts:
                                    if op.content:
                                        opt_text += f" {op.content}"
                                options_content += f"- {opt_text}\\n"
                                option_map[str(o.id)] = opt_text
                                if o.is_correct:
                                    correct_answers.append(opt_text)

                        user_response_raw = payload.get('parts', [{}])[0].get('text_response', '')
                        user_answer_text = user_response_raw
                        
                        # Check if response is an Option ID
                        if user_response_raw in option_map:
                            user_answer_text = option_map[user_response_raw]
                            print(f"WS: Resolved Option ID {user_response_raw} to '{user_answer_text}'")

                        correct_answer_text = ", ".join(correct_answers) if correct_answers else "Unknown"
                        is_single_correct = len(correct_answers) == 1
                        print(f"WS: Single correct answer: {is_single_correct}")

                        # Build prompt using template
                        prompt = build_grading_prompt(
                            taxonomy_context=taxonomy_context,
                            question_title=question.title or '',
                            question_description=question.description or '',
                            parts_content=parts_content,
                            options_content=options_content,
                            correct_answer_text=correct_answer_text,
                            user_answer_text=user_answer_text,
                            is_single_correct=is_single_correct,
                        )
                        print(prompt, "-------------")
                        # Get API key and create LangChain LLM
                        api_key = await key_manager.get_api_key()
                        llm = ChatGoogleGenerativeAI(
                            model="gemini-2.5-flash",
                            google_api_key=api_key,
                            temperature=0.7
                        )
                        
                        # Enable Google Search grounding
                        llm_with_search = llm.bind_tools([{"google_search": {}}])
                        
                        # Create structured LLM with json_schema method
                        structured_llm = llm_with_search.with_structured_output(
                            schema=ScoringResponse.model_json_schema(),
                            method="json_schema"
                        )
                        
                        # Stream structured output
                        full_response = {}
                        chunk_num = 0
                        last_sent_blocks = []  # Track last sent state of each block
                        
                        print("WS: Waiting for LLM chunks...")
                        async for chunk in structured_llm.astream(prompt):
                            chunk_num += 1
                            print(f"WS: Received chunk {chunk_num} {chunk}")
                            
                            # Merge chunks
                            if chunk_num == 1:
                                full_response = chunk
                            else:
                                if isinstance(chunk, dict) and isinstance(full_response, dict):
                                    full_response.update(chunk)
                            
                            # Send incremental update
                            await websocket.send_json({
                                "type": "structured_chunk",
                                "score": full_response.get('score'),
                                "explanation_count": len(full_response.get('explanation', []))
                            })
                            
                            # Send explanation blocks when they change
                            explanations = full_response.get('explanation', [])
                            
                            for i, block in enumerate(explanations):
                                # Check if this block is new or has changed
                                if i >= len(last_sent_blocks) or last_sent_blocks[i] != block:
                                    print(f"WS: Sending updated block {i}: {block}")
                                    await websocket.send_json({
                                        "type": "explanation_block",
                                        "index": i,
                                        "block": block
                                    })
                                    
                                    # Update tracking
                                    if i >= len(last_sent_blocks):
                                        last_sent_blocks.append(block)
                                    else:
                                        last_sent_blocks[i] = block
                        
                        print("WS: LLM stream finished")
                        await websocket.send_json({"type": "explanation_end"})
                        
                        # Extract final score from response
                        final_score = full_response.get('score', 0)
                        if isinstance(final_score, str):
                            try:
                                final_score = float(final_score)
                            except ValueError:
                                final_score = 0.0
                        
                        # 5. SAVE attempt to database
                        print(f"WS: Saving attempt - score={final_score}, question={question_id}, quiz_attempt={attempt_id}, user={payload.get('user_id')}")
                        
                        try:
                            # Validate quiz_attempt exists before saving
                            from app.db.models import QuizAttempt
                            stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id)
                            result = await db.execute(stmt)
                            quiz_attempt = result.scalar()
                            
                            if not quiz_attempt:
                                print(f"WS: Error - QuizAttempt {attempt_id} not found in database")
                                await websocket.send_json({"error": f"QuizAttempt {attempt_id} not found. Please create the attempt first."})
                                await db.rollback()
                                break
                            
                            print(f"WS: Found QuizAttempt {attempt_id}")
                            
                            # Extract user response parts from payload
                            user_answer_parts = []
                            if payload.get('parts'):
                                for part in payload['parts']:
                                    user_answer_parts.append({
                                        "text_response": part.get('text_response'),
                                        "selected_option_ids": part.get('selected_option_ids'),
                                        "numeric_response": part.get('numeric_response'),
                                        "file_media_id": part.get('file_media_id'),
                                        "raw_response": part.get('raw_response'),
                                    })
                            
                            # Save the question attempt with grading details
                            question_attempt = await save_question_attempt(
                                db=db,
                                quiz_attempt_id=attempt_id,
                                question_id=question_id,
                                user_answer_parts=user_answer_parts,
                                score=final_score,
                                max_score=1.0,
                                grading_details={
                                    "explanation": full_response.get('explanation', []),
                                    "score": final_score,
                                },
                                attempt_index=payload.get('attempt_index', 1),
                            )
                            
                            # Update user taxonomy statistics
                            user_id = payload.get('user_id')
                            if user_id:
                                try:
                                    user_id = UUID(user_id)
                                except (ValueError, TypeError):
                                    user_id = None
                            
                            if user_id:
                                is_correct = final_score >= 0.8  # Consider >= 80% as correct
                                await update_attempt_stats(
                                    db=db,
                                    user_id=user_id,
                                    question_id=question_id,
                                    is_correct=is_correct,
                                    score=final_score,
                                    max_score=1.0,
                                )
                            
                            # Commit changes
                            await db.commit()
                            print(f"WS: Successfully saved question attempt {question_attempt.id}")
                            
                        except Exception as save_error:
                            print(f"WS: Error saving attempt: {save_error}")
                            import traceback
                            traceback.print_exc()
                            await db.rollback()
                        
                        await websocket.send_json({
                            "type": "result",
                            "score": final_score,
                            "total_blocks": len(full_response.get('explanation', [])),
                            "saved": True
                        })
                        
                except Exception as e:
                    print(f"WS Error inside loop: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_json({"error": str(e)})
                
                # End of async with block - session auto-commits/rolls back

    except WebSocketDisconnect:
        print("WS: Client disconnected")
    except Exception as e:
        print(f"WS: Fatal error: {e}")
        import traceback
        traceback.print_exc()
