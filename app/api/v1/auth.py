from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import os
import json
import httpx
import jwt
import bcrypt
from typing import Optional
import glob

from ...db.base import get_session
from ...db.models import User

router = APIRouter()

# Load client secret JSON. Prefer explicit env var, otherwise find first matching file.
CLIENT_SECRET_PATH = os.environ.get("GOOGLE_CLIENT_SECRET_PATH")
if not CLIENT_SECRET_PATH:
    candidates = glob.glob("client_secret_*.json")
    CLIENT_SECRET_PATH = candidates[0] if candidates else None

if not CLIENT_SECRET_PATH:
    raise RuntimeError("No Google client secret file found. Set GOOGLE_CLIENT_SECRET_PATH or place a client_secret_*.json file in the backend folder.")

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret")

with open(CLIENT_SECRET_PATH, "r") as f:
    _client_json = json.load(f)

_client_info = _client_json.get("installed") or _client_json.get("web") or _client_json.get("android") or {}
CLIENT_ID = _client_info.get("client_id")
CLIENT_SECRET = _client_info.get("client_secret")
AUTH_URI = _client_info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")
TOKEN_URI = _client_info.get("token_uri", "https://oauth2.googleapis.com/token")

if not CLIENT_ID:
    raise RuntimeError("Missing Google client_id in client secret file")


class GoogleTokenVerifyRequest(BaseModel):
    id_token: str


class TokenRequest(BaseModel):
    code: str
    redirect_uri: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, hash_: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hash_.encode())


def create_app_token(user_id: str, email: str, name: Optional[str] = None) -> str:
    """Create application JWT token."""
    payload = {
        "sub": user_id,
        "email": email,
        "name": name or email,
    }
    return jwt.encode(payload, APP_SECRET, algorithm="HS256")


@router.post("/register")
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_session)):
    """Register a new user with email and password."""
    # Check if user exists
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    password_hash = hash_password(payload.password)
    new_user = User(
        email=payload.email,
        password_hash=password_hash,
        password_algo="bcrypt",
        display_name=payload.name or payload.email,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Generate token
    app_token = create_app_token(str(new_user.id), new_user.email, new_user.display_name)
    
    return {
        "access_token": app_token,
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "name": new_user.display_name,
        }
    }


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_session)):
    """Login with email and password."""
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Generate token
    app_token = create_app_token(str(user.id), user.email, user.display_name)
    
    return {
        "access_token": app_token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.display_name,
        }
    }


@router.get("/google/url")
async def google_auth_url(redirect_uri: Optional[str] = None, scope: Optional[str] = None):
    """Return a Google OAuth consent URL. The client should pass the redirect_uri that will receive the code.
    Example redirect_uri: com.example.net:/oauth2redirect
    """
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri parameter is required")

    scope = scope or "openid email profile"
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "access_type": "offline",
        "prompt": "select_account consent",
    }
    from urllib.parse import urlencode

    url = f"{AUTH_URI}?{urlencode(params)}"
    return JSONResponse({"url": url})


@router.post("/google/token")
async def exchange_code_for_token(payload: TokenRequest):
    """Exchange an authorization code for tokens and return an application JWT.

    Request body: { "code": "...", "redirect_uri": "<registered-redirect-uri>" }
    """
    code = payload.code
    redirect_uri = payload.redirect_uri

    if not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Server is not configured with client_secret for confidential exchange.")

    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URI, data=data, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail={"error": "token_exchange_failed", "body": resp.text})
        token_data = resp.json()

        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")

        # Optionally fetch userinfo
        userinfo = {}
        if access_token:
            try:
                ui_resp = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {access_token}"})
                if ui_resp.status_code == 200:
                    userinfo = ui_resp.json()
            except Exception:
                userinfo = {}

    # Build an application JWT
    payload = {
        "sub": userinfo.get("sub") or userinfo.get("id") or userinfo.get("email"),
        "email": userinfo.get("email"),
        "name": userinfo.get("name"),
    }
    app_token = jwt.encode(payload, APP_SECRET, algorithm="HS256")

    return {"access_token": app_token, "user": payload}


@router.post("/google/verify")
async def verify_google_token(payload: GoogleTokenVerifyRequest, db: AsyncSession = Depends(get_session)):
    """Verify a Google ID token from the mobile/web app and create an application session.
    
    The Flutter app uses the google_sign_in package which provides the ID token.
    This endpoint verifies the token with Google and returns an application JWT.
    
    Request body: { "id_token": "<Google ID token>" }
    """
    id_token = payload.id_token

    # Verify the ID token with Google's tokeninfo endpoint
    # In production, consider using google-auth library for proper verification
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=401, 
                detail={"error": "invalid_token", "body": resp.text}
            )
        
        token_info = resp.json()
        
        # Verify the token is for this app
        if token_info.get("aud") not in [CLIENT_ID]:
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_audience", "expected": CLIENT_ID}
            )
        
        # Extract user information from token
        google_sub = token_info.get("sub")
        email = token_info.get("email")
        name = token_info.get("name")
        picture = token_info.get("picture")
        email_verified = token_info.get("email_verified")
        
        if not google_sub or not email:
            raise HTTPException(status_code=400, detail="Invalid token: missing sub or email")

    # Look up or create user in database
    stmt = select(User).where(User.google_id == google_sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Create new user from Google account
        user = User(
            email=email,
            google_id=google_sub,
            display_name=name or email,
            profile_picture_url=picture,
            email_verified=email_verified == "true" or email_verified is True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Update user info if changed
        if user.display_name != name and name:
            user.display_name = name
        if user.profile_picture_url != picture and picture:
            user.profile_picture_url = picture
        await db.commit()

    # Generate application token
    app_token = create_app_token(str(user.id), user.email, user.display_name)

    return {
        "access_token": app_token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "picture": user.profile_picture_url,
        }
    }
