from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_session
from app.db.models import User, Role, UserRole
import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple

_bearer = HTTPBearer(auto_error=False)

# Refresh token lifetime (seconds)
REFRESH_TOKEN_SECONDS = int(os.environ.get("REFRESH_TOKEN_SECONDS", 60 * 60 * 24 * 30))  # 30 days

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token() -> Tuple[str, datetime]:
    token = secrets.token_urlsafe(64)
    expires = datetime.now(tz=timezone.utc) + timedelta(seconds=REFRESH_TOKEN_SECONDS)
    return token, expires


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer), db: AsyncSession = Depends(get_session)) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, APP_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, sub)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(role_name: str):
    """Return a dependency that ensures the current user has the given role name.

    Usage: current_user = Depends(require_role("author"))
    """

    async def _require(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_session)):
        # Check roles for the user
        try:
            stmt = select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == current_user.id, Role.name == role_name)
            res = await db.execute(stmt)
            role = res.scalar_one_or_none()
            if not role:
                raise HTTPException(status_code=403, detail="insufficient_role")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="insufficient_role")
        return current_user

    return _require
