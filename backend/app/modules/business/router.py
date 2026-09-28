import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.dependencies import (
    get_current_user,
    get_current_business,
    CurrentBusinessContext,
    require_owner,
)
from backend.app.core.permissions import Role
from backend.app.db.database import get_db
from backend.app.db.models import Business, BusinessMembership, User, Category
from backend.app.modules.business.schemas import (
    BusinessCreate,
    BusinessUpdate,
    BusinessResponse,
    MemberInvite,
    BusinessMemberResponse,
)

router = APIRouter(prefix="/businesses", tags=["Businesses"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_business(
    body: BusinessCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = Business(
        id=uuid.uuid4(),
        name=body.name,
        base_currency=body.base_currency.upper(),
        settings=body.settings or {},
    )
    db.add(business)

    membership = BusinessMembership(
        id=uuid.uuid4(),
        business_id=business.id,
        user_id=user.id,
        role=Role.OWNER,
    )
    db.add(membership)

    # Seed default categories for new business
    default_categories = [
        Category(id=uuid.uuid4(), business_id=business.id, name="Sales Income", type="INCOME", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Consulting & Services", type="INCOME", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Rent & Facility", type="EXPENSE", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Payroll & Wages", type="EXPENSE", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Utilities & Subscriptions", type="EXPENSE", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Travel & Transport", type="EXPENSE", is_default=True),
        Category(id=uuid.uuid4(), business_id=business.id, name="Office Supplies", type="EXPENSE", is_default=True),
    ]
    db.add_all(default_categories)

    await db.commit()
    await db.refresh(business)

    return {
        "data": BusinessResponse.model_validate(business),
        "message": "Business entity created successfully",
    }


@router.get("", response_model=dict)
async def list_user_businesses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Business)
        .join(BusinessMembership, BusinessMembership.business_id == Business.id)
        .where(BusinessMembership.user_id == user.id)
    )
    result = await db.execute(stmt)
    businesses = result.scalars().all()

    return {
        "data": [BusinessResponse.model_validate(b) for b in businesses],
        "message": f"Retrieved {len(businesses)} businesses",
    }


@router.get("/{business_id}", response_model=dict)
async def get_business_detail(
    ctx: CurrentBusinessContext = Depends(get_current_business),
):
    return {
        "data": {
            "business": BusinessResponse.model_validate(ctx.business),
            "user_role": ctx.role,
        },
        "message": "Business detail fetched successfully",
    }


@router.put("/{business_id}", response_model=dict)
async def update_business(
    body: BusinessUpdate,
    ctx: CurrentBusinessContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    business = ctx.business
    if body.name is not None:
        business.name = body.name
    if body.base_currency is not None:
        business.base_currency = body.base_currency.upper()
    if body.settings is not None:
        business.settings = body.settings

    await db.commit()
    await db.refresh(business)

    return {
        "data": BusinessResponse.model_validate(business),
        "message": "Business updated successfully",
    }


@router.post("/{business_id}/members", response_model=dict)
async def add_business_member(
    body: MemberInvite,
    ctx: CurrentBusinessContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    # Verify user exists
    stmt = select(User).where(User.id == body.user_id)
    user_res = await db.execute(stmt)
    target_user = user_res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "Target user does not exist"},
        )

    # Check if existing member
    mem_stmt = select(BusinessMembership).where(
        BusinessMembership.business_id == ctx.business.id,
        BusinessMembership.user_id == body.user_id,
    )
    existing_mem = (await db.execute(mem_stmt)).scalar_one_or_none()
    if existing_mem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MEMBER_ALREADY_EXISTS", "message": "User is already a member of this business"},
        )

    membership = BusinessMembership(
        id=uuid.uuid4(),
        business_id=ctx.business.id,
        user_id=body.user_id,
        role=body.role.upper(),
    )
    db.add(membership)
    await db.commit()

    return {
        "data": {
            "id": str(membership.id),
            "business_id": str(membership.business_id),
            "user_id": str(membership.user_id),
            "role": membership.role,
            "user_phone": target_user.phone,
            "user_name": target_user.name,
        },
        "message": "Member added to business successfully",
    }


@router.get("/{business_id}/members", response_model=dict)
async def list_business_members(
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(BusinessMembership, User)
        .join(User, BusinessMembership.user_id == User.id)
        .where(BusinessMembership.business_id == ctx.business.id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    members = [
        {
            "id": str(mem.id),
            "business_id": str(mem.business_id),
            "user_id": str(mem.user_id),
            "role": mem.role,
            "user_phone": u.phone,
            "user_name": u.name,
            "created_at": mem.created_at,
        }
        for mem, u in rows
    ]

    return {
        "data": members,
        "message": f"Retrieved {len(members)} team members",
    }
