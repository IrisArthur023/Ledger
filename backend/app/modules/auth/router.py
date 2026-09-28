import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
