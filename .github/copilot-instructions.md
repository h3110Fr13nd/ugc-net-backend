<!-- .github/copilot-instructions.md for the `ugc-net-backend` service -->
# Quick instructions for AI coding agents (backend service)

Keep guidance short, concrete, and tied to the `backend/` microservice in this repo.

- Project type: FastAPI web service (async SQLAlchemy + Postgres). Key files:
  - `app/main.py` — app factory and router inclusion (uses `app.include_router(..., prefix="/api/v1")`).
  - `app/api/v1/routes.py` — versioned endpoints example (`GET /api/v1/health`).
  - `app/db/base.py` — async engine (`create_async_engine`), `AsyncSessionLocal`, and `get_session()` dependency.
  - `app/db/models.py` — declarative Base and example models (e.g. `User`).
  - `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example` — development and container workflows.

- Big picture and boundaries:
  - This folder is a single-purpose backend service meant to run independently (it has its own Git remote: `ugc-net-backend`).
  - API versioning is explicit: add new endpoints under `app/api/v<major>/` and mount with `include_router(..., prefix="/api/v<major>")`.
  - The service owns its Postgres schema and should expose database migrations in `migrations/` (use Alembic).

- Local dev & run commands (pick one approach):
  - Docker (recommended for parity):
    - Copy `.env.example` -> `.env` and adjust if needed.
    - Start services: `docker-compose up --build` (app listens on port 8000; Postgres on 5432).
  - Local (venv):
    - `python -m venv .venv && source .venv/bin/activate`
    - Install and use the `uv` dependency manager (preferred for this project):
      - Create a venv for Python 3.14 (preferred) using `uv` (recommended):
        - Remove any existing venv: `rm -rf .venv`
        - If `uv` is not installed yet in your system Python: `python -m pip install --user uv` (or install into a bootstrap venv).
        - Create a new venv via `uv` targeting Python 3.14 (preferred):
          - `uv venv create .venv --python 3.14`
          - If 3.14 is not available on the machine, fall back to a locally available interpreter, e.g. `uv venv create .venv --python python3.13`.
        - Activate the venv:
          - `source .venv/bin/activate`
        - Ensure pip is up-to-date inside the venv: `python -m pip install --upgrade pip`
      - Add runtime dependencies using `uv` (will record them in uv's lock/metadata). Prefer async-first libraries and the latest stable releases:
        - `uv add fastapi uvicorn[standard] sqlalchemy asyncpg`
      - Add dev dependencies with `uv`:
        - `uv add -d pytest pytest-asyncio httpx alembic black pytest-cov`
      - Install from existing requirements files (alternative):
        - `uv pip install -r requirements.txt`
        - `uv pip install -r dev-requirements.txt`
    - Run app:
      - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

- Patterns & conventions to follow when editing backend code:
  - Versioned routers: always place endpoints inside `app/api/vX` and mount them in `app/main.py`.
  - DB sessions: use `get_session()` from `app/db/base.py` as a route dependency (FastAPI Depends) and perform async operations against `AsyncSession`.
  - Declarative models: define models in `app/db/models.py` and import `Base` for migrations (Alembic config should reference `app.db.models.Base`).
  - Keep endpoint handlers small: move business logic into separate service modules if it grows.

- Tests, migrations, and CI:
  - This scaffold currently lacks migrations and tests. Add them under:
    - `migrations/` — Alembic migrations (commit migration scripts to repo).
    - `tests/` — pytest tests for endpoints and DB interactions. Prefer small, focused unit and integration tests.
  - CI should run both Flutter app checks (top-level) and backend tests; add a separate pipeline job for the backend service.

- PR & branching guidance for backend work:
  - Branch naming: `issue-<number>-short-desc` (e.g., `issue-2-fastapi-structure`).
  - Keep changes in a feature branch inside `backend/`, push to the `ugc-net-backend` remote, and open a PR against that repo.
  - PR checklist examples: include migrations (if DB changes), tests, update `.env.example` when adding new env vars, and update README with usage notes.

- Examples from the codebase:
  - Health endpoint: `GET /api/v1/health` implemented in `app/api/v1/routes.py` returns `{ "status": "ok", "version": "v1" }`.
  - DB session injection example pattern:

    - In a route: `async def list_users(db: AsyncSession = Depends(get_session)):` then run queries with `await db.execute(...)`.

- Integration points & secrets:
  - `DATABASE_URL` is used to configure `create_async_engine` in `app/db/base.py`; do not commit secrets—use `.env` and `.env.example`.
  - Docker Compose defines the `db` service and sets `DATABASE_URL` for the `web` service in `docker-compose.yml`.

- When in doubt:
  - Check `app/main.py` and `app/api/v1/routes.py` to learn the routing pattern.
  - Follow established async SQLAlchemy usage in `app/db/base.py` (use `AsyncSessionLocal` and `get_session`).
    - Prefer async-first patterns and libraries: use SQLAlchemy 2.x async features and `asyncpg` for Postgres, and prefer async third-party libraries when available.

Please tell me if you want a PR template, initial Alembic setup, or a basic pytest for the health endpoint added next.
