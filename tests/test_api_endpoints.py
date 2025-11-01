import pytest
import io
import json
from uuid import UUID


@pytest.mark.asyncio
async def test_auth_register_and_login(client):
    # Register
    payload = {"email": "alice@example.com", "password": "secret123", "name": "Alice"}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == "alice@example.com"

    # Login
    r2 = await client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "secret123"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "access_token" in data2
    assert data2["user"]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_auth_google_url_and_token_flow(client, monkeypatch):
    # google/url requires redirect_uri
    r = await client.get("/api/v1/auth/google/url")
    assert r.status_code == 400

    # Now test google/token by mocking httpx.AsyncClient to return a token response
    class DummyResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

        @property
        def text(self):
            return json.dumps(self._body)

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, headers=None):
            return DummyResp(200, {"access_token": "fake", "id_token": "fake-id"})

        async def get(self, url, headers=None):
            # userinfo URL
            if "userinfo" in url:
                return DummyResp(200, {"sub": "gsub", "email": "bob@example.com", "name": "Bob"})
            return DummyResp(200, {})

    monkeypatch.setattr("app.api.v1.auth.httpx.AsyncClient", DummyClient)

    r = await client.post("/api/v1/auth/google/token", json={"code": "x", "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_questions_crud(client):
    # List initially empty
    r = await client.get("/api/v1/questions")
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 0 or payload["questions"] == []

    # Create a question
    q = {
        "title": "Sample Q",
        "description": "desc",
        "answer_type": "options",
        "parts": [{"index": 0, "part_type": "text", "content": "What is 2+2?"}],
        "options": [{"label": "A", "index": 0, "is_correct": True, "parts": [{"index": 0, "part_type": "text", "content": "4"}]}],
    }
    r = await client.post("/api/v1/questions", json=q)
    assert r.status_code == 201
    created = r.json()
    qid = created["id"]

    # Get
    r = await client.get(f"/api/v1/questions/{qid}")
    assert r.status_code == 200
    got = r.json()
    assert got["title"] == "Sample Q"

    # Update
    r = await client.put(f"/api/v1/questions/{qid}", json={"title": "Updated Q"})
    assert r.status_code == 200
    updated = r.json()
    assert updated["title"] == "Updated Q"

    # Delete
    r = await client.delete(f"/api/v1/questions/{qid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_media_upload_and_lifecycle(client):
    # Upload a small PNG file
    file_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    files = {"file": ("test.png", file_bytes, "image/png")}
    r = await client.post("/api/v1/media/upload", files=files)
    assert r.status_code == 201
    media = r.json()
    mid = media["id"]

    # Get media
    r = await client.get(f"/api/v1/media/{mid}")
    assert r.status_code == 200

    # List media
    r = await client.get("/api/v1/media/")
    assert r.status_code == 200
    arr = r.json()
    assert any(m["id"] == mid for m in arr)

    # Delete media
    r = await client.delete(f"/api/v1/media/{mid}")
    assert r.status_code == 204

    # Not found afterwards
    r = await client.get(f"/api/v1/media/{mid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_media_image_only_and_size_checks(client, monkeypatch):
    # Force tiny max size
    from app.api.v1 import media as media_mod
    monkeypatch.setattr(media_mod, "MAX_FILE_SIZE", 10)

    # Upload too large file
    file_bytes = b"0" * 1024
    files = {"file": ("big.png", file_bytes, "image/png")}
    r = await client.post("/api/v1/media/upload", files=files)
    assert r.status_code == 413

    # upload-image rejects non-image
    files = {"file": ("song.mp3", b"abc", "audio/mpeg")}
    r = await client.post("/api/v1/media/upload-image", files=files)
    assert r.status_code == 400

    # upload-image accepts image
    files = {"file": ("ok.png", b"\x89PNG\r\n\x1a\n" + b"0" * 5, "image/png")}
    # Temporarily increase MAX_FILE_SIZE so this small file is allowed
    monkeypatch.setattr(media_mod, "MAX_FILE_SIZE", 10 * 1024 * 1024)
    r = await client.post("/api/v1/media/upload-image", files=files)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_auth_negative_flows(client, monkeypatch):
    # Register once
    payload = {"email": "carol@example.com", "password": "pw", "name": "Carol"}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 200

    # Register same email again -> 400
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400

    # Login with wrong password
    r3 = await client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "wrong"})
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_google_verify_variants(client, monkeypatch):
    # Prepare dummy responses for tokeninfo
    class DummyResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

        @property
        def text(self):
            return json.dumps(self._body)

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            # tokeninfo endpoint
            if "tokeninfo" in url:
                # valid tokeninfo with correct audience
                return DummyResp(200, {"aud": ""})
            return DummyResp(200, {})

    # Case: tokeninfo returns non-200 -> 401
    class BadClient(DummyClient):
        async def get(self, url, headers=None):
            return DummyResp(400, {"error": "bad"})

    monkeypatch.setattr("app.api.v1.auth.httpx.AsyncClient", BadClient)
    r = await client.post("/api/v1/auth/google/verify", json={"id_token": "x"})
    assert r.status_code == 401

    # Case: tokeninfo returns 200 but missing fields -> 400
    class MissingFieldsClient(DummyClient):
        async def get(self, url, headers=None):
            return DummyResp(200, {"aud": "not-this-client"})

    monkeypatch.setattr("app.api.v1.auth.httpx.AsyncClient", MissingFieldsClient)
    r = await client.post("/api/v1/auth/google/verify", json={"id_token": "x"})
    assert r.status_code in (400, 401)


@pytest.mark.asyncio
async def test_google_verify_success_creates_user(client, monkeypatch):
    # Successful tokeninfo -> should create or update user
    class DummyResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

        @property
        def text(self):
            return json.dumps(self._body)

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            # tokeninfo endpoint; return aud equal to the configured CLIENT_ID
            from app.api.v1.auth import CLIENT_ID
            return DummyResp(200, {"aud": CLIENT_ID, "sub": "gsub2", "email": "eve@example.com", "name": "Eve", "picture": "http://p"})

    # inject a DummyClient that returns a tokeninfo with aud == CLIENT_ID
    monkeypatch.setattr("app.api.v1.auth.httpx.AsyncClient", DummyClient)

    # Call verify
    r = await client.post("/api/v1/auth/google/verify", json={"id_token": "valid"})
    # Should either create user or return token; primarily assert no error
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_questions_replace_parts_and_filters(client):
    # Create two questions with different answer_type and difficulty
    q1 = {
        "title": "Q1",
        "answer_type": "options",
        "parts": [{"index": 0, "part_type": "text", "content": "A"}],
        "options": [{"label": "A", "index": 0, "is_correct": True, "parts": [{"index": 0, "part_type": "text", "content": "A"}]}],
    }
    r = await client.post("/api/v1/questions", json=q1)
    assert r.status_code == 201
    q1_id = r.json()["id"]

    q2 = {"title": "Q2", "answer_type": "text", "difficulty": 3}
    r = await client.post("/api/v1/questions", json=q2)
    assert r.status_code == 201
    q2_id = r.json()["id"]

    # Filter by answer_type
    r = await client.get("/api/v1/questions", params={"answer_type": "text"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    # Now replace parts and options for q1
    update_payload = {
        "parts": [{"index": 0, "part_type": "text", "content": "Replaced"}],
        "options": [{"label": "B", "index": 0, "is_correct": False, "parts": [{"index": 0, "part_type": "text", "content": "No"}]}],
    }
    r = await client.put(f"/api/v1/questions/{q1_id}", json=update_payload)
    assert r.status_code == 200
    updated = r.json()
    assert any(p["content"] == "Replaced" for p in updated["parts"]) 
    assert any(o["label"] == "B" for o in updated["options"]) 
