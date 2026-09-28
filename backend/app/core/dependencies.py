import uuid
from typing import Optional, Callable
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Header, Query, Path, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.security import decode_token
from backend.app.core.permissions import Permission, Role, has_permission
from backend.app.db.database import get_db
from backend.app.db.models import User, Business, BusinessMembership

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)


@dataclass
class CurrentBusinessContext:
    business: Business
    membership: BusinessMembership
    user: User
    role: str


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Authentication token missing or invalid"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    token_type = payload.get("type")
    sub = payload.get("sub")
    if not payload or token_type != "access" or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Could not validate authentication credentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid token subject format"},
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or inactive"},
        )
    return user


async def get_current_business(
    x_business_id: Optional[str] = Header(None, alias="X-Business-ID"),
    business_id_query: Optional[str] = Query(None, alias="business_id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CurrentBusinessContext:
    target_business_id_str = x_business_id or business_id_query
    if not target_business_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BUSINESS_ID_MISSING", "message": "Business ID header (X-Business-ID) or query parameter required"},
        )
    try:
        business_id = uuid.UUID(target_business_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_BUSINESS_ID", "message": "Invalid business ID UUID format"},
        )
    
    # Query membership and business
    stmt = (
        select(BusinessMembership, Business)
        .join(Business, BusinessMembership.business_id == Business.id)
        .where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user.id
        )
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "TENANT_ACCESS_DENIED", "message": "User is not a member of the specified business"},
        )
    
    membership, business = row
    return CurrentBusinessContext(
        business=business,
        membership=membership,
        user=user,
        role=membership.role
    )


def require_permission(permission: Permission) -> Callable:
    async def permission_checker(
        ctx: CurrentBusinessContext = Depends(get_current_business)
    ) -> CurrentBusinessContext:
        if not has_permission(ctx.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": f"Action requires permission: {permission.value}"},
            )
        return ctx
    return permission_checker


def require_owner(
    ctx: CurrentBusinessContext = Depends(get_current_business)
) -> CurrentBusinessContext:
    if ctx.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "OWNER_REQUIRED", "message": "Action requires OWNER role"},
        )
    return ctx


def require_manager(
    ctx: CurrentBusinessContext = Depends(get_current_business)
) -> CurrentBusinessContext:
    if ctx.role not in (Role.OWNER, Role.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MANAGER_REQUIRED", "message": "Action requires MANAGER or OWNER role"},
        )
    return ctx


def require_employee(
    ctx: CurrentBusinessContext = Depends(get_current_business)
) -> CurrentBusinessContext:
    return ctx
