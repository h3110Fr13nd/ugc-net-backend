import pytest
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import Question, QuizAttempt, QuestionAttempt, User
from app.db.base import get_session

# We need to use TestClient for WebSockets
@pytest.fixture
def test_client(test_session):
    # Override dependency
    async def override_get_session():
        yield test_session
    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)

@pytest.mark.asyncio
async def test_stream_answer_flow(test_client, test_session):
    # 1. Setup Data
    # Create a user
    user = User(email="test@example.com", password_hash="hash")
    test_session.add(user)
    await test_session.flush()

    question = Question(
        title="Test Question",
        description="Explain gravity.",
        answer_type="text",
        scoring={},
        meta_data={}
    )
    test_session.add(question)
    
    quiz_attempt = QuizAttempt(
        quiz_id=question.id, # Hack: using question id as quiz id for simplicity as FKs might be loose or mocked
        # In real integration test we need valid Quiz. 
        # But let's just create a Quiz first to be safe.
    )
    # Actually, let's create a proper Quiz
    from app.db.models import Quiz
    quiz = Quiz(title="Test Quiz", meta_data={})
    test_session.add(quiz)
    await test_session.flush()
    
    # Add parts and options
    from app.db.models import QuestionPart, Option
    part = QuestionPart(question_id=question.id, index=0, part_type="text", content="What is gravity?")
    test_session.add(part)
    
    option1 = Option(question_id=question.id, index=0, label="A force", is_correct=True)
    option2 = Option(question_id=question.id, index=1, label="A fruit", is_correct=False)
    test_session.add(option1)
    test_session.add(option2)
    
    quiz_attempt = QuizAttempt(user_id=user.id, quiz_id=quiz.id, meta_data={})
    test_session.add(quiz_attempt)
    await test_session.commit()
    
    # 2. Mock Google GenAI and KeyManager
    # We need to mock key_manager.get_client() to return our mock client
    with patch("app.api.v1.ws_attempts.key_manager.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Mock the stream response
        mock_chunk1 = MagicMock()
        mock_chunk1.text = '{"score": 0.8, "explanation": '
        mock_chunk2 = MagicMock()
        mock_chunk2.text = '[{"type": "text", "content": "Gravity is a force."}]}'
        
        # Let's mock generate_content_stream to return an iterator
        mock_client.models.generate_content_stream.return_value = [mock_chunk1, mock_chunk2]
        
        # 3. Connect WebSocket
        with test_client.websocket_connect(f"/api/v1/ws/quiz-attempts/{quiz_attempt.id}/question/{question.id}/stream-answer") as websocket:
            # Send answer
            payload = {
                "parts": [{"text_response": "It pulls things down."}],
                "attempt_index": 1
            }
            websocket.send_json(payload)
            
            # Receive messages
            # Expect: explanation_start
            msg1 = websocket.receive_json()
            print(f"DEBUG: Received message: {msg1}")
            print(f"DEBUG: Message keys: {msg1.keys() if isinstance(msg1, dict) else 'not a dict'}")
            if "error" in msg1:
                print(f"DEBUG: Error message: {msg1['error']}")
            assert "type" in msg1, f"Expected 'type' key in message, got: {msg1}"
            assert msg1["type"] == "explanation_start"
            assert msg1["cached"] is False
            
            # Expect: chunks
            msg2 = websocket.receive_json()
            assert msg2["type"] == "llm_chunk"
            # We are just streaming raw text in the implementation
            
            msg3 = websocket.receive_json()
            assert msg3["type"] == "llm_chunk"
            
            # Expect: explanation_end
            msg4 = websocket.receive_json()
            assert msg4["type"] == "explanation_end"
            
    # 4. Verify DB side effects (if implemented in ws_attempts)
    # Currently ws_attempts.py has placeholders for saving.
    # If we implemented saving, we would check QuestionAttempt here.
