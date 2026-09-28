import uuid
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.dependencies import (
    get_current_business,
    CurrentBusinessContext,
    require_manager,
)
from backend.app.db.database import get_db
from backend.app.db.models import Account
from backend.app.services.balance_service import BalanceService
from backend.app.modules.account.schemas import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    account = Account(
        id=uuid.uuid4(),
        business_id=ctx.business.id,
        name=body.name,
        type=body.type.upper(),
        currency=body.currency.upper(),
        opening_balance=body.opening_balance,
        current_balance=body.opening_balance,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return {
        "data": AccountResponse.model_validate(account),
        "message": "Account created successfully",
    }


@router.get("", response_model=dict)
async def list_accounts(
    include_archived: bool = Query(False),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account).where(Account.business_id == ctx.business.id)
    if not include_archived:
        stmt = stmt.where(Account.is_archived == False)

    stmt = stmt.order_by(Account.name.asc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return {
        "data": [AccountResponse.model_validate(acc) for acc in accounts],
        "message": f"Retrieved {len(accounts)} accounts",
    }


@router.get("/{account_id}", response_model=dict)
async def get_account_detail(
    account_id: uuid.UUID,
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account).where(
        Account.id == account_id,
        Account.business_id == ctx.business.id,
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": "Account not found for this business"},
        )

    return {
        "data": AccountResponse.model_validate(account),
        "message": "Account details retrieved successfully",
    }


@router.put("/{account_id}", response_model=dict)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account).where(
        Account.id == account_id,
        Account.business_id == ctx.business.id,
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": "Account not found for this business"},
        )

    if body.name is not None:
        account.name = body.name
    if body.type is not None:
        account.type = body.type.upper()
    if body.currency is not None:
        account.currency = body.currency.upper()
    if body.is_archived is not None:
        account.is_archived = body.is_archived
    if body.opening_balance is not None:
        diff = body.opening_balance - account.opening_balance
        account.opening_balance = body.opening_balance
        account.current_balance += diff

    await db.commit()
    await db.refresh(account)

    return {
        "data": AccountResponse.model_validate(account),
        "message": "Account updated successfully",
    }


@router.delete("/{account_id}", response_model=dict)
async def archive_account(
    account_id: uuid.UUID,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account).where(
        Account.id == account_id,
        Account.business_id == ctx.business.id,
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": "Account not found for this business"},
        )

    account.is_archived = True
    await db.commit()

    return {
        "data": {"id": str(account.id), "is_archived": True},
        "message": "Account archived successfully",
    }
