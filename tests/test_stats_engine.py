import pytest
import uuid

from sqlalchemy import select
from app.db.models import UserTaxonomyStats, QuestionTaxonomy, Taxonomy


@pytest.mark.asyncio
async def test_stats_aggregation(client, test_session):
    # Create taxonomy tree: Root -> Child
    r = await client.post("/api/v1/taxonomy", json={"name": "Root", "node_type": "subject"})
    assert r.status_code == 201
    root_id = r.json()["id"]

    r = await client.post("/api/v1/taxonomy", json={"name": "Child", "node_type": "topic", "parent_id": root_id})
    assert r.status_code == 201
    child_id = r.json()["id"]

    # Create question and link to child
    q = {
        "title": "StatQ",
        "answer_type": "options",
        "parts": [{"index": 0, "part_type": "text", "content": "Pick 1"}],
        "options": [
            {"label": "A", "index": 0, "is_correct": True, "parts": [{"index": 0, "part_type": "text", "content": "Yes"}]},
            {"label": "B", "index": 1, "is_correct": False, "parts": [{"index": 0, "part_type": "text", "content": "No"}]},
        ],
    }
    r = await client.post("/api/v1/questions", json=q)
    qid = r.json()["id"]

    # Link question to taxonomy
    r = await client.post(f"/api/v1/questions/{qid}/taxonomy", params={"taxonomy_id": child_id})
    assert r.status_code in (200, 201)

    # Register user and start attempt, submit correct answer multiple times
    r = await client.post("/api/v1/auth/register", json={"email": "s1@example.com", "password": "pw", "name": "S1"})
    uid = r.json()["user"]["id"]

    # Create quiz and publish
    r = await client.post("/api/v1/quizzes", json={"title": "StatsQuiz"})
    quiz_id = r.json()["id"]
    r = await client.post(f"/api/v1/quizzes/{quiz_id}/publish", json=[qid])
    assert r.status_code == 200

    # Perform 3 correct submissions
    for _ in range(3):
        r = await client.post(f"/api/v1/quizzes/{quiz_id}/start", json={"quiz_id": quiz_id, "user_id": uid})
        attempt_id = r.json()["id"]
        # submit correct
        options = (await client.get(f"/api/v1/questions/{qid}")).json()["options"]
        correct_ids = [o["id"] for o in options if o.get("is_correct")]
        payload = {"question_id": qid, "parts": [{"selected_option_ids": correct_ids}]}
        r = await client.post(f"/api/v1/quiz-attempts/{attempt_id}/submit-answer", json=payload)
        assert r.status_code == 200

    # Query UserTaxonomyStats directly using test_session
    # convert ids to UUID objects for direct DB queries
    uid_uuid = uuid.UUID(uid)
    child_uuid = uuid.UUID(child_id)
    root_uuid = uuid.UUID(root_id)

    res = await test_session.execute(select(UserTaxonomyStats).where(UserTaxonomyStats.user_id == uid_uuid, UserTaxonomyStats.taxonomy_id == child_uuid))
    child_stats = res.scalar_one_or_none()
    assert child_stats is not None
    assert child_stats.questions_attempted >= 3

    # Parent stats should also reflect the attempts (upsampled)
    res = await test_session.execute(select(UserTaxonomyStats).where(UserTaxonomyStats.user_id == uid_uuid, UserTaxonomyStats.taxonomy_id == root_uuid))
    parent_stats = res.scalar_one_or_none()
    assert parent_stats is not None
    assert parent_stats.questions_attempted >= 3

