import pytest


@pytest.mark.asyncio
async def test_question_taxonomy_link_unlink(client):
    # Create a question
    q = {
        "title": "TaxQ",
        "answer_type": "text",
        "parts": [{"index": 0, "part_type": "text", "content": "What?"}],
        "options": [],
    }
    r = await client.post("/api/v1/questions", json=q)
    assert r.status_code == 201
    qid = r.json()["id"]

    # Create taxonomy
    t = {"name": "Topic X", "node_type": "topic"}
    r = await client.post("/api/v1/taxonomy", json=t)
    assert r.status_code == 201
    tid = r.json()["id"]

    # Link
    r = await client.post(f"/api/v1/questions/{qid}/taxonomy", params={"taxonomy_id": tid})
    # Our endpoint expects taxonomy_id as query param; allow 201 or 200 depending on client lib
    assert r.status_code in (200, 201)

    # Duplicate link should fail
    r = await client.post(f"/api/v1/questions/{qid}/taxonomy", params={"taxonomy_id": tid})
    assert r.status_code == 400

    # Unlink
    r = await client.delete(f"/api/v1/questions/{qid}/taxonomy/{tid}")
    assert r.status_code == 204

    # Unlink again -> 404
    r = await client.delete(f"/api/v1/questions/{qid}/taxonomy/{tid}")
    assert r.status_code == 404
