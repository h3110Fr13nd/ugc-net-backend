# ugc-net-backend

This repository contains the backend for the UGC Net project.

Work for Issue #2: scaffold a FastAPI-based project structure with API versioning, SQLAlchemy, Postgres and Docker support.

Quickstart (development):

1. Copy `.env.example` to `.env` and adjust settings if needed.
2. Create a venv and install dependencies using `uv` (preferred):

	- Remove any existing venv: `rm -rf .venv`
	- Install `uv` if needed: `python -m pip install --user uv`
	- Create and activate venv (prefer Python 3.14):

	  ```bash
	  uv venv create .venv --python 3.14
	  source .venv/bin/activate
	  python -m pip install --upgrade pip
	  ```

	- Add runtime deps: `uv add fastapi uvicorn[standard] sqlalchemy asyncpg`
	- Add dev deps: `uv add -d pytest pytest-asyncio httpx alembic black pytest-cov`

	- Alternatively, install from requirements: `uv pip install -r requirements.txt` and `uv pip install -r dev-requirements.txt`.

3. Start services with Docker Compose (recommended for parity):

	docker-compose up --build

4. The API will be available at http://localhost:8000/api/v1/health

Database migrations (Alembic)

1. Install alembic (already added to requirements):

	```bash
	uv add -d alembic
	# or
	uv pip install alembic
	```

2. Create an autogenered revision and apply it:

	```bash
	alembic revision --autogenerate -m "initial"
	alembic upgrade head
	```


