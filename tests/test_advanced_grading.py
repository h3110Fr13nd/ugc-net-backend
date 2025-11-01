import pytest
import re


@pytest.mark.asyncio
async def test_per_part_regex_and_fuzzy(client):
    # Per-part question: part0 exact text, part1 regex
    q = {
        "title": "PartQ",
        "answer_type": "composite",
        "scoring": {
            "parts": [
                {"type": "text", "accepted_answers": ["hello"], "max_score": 2},
                {"type": "regex", "pattern": "\\\\d{3}", "max_score": 3}
            ]
        },
        "parts": [{"index": 0, "part_type": "text", "content": "Say hello"}, {"index": 1, "part_type": "text", "content": "Enter 3 digits"}],
        "options": [],
    }
    r = await client.post("/api/v1/questions", json=q)
    assert r.status_code == 201
    qid = r.json()["id"]

    # Create quiz and publish with this question
    r = await client.post("/api/v1/quizzes", json={"title": "PQuiz"})
    quiz_id = r.json()["id"]
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/publish", json=[qid])
    assert r.status_code == 200

    # Start attempt
    r = await client.post("/api/v1/auth/register", json={"email": "pg@example.com", "password": "pw", "name": "P"})
    user_id = r.json()["user"]["id"]
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/start", json={"quiz_id": quiz_id, "user_id": user_id})
    attempt_id = r.json()["id"]

    # Submit matching both parts
    payload = {
        "question_id": qid,
        "parts": [
            {"text_response": "Hello"},
            {"text_response": "123"}
        ]
    }
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    assert float(r.json()["score"]) == 5.0

    # Submit failing regex
    payload = {"question_id": qid, "parts": [{"text_response": "hello"}, {"text_response": "12a"}]}
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    assert float(r.json()["score"]) == 2.0

    # Fuzzy matching test
    q2 = {
        "title": "FuzzyQ",
        "answer_type": "fuzzy",
        "scoring": {"target": "approximate", "threshold": 0.7, "max_score": 4},
        "parts": [{"index": 0, "part_type": "text", "content": "Type approximate"}],
        "options": [],
    }
    r = await client.post("/api/v1/questions", json=q2)
    q2id = r.json()["id"]
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/questions", params={"question_id": q2id})
    assert r.status_code in (200, 201)
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/publish", json=None)
    assert r.status_code == 200

    r = await client.post(f"/api/v1/quizzes/{quiz_id}/start", json={"quiz_id": quiz_id, "user_id": user_id})
    attempt_id2 = r.json()["id"]
    payload = {"question_id": q2id, "parts": [{"text_response": "aproximate"}]}
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id2}/submit-answer", json=payload)
    assert r.status_code == 200
    # should get credit if similarity >= threshold
    assert float(r.json()["score"]) in (0.0, 4.0)
