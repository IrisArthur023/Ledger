import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth0 import (
    build_authorization_url,
    build_logout_url,
    exchange_code_for_tokens,
    get_current_user,
)
from backend.app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.modules.auth.schemas import (
    PhoneOTPRequest,
    PhoneOTPVerify,
    PasswordLoginRequest,
    TokenRefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─── Auth0 Redirect Flow ────────────────────────────────────────────────────

@router.get("/login", summary="Redirect to Auth0 Universal Login")
async def auth0_login(screen_hint: str | None = Query(default=None)):
    """
    Initiates the Auth0 redirect flow.  The browser is sent to Auth0's
    Universal Login page; after the user authenticates, Auth0 redirects
    back to ``/auth/callback``.

    Pass ``?screen_hint=signup`` to open the registration screen directly.
    """
    state = secrets.token_urlsafe(32)
    url = build_authorization_url(state=state, screen_hint=screen_hint)
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", summary="Auth0 OAuth2 callback")
async def auth0_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Auth0 redirects the browser here after a successful login.
    Exchanges the authorization code for tokens, provisions or updates
    the local User record, and returns app-level JWT credentials.
    """
    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Auth0 token exchange failed: {exc}",
        )

    id_token: str = token_data.get("id_token", "")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth0 did not return an id_token.",
        )

    # Decode the id_token without signature verification — the exchange
    # itself proved authenticity; we only need the claims here.
    from jose import jwt as jose_jwt
    claims: dict = jose_jwt.get_unverified_claims(id_token)

    auth0_sub: str = claims.get("sub", "")
    email: str = claims.get("email", "")
    name: str = claims.get("name") or claims.get("nickname") or email.split("@")[0]

    # Upsert user
    stmt = select(User).where(User.auth0_sub == auth0_sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=uuid.uuid4(),
            auth0_sub=auth0_sub,
            email=email,
            name=name or "Auth0 User",
            is_active=True,
        )
        db.add(user)
    else:
        # Keep profile in sync with Auth0
        user.email = email
        user.name = name or user.name

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "auth0_sub": user.auth0_sub,
            },
        },
        "message": "Auth0 login successful",
    }


@router.get("/logout", summary="Redirect to Auth0 logout")
async def auth0_logout():
    """
    Redirects the browser to Auth0's logout endpoint, which clears the
    Auth0 SSO session and then sends the user to ``APP_BASE_URL``.
    """
    url = build_logout_url()
    return RedirectResponse(url=url, status_code=302)


@router.get("/me", summary="Get currently authenticated user")
async def me(current_user: User = Depends(get_current_user)):
    """
    Returns the profile of the currently authenticated user.
    Requires a valid ``Authorization: Bearer <token>`` header.
    """
    return {
        "data": {
            "id": str(current_user.id),
            "email": current_user.email,
            "name": current_user.name,
            "phone": current_user.phone,
            "auth0_sub": current_user.auth0_sub,
            "is_active": current_user.is_active,
        },
        "message": "User profile retrieved",
    }


# ─── Legacy Phone / OTP Flow (unchanged) ─────────────────────────────────────



@router.post("/request-otp")
async def request_otp(body: PhoneOTPRequest):
    # In production, triggers Firebase / Twilio OTP dispatch
    return {
        "data": {"phone": body.phone, "otp_sent": True, "simulation_code": "123456"},
        "message": "OTP verification code sent successfully",
    }


@router.post("/verify-otp", response_model=dict)
async def verify_otp(body: PhoneOTPVerify, db: AsyncSession = Depends(get_db)):
    # Accepts 123456 as valid OTP for test/demo simulation
    if body.otp != "123456":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_OTP", "message": "The provided OTP verification code is invalid"},
        )

    stmt = select(User).where(User.phone == body.phone)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=uuid.uuid4(),
            phone=body.phone,
            name=f"User {body.phone[-4:]}",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {"id": str(user.id), "phone": user.phone, "name": user.name},
        },
        "message": "OTP verified and authentication successful",
    }


@router.post("/login", response_model=dict)
async def login(body: PasswordLoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.phone == body.phone)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid phone number or password"},
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {"id": str(user.id), "phone": user.phone, "name": user.name},
        },
        "message": "Login successful",
    }


@router.post("/refresh", response_model=dict)
async def refresh_token(body: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_REFRESH_TOKEN", "message": "Invalid or expired refresh token"},
        )

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid token subject format"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User inactive or not found"},
        )

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return {
        "data": {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user": {"id": str(user.id), "phone": user.phone, "name": user.name},
        },
        "message": "Token refreshed successfully",
    }
