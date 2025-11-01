import pytest


@pytest.mark.asyncio
async def test_text_and_numeric_grading(client):
    # Create text question with accepted answers
    q_text = {
        "title": "TextQ",
        "answer_type": "text",
        "scoring": {"accepted_answers": ["yes", "y"], "max_score": 5},
        "parts": [{"index": 0, "part_type": "text", "content": "Do you agree?"}],
        "options": [],
    }
    r = await client.post("/api/v1/questions", json=q_text)
    assert r.status_code == 201
    qid_text = r.json()["id"]

    # Create numeric question
    q_num = {
        "title": "NumQ",
        "answer_type": "numeric",
        "scoring": {"answer": 3.14, "tolerance": 0.01, "max_score": 10},
        "parts": [{"index": 0, "part_type": "text", "content": "Enter pi approx"}],
        "options": [],
    }
    r = await client.post("/api/v1/questions", json=q_num)
    assert r.status_code == 201
    qid_num = r.json()["id"]

    # Create quiz
    r = await client.post("/api/v1/quizzes", json={"title": "Grading Quiz"})
    assert r.status_code == 201
    quiz_id = r.json()["id"]

    # Publish quiz with both questions
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/publish", json=[qid_text, qid_num])
    assert r.status_code == 200

    # Register student and start attempt
    r = await client.post("/api/v1/auth/register", json={"email": "gstu@example.com", "password": "pw", "name": "GStu"})
    user_id = r.json()["user"]["id"]
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/start", json={"quiz_id": quiz_id, "user_id": user_id})
    assert r.status_code == 201
    attempt_id = r.json()["id"]

    # Submit correct text answer
    payload = {"question_id": qid_text, "parts": [{"text_response": "Yes"}]}
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    # API may return numeric as Decimal serialized to string; accept numeric-equivalent
    assert float(r.json()["score"]) == 5.0

    # Submit numeric within tolerance
    payload = {"question_id": qid_num, "parts": [{"numeric_response": 3.141}]}
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    assert float(r.json()["score"]) == 10.0

    # Submit numeric outside tolerance
    payload = {"question_id": qid_num, "parts": [{"numeric_response": 3.2}]}
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    assert float(r.json()["score"]) == 0.0
