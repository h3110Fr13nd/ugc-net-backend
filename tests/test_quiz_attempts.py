import pytest


@pytest.mark.asyncio
async def test_quiz_publish_and_attempt_flow(client):
    # Register a user
    r = await client.post("/api/v1/auth/register", json={"email": "stu@example.com", "password": "pw", "name": "Student"})
    assert r.status_code == 200
    user = r.json()["user"]
    user_id = user["id"]

    # Create a question linked to a taxonomy
    q = {
        "title": "Simple MCQ",
        "description": "What is 1+1?",
        "answer_type": "options",
        "parts": [{"index": 0, "part_type": "text", "content": "1+1?"}],
        "options": [
            {"label": "A", "index": 0, "is_correct": False, "parts": [{"index": 0, "part_type": "text", "content": "1"}]},
            {"label": "B", "index": 1, "is_correct": True, "parts": [{"index": 0, "part_type": "text", "content": "2"}]},
        ],
    }
    r = await client.post("/api/v1/questions", json=q)
    assert r.status_code == 201
    created = r.json()
    qid = created["id"]

    # Create a taxonomy node and link the question to it
    t = {"name": "Arithmetic", "node_type": "topic"}
    r = await client.post("/api/v1/taxonomy", json=t)
    assert r.status_code == 201
    tax = r.json()
    tid = tax["id"]

    # Link question to taxonomy via direct DB API (no endpoint yet) by creating QuestionTaxonomy record
    # Use a small helper endpoint-like flow: create a minimal question_taxonomy via POST to questions endpoint if supported
    # The app currently doesn't have a direct endpoint, so instead we will create a small patch by calling the internal API path
    # There's no public endpoint; we skip explicit link and rely on absence of taxonomy links for stats test.

    # Create a quiz
    quiz = {"title": "Sample Quiz", "description": "Test quiz"}
    r = await client.post("/api/v1/quizzes", json=quiz)
    assert r.status_code == 201
    quiz_created = r.json()
    quiz_id = quiz_created["id"]

    # Publish quiz with the question id
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/publish", json=[qid])
    assert r.status_code == 200
    data = r.json()
    assert "quiz_version_id" in data

    # Start attempt
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/start", json={"quiz_id": quiz_id, "user_id": user_id})
    assert r.status_code == 201
    attempt = r.json()
    attempt_id = attempt["id"]

    # Submit answer selecting the correct option
    # Need to assemble selected_option_ids from created question
    options = created.get("options", [])
    correct_ids = [o["id"] for o in options if o.get("is_correct")]
    payload = {
        "question_id": qid,
        "parts": [{"selected_option_ids": correct_ids}]
    }
    r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
    assert r.status_code == 200
    qa = r.json()
    assert qa["score"] is not None

