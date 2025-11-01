"""
Pytest configuration and fixtures for testing.

This harness will prefer a real Postgres for tests. If the environment
variable `TEST_DATABASE_URL` is set (e.g., in CI or local dev), it will use
that. Otherwise it will spin up an ephemeral Postgres via testcontainers.

Using Postgres in tests ensures UUID, JSONB and ARRAY types behave like
production and removes the need for SQLite-specific hacks.
"""

import os
import pytest
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import sqlalchemy as sa
from testcontainers.postgres import PostgresContainer

from app.main import app
from app.db.models import Base
from app.db.base import get_session

# Prefer env var (CI or developer override)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def postgres_container():
    """Provide an asyncpg-compatible DB URL for tests.

    If TEST_DATABASE_URL env var is present, use that. Otherwise spin up a
    Postgres container for the duration of the test session.
    """
    if TEST_DATABASE_URL:
        # Ensure asyncpg dialect prefix
        url = TEST_DATABASE_URL
        if url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        yield url
    else:
        with PostgresContainer("postgres:15") as pg:
            raw = pg.get_connection_url()
            # Normalize to asyncpg driver URL (testcontainers may return a sync URL)
            if raw.startswith("postgresql+psycopg2://"):
                url = raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            elif raw.startswith("postgresql://"):
                url = raw.replace("postgresql://", "postgresql+asyncpg://")
            else:
                url = raw
            yield url


@pytest.fixture(scope="session")
def postgres_db(postgres_container):
    """Session-scoped fixture that returns the DB URL and ensures pgcrypto exists.

    Important: keep this synchronous so we don't create asyncpg connections in a
    session-scoped fixture (that would be bound to a different event loop than
    per-test asyncio loops and cause "Future attached to a different loop"
    errors). The async engine will be created per-test in `test_session`.
    """
    db_url = postgres_container

    # Ensure pgcrypto extension (gen_random_uuid) exists using a sync engine
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    sync_engine = sa.create_engine(sync_url)
    with sync_engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

    # Persist sync_url so other fixtures (reset between tests) can run DDL using
    # a separate sync connection to avoid asyncpg 'another operation in progress' errors.
    os.environ["TEST_SYNC_DATABASE_URL"] = sync_url

    # Create initial schema once using the sync engine.
    with sync_engine.begin() as conn:
        Base.metadata.create_all(bind=conn)

    yield db_url

    # Drop schema at session end
    with sync_engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)



@pytest.fixture
async def test_session(postgres_db) -> AsyncGenerator[AsyncSession, None]:
    """Create a transactional test database session.

    This fixture creates an async engine, opens a connection and starts an
    outer transaction and a nested (savepoint) transaction. Tests run inside
    that nested context and when the test finishes the outer transaction is
    rolled back, providing fast isolation without recreating the schema.
    """
    db_url = postgres_db
    engine = create_async_engine(db_url, echo=False)

    # Use a single connection per-test so the transaction lifecycle is simple
    conn = await engine.connect()
    # begin an outer transaction
    trans = await conn.begin()
    # nested transaction to allow session.commit() inside tests without
    # committing the outer transaction
    await conn.begin_nested()

    async_session = sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            yield session
    finally:
        # Rollback the outer transaction to undo all test changes.
        try:
            await trans.rollback()
        finally:
            await conn.close()
            await engine.dispose()


@pytest.fixture
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""

    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    # Create an admin user and role for tests and set a default Authorization header
    from app.db.models import User, Role, UserRole
    from app.core.security import APP_SECRET
    import jwt
    import datetime

    # create admin and author roles and user in DB
    admin_role = Role(name="admin")
    author_role = Role(name="author")
    test_session.add_all([admin_role, author_role])
    await test_session.flush()

    admin_user = User(email="test-admin@example.com", password_hash="", display_name="Admin")
    test_session.add(admin_user)
    await test_session.flush()

    # assign both admin and author roles to the test user
    user_roles = [
        UserRole(user_id=admin_user.id, role_id=admin_role.id, assigned_at=datetime.datetime.now(datetime.timezone.utc)),
        UserRole(user_id=admin_user.id, role_id=author_role.id, assigned_at=datetime.datetime.now(datetime.timezone.utc)),
    ]
    test_session.add_all(user_roles)
    await test_session.commit()

    # create JWT token for admin
    token = jwt.encode({"sub": str(admin_user.id)}, APP_SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}

    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# Per-test transactional isolation is used; no DDL reset is necessary.

