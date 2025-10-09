"""
Database integration tests.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@pytest.mark.asyncio
async def test_user_model_crud(test_session: AsyncSession):
    """Test basic CRUD operations on the User model."""
    # Create
    user = User(name="Test User")
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)

    assert user.id is not None
    assert user.name == "Test User"

    # Read
    result = await test_session.execute(select(User).where(User.name == "Test User"))
    fetched_user = result.scalar_one_or_none()

    assert fetched_user is not None
    assert fetched_user.id == user.id
    assert fetched_user.name == "Test User"

    # Update
    fetched_user.name = "Updated User"
    await test_session.commit()
    await test_session.refresh(fetched_user)

    assert fetched_user.name == "Updated User"

    # Delete
    await test_session.delete(fetched_user)
    await test_session.commit()

    result = await test_session.execute(select(User).where(User.id == user.id))
    deleted_user = result.scalar_one_or_none()

    assert deleted_user is None
