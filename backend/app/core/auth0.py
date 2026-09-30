"""
backend/app/core/auth0.py
─────────────────────────
Auth0 integration for FastAPI.

Two usage patterns are supported:

1. **Token-based (API / SPA)**
   Clients obtain a JWT from Auth0 directly (e.g. via the Auth0 SPA SDK or
   the `/auth/login` redirect flow) and then pass it in the
   `Authorization: Bearer <token>` header on every protected request.
   The `get_current_user` FastAPI dependency validates that token.

2. **Server-side redirect flow (browser)**
   `/auth/login`    → redirect to Auth0 Universal Login
   `/auth/callback` → exchange code for tokens, upsert user, issue our own JWT
   `/auth/logout`   → clear session and redirect to Auth0 logout
"""

import json
import uuid
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.database import get_db
from backend.app.db.models import User

# ---------------------------------------------------------------------------
# JWKS cache — fetched once per process lifetime (LRU with maxsize=1)
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch and cache Auth0's JSON Web Key Set."""
    url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_token(token: str) -> dict[str, Any]:
    """
    Validate an Auth0-issued JWT.

    Returns the decoded payload on success; raises HTTP 401 on any failure.
    """
    if not settings.AUTH0_DOMAIN or not settings.AUTH0_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth0 is not configured on this server.",
        )

    try:
        jwks = _get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        # Find the matching key by kid
        rsa_key: dict[str, str] = {}
        for key in jwks.get("keys", []):
            if key.get("kid") == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n":   key["n"],
                    "e":   key["e"],
                }
                break

        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find matching public key.",
            )

        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.AUTH0_CLIENT_ID,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
        return payload

    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependency — protect any route with Auth0 JWT
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that:
    1. Extracts the Bearer token from the Authorization header.
    2. Validates it against Auth0's JWKS.
    3. Looks up (or creates) the matching local User row.
    4. Returns the User ORM object.

    Usage::

        @router.get("/me")
        async def me(user: User = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_token(credentials.credentials)
    auth0_sub: str = payload.get("sub", "")

    # Upsert: find existing user by auth0_sub, or create a new one
    stmt = select(User).where(User.auth0_sub == auth0_sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # First-time login — provision a local user from the token claims
        email: str = payload.get("email", "")
        name: str = payload.get("name") or payload.get("nickname") or email.split("@")[0]
        user = User(
            id=uuid.uuid4(),
            auth0_sub=auth0_sub,
            email=email,
            name=name or "Auth0 User",
            phone="",          # phone is not provided by Auth0; left blank
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


# ---------------------------------------------------------------------------
# OAuth helper — used by the /auth/* redirect routes
# ---------------------------------------------------------------------------

def build_authorization_url(state: str, screen_hint: str | None = None) -> str:
    """Build the Auth0 /authorize redirect URL."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": settings.AUTH0_CLIENT_ID or "",
        "redirect_uri": f"{settings.APP_BASE_URL}/api/v1/auth/callback",
        "scope": "openid profile email",
        "state": state,
    }
    if screen_hint:
        params["screen_hint"] = screen_hint
    return f"https://{settings.AUTH0_DOMAIN}/authorize?" + urlencode(params)


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange the authorization code for an id_token + access_token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{settings.AUTH0_DOMAIN}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": settings.AUTH0_CLIENT_ID,
                "client_secret": settings.AUTH0_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{settings.APP_BASE_URL}/api/v1/auth/callback",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def build_logout_url(return_to: str | None = None) -> str:
    """Build the Auth0 logout URL."""
    params: dict[str, str] = {
        "client_id": settings.AUTH0_CLIENT_ID or "",
        "returnTo": return_to or settings.APP_BASE_URL,
    }
    return f"https://{settings.AUTH0_DOMAIN}/v2/logout?" + urlencode(params)
