"""
Auth router — GitHub and GitLab OAuth2 + JWT issuance.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: Optional[str]
    github_id: Optional[str]
    gitlab_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise exc
    except JWTError:
        raise exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise exc
    return user


# ---------------------------------------------------------------------------
# GitHub OAuth
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAIL_URL = "https://api.github.com/user/emails"


@router.get("/github", summary="Redirect to GitHub OAuth")
async def github_login():
    params = (
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&scope=read:user,user:email"
    )
    return RedirectResponse(GITHUB_AUTHORIZE_URL + params)


@router.get("/github/callback", response_model=TokenOut, summary="GitHub OAuth callback")
async def github_callback(code: str, db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub OAuth failed: could not obtain access token",
            )

        gh_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        # Fetch user profile
        user_resp = await client.get(GITHUB_USER_URL, headers=gh_headers)
        gh_user = user_resp.json()

        # Fetch primary email if not public
        email = gh_user.get("email")
        if not email:
            emails_resp = await client.get(GITHUB_EMAIL_URL, headers=gh_headers)
            emails = emails_resp.json()
            primary = next(
                (e for e in emails if e.get("primary") and e.get("verified")), None
            )
            email = primary["email"] if primary else None

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not retrieve a verified email from GitHub",
        )

    github_id = str(gh_user["id"])
    name = gh_user.get("name") or gh_user.get("login", "GitHub User")
    avatar_url = gh_user.get("avatar_url")

    # Upsert user
    user = await _upsert_oauth_user(
        db=db,
        email=email,
        name=name,
        avatar_url=avatar_url,
        github_id=github_id,
        gitlab_id=None,
    )

    jwt_token = create_access_token(user.id)
    redirect_url = f"{settings.FRONTEND_URL}/login?token={jwt_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# GitLab OAuth
# ---------------------------------------------------------------------------

@router.get("/gitlab", summary="Redirect to GitLab OAuth")
async def gitlab_login():
    base = settings.GITLAB_BASE_URL.rstrip("/")
    params = (
        f"?client_id={settings.GITLAB_CLIENT_ID}"
        f"&redirect_uri={settings.GITLAB_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=read_user"
    )
    return RedirectResponse(f"{base}/oauth/authorize{params}")


@router.get("/gitlab/callback", response_model=TokenOut, summary="GitLab OAuth callback")
async def gitlab_callback(code: str, db: AsyncSession = Depends(get_db)):
    base = settings.GITLAB_BASE_URL.rstrip("/")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{base}/oauth/token",
            data={
                "client_id": settings.GITLAB_CLIENT_ID,
                "client_secret": settings.GITLAB_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GITLAB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitLab OAuth failed: could not obtain access token",
            )

        gl_headers = {"Authorization": f"Bearer {access_token}"}
        user_resp = await client.get(f"{base}/api/v4/user", headers=gl_headers)
        gl_user = user_resp.json()

    email = gl_user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not retrieve email from GitLab",
        )

    gitlab_id = str(gl_user["id"])
    name = gl_user.get("name") or gl_user.get("username", "GitLab User")
    avatar_url = gl_user.get("avatar_url")

    user = await _upsert_oauth_user(
        db=db,
        email=email,
        name=name,
        avatar_url=avatar_url,
        github_id=None,
        gitlab_id=gitlab_id,
    )

    jwt_token = create_access_token(user.id)
    redirect_url = f"{settings.FRONTEND_URL}/login?token={jwt_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# Dev-only token endpoint (DEBUG mode only)
# ---------------------------------------------------------------------------

@router.post("/dev-token", response_model=TokenOut, summary="[DEV] Create test user and return JWT")
async def dev_token(db: AsyncSession = Depends(get_db)):
    """
    Creates (or returns) a test user and issues a JWT.
    Only available when DEBUG=true. Do NOT expose in production.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    user = await _upsert_oauth_user(
        db=db,
        email="dev@autoverif.local",
        name="Dev User",
        avatar_url=None,
        github_id="dev-test-user-001",
        gitlab_id=None,
    )
    jwt_token = create_access_token(user.id)
    return TokenOut(access_token=jwt_token, user=UserOut.model_validate(user))


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut, summary="Get current user")
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _upsert_oauth_user(
    db: AsyncSession,
    email: str,
    name: str,
    avatar_url: Optional[str],
    github_id: Optional[str],
    gitlab_id: Optional[str],
) -> User:
    """Find existing user by OAuth ID or email, or create a new one."""
    user: Optional[User] = None

    # Try to find by provider ID first
    if github_id:
        res = await db.execute(select(User).where(User.github_id == github_id))
        user = res.scalar_one_or_none()
    if not user and gitlab_id:
        res = await db.execute(select(User).where(User.gitlab_id == gitlab_id))
        user = res.scalar_one_or_none()

    # Fall back to email lookup
    if not user:
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()

    if user:
        # Update potentially stale fields
        user.name = name
        user.avatar_url = avatar_url
        if github_id:
            user.github_id = github_id
        if gitlab_id:
            user.gitlab_id = gitlab_id
        await db.commit()
        await db.refresh(user)
    else:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            avatar_url=avatar_url,
            github_id=github_id,
            gitlab_id=gitlab_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
