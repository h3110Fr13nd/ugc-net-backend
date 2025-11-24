import json
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

from app.db.base import get_session
from app.db.models import (
    Question,
    Option,
    QuestionTaxonomy,
)
from app.core.config import key_manager
from app.core.prompts import build_grading_prompt

router = APIRouter(tags=["ws_attempts"])

# Pydantic models for structured output
class ExplanationBlock(BaseModel):
    """A single explanation block."""
    type: Literal["text", "code"] = Field(description="Type of block: 'text' or 'code'")
    content: str = Field(description="Content of the block")

class ScoringResponse(BaseModel):
    """LLM scoring response - score is at the end so LLM generates explanation first."""
    explanation: list[ExplanationBlock] = Field(description="List of explanation blocks explaining the answer")
    score: float = Field(description="Score from 0.0 to 1.0, determined after generating explanation")

@router.websocket("/ws/quiz-attempts/{attempt_id}/question/{question_id}/stream-answer")
async def stream_answer(
    websocket: WebSocket,
    attempt_id: UUID,
    question_id: UUID,
):
    print(f"WS: Connection request for attempt={attempt_id}, question={question_id}")
    await websocket.accept()
    print("WS: Connection accepted")
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"WS: Received data: {data}")
            payload = json.loads(data)
            
            # Create a fresh session for this operation
            async for db in get_session():
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
                            
                            # Send new explanation blocks
                            explanations = full_response.get('explanation', [])
                            if explanations and chunk_num > 1:
                                # Send the latest block
                                latest_block = explanations[-1]
                                print(f"WS: Sending block: {latest_block}")
                                await websocket.send_json({
                                    "type": "explanation_block",
                                    "block": latest_block
                                })
                        
                        print("WS: LLM stream finished")
                        await websocket.send_json({"type": "explanation_end"})
                        await websocket.send_json({
                            "type": "result",
                            "score": full_response.get('score', 0),
                            "total_blocks": len(full_response.get('explanation', []))
                        })
                        
                except Exception as e:
                    print(f"WS Error inside loop: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_json({"error": str(e)})
                
                # Break after processing one message
                break
            
            # Break after one request-response cycle
            break

    except WebSocketDisconnect:
        print("WS: Client disconnected")
    except Exception as e:
        print(f"WS: Fatal error: {e}")
        import traceback
        traceback.print_exc()
