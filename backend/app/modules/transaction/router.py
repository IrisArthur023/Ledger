import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.dependencies import (
    get_current_business,
    CurrentBusinessContext,
    require_employee,
    require_manager,
)
from backend.app.db.database import get_db
from backend.app.db.models import Transaction, Account, Category
from backend.app.services.balance_service import BalanceService
from backend.app.services.fx_service import FXService
from backend.app.services.audit_service import AuditService
from backend.app.services.ai_classification_service import AIClassificationService
from backend.app.modules.transaction.schemas import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    SuggestCategoryRequest,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    body: TransactionCreate,
    ctx: CurrentBusinessContext = Depends(require_employee),
    db: AsyncSession = Depends(get_db),
):
    # Verify target account exists and belongs to business
    acc_stmt = select(Account).where(
        Account.id == body.account_id,
        Account.business_id == ctx.business.id,
    )
    account = (await db.execute(acc_stmt)).scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ACCOUNT_NOT_FOUND", "message": "Target account not found"},
        )

    # Verify category exists and belongs to business
    cat_stmt = select(Category).where(
        Category.id == body.category_id,
        Category.business_id == ctx.business.id,
    )
    category = (await db.execute(cat_stmt)).scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "Target category not found"},
        )

    # Convert currency rate to business base currency
    rate, fx_snapshot = await FXService.get_or_create_rate_snapshot(
        db=db,
        base_currency=ctx.business.base_currency,
        original_currency=body.original_currency,
        manual_rate=body.manual_exchange_rate,
    )

    base_amount = FXService.calculate_base_amount(body.original_amount, rate)
    tx_timestamp = body.transaction_timestamp or datetime.now(timezone.utc)

    tx = Transaction(
        id=uuid.uuid4(),
        business_id=ctx.business.id,
        account_id=account.id,
        category_id=category.id,
        created_by_user_id=ctx.user.id,
        type=body.type.upper(),
        original_amount=body.original_amount,
        original_currency=body.original_currency.upper(),
        base_currency_amount=base_amount,
        exchange_rate_snapshot_id=fx_snapshot.id if fx_snapshot else None,
        transaction_timestamp=tx_timestamp,
        description=body.description,
        status="ACTIVE",
        sync_metadata=body.sync_metadata or {},
    )
    db.add(tx)

    if fx_snapshot:
        fx_snapshot.transaction_id = tx.id

    # Update account current balance
    await BalanceService.update_balance_on_create(db, account, tx)

    # Audit log
    await AuditService.log_action(
        db=db,
        business_id=ctx.business.id,
        actor_user_id=ctx.user.id,
        entity_type="Transaction",
        entity_id=tx.id,
        action="CREATE",
        after_values={
            "account_id": str(account.id),
            "amount": str(tx.original_amount),
            "type": tx.type,
            "description": tx.description,
        },
    )

    await db.commit()
    await db.refresh(tx)

    return {
        "data": TransactionResponse.model_validate(tx),
        "message": "Transaction recorded successfully",
    }


@router.get("", response_model=dict)
async def list_transactions(
    account_id: Optional[uuid.UUID] = Query(None),
    category_id: Optional[uuid.UUID] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).where(Transaction.business_id == ctx.business.id)

    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
    if type_filter:
        stmt = stmt.where(Transaction.type == type_filter.upper())
    if status_filter:
        stmt = stmt.where(Transaction.status == status_filter.upper())

    stmt = stmt.order_by(Transaction.transaction_timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    transactions = result.scalars().all()

    return {
        "data": [TransactionResponse.model_validate(tx) for tx in transactions],
        "message": f"Retrieved {len(transactions)} transactions",
        "pagination": {"limit": limit, "offset": offset},
    }


@router.get("/{transaction_id}", response_model=dict)
async def get_transaction(
    transaction_id: uuid.UUID,
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.business_id == ctx.business.id,
    )
    tx = (await db.execute(stmt)).scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found"},
        )

    return {
        "data": TransactionResponse.model_validate(tx),
        "message": "Transaction retrieved successfully",
    }


@router.put("/{transaction_id}", response_model=dict)
async def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.business_id == ctx.business.id,
    )
    tx = (await db.execute(stmt)).scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found"},
        )

    if tx.status == "VOIDED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_EDIT_VOIDED", "message": "Cannot edit a voided transaction"},
        )

    # Fetch associated account
    acc_stmt = select(Account).where(Account.id == tx.account_id)
    account = (await db.execute(acc_stmt)).scalar_one()

    # Capture before values for audit & balance reversal
    old_type = tx.type
    old_amount = tx.original_amount
    old_currency = tx.original_currency
    old_base_amount = tx.base_currency_amount
    old_status = tx.status

    # Apply updates
    if body.account_id is not None:
        tx.account_id = body.account_id
    if body.category_id is not None:
        tx.category_id = body.category_id
    if body.type is not None:
        tx.type = body.type.upper()
    if body.description is not None:
        tx.description = body.description
    if body.transaction_timestamp is not None:
        tx.transaction_timestamp = body.transaction_timestamp
    if body.original_amount is not None:
        tx.original_amount = body.original_amount
    if body.original_currency is not None:
        tx.original_currency = body.original_currency.upper()

    # Recalculate FX rate if amount/currency changed
    if body.original_amount is not None or body.original_currency is not None or body.manual_exchange_rate is not None:
        rate, fx_snapshot = await FXService.get_or_create_rate_snapshot(
            db=db,
            base_currency=ctx.business.base_currency,
            original_currency=tx.original_currency,
            manual_rate=body.manual_exchange_rate,
            transaction_id=tx.id,
        )
        tx.base_currency_amount = FXService.calculate_base_amount(tx.original_amount, rate)
        if fx_snapshot:
            tx.exchange_rate_snapshot_id = fx_snapshot.id

    # Recalculate balance
    await BalanceService.update_balance_on_edit(
        db, account, old_type, old_amount, old_currency, old_base_amount, old_status, tx
    )

    # Audit log
    await AuditService.log_action(
        db=db,
        business_id=ctx.business.id,
        actor_user_id=ctx.user.id,
        entity_type="Transaction",
        entity_id=tx.id,
        action="UPDATE",
        before_values={"amount": str(old_amount), "type": old_type},
        after_values={"amount": str(tx.original_amount), "type": tx.type},
    )

    await db.commit()
    await db.refresh(tx)

    return {
        "data": TransactionResponse.model_validate(tx),
        "message": "Transaction updated successfully",
    }


@router.post("/{transaction_id}/void", response_model=dict)
async def void_transaction(
    transaction_id: uuid.UUID,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.business_id == ctx.business.id,
    )
    tx = (await db.execute(stmt)).scalar_one_or_none()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found"},
        )

    if tx.status == "VOIDED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ALREADY_VOIDED", "message": "Transaction is already voided"},
        )

    acc_stmt = select(Account).where(Account.id == tx.account_id)
    account = (await db.execute(acc_stmt)).scalar_one()

    before_val = {"status": tx.status}
    await BalanceService.update_balance_on_void(db, account, tx)

    await AuditService.log_action(
        db=db,
        business_id=ctx.business.id,
        actor_user_id=ctx.user.id,
        entity_type="Transaction",
        entity_id=tx.id,
        action="VOID",
        before_values=before_val,
        after_values={"status": tx.status},
    )

    await db.commit()

    return {
        "data": TransactionResponse.model_validate(tx),
        "message": "Transaction voided successfully and account balance updated",
    }


@router.post("/suggest-category", response_model=dict)
async def suggest_category(
    body: SuggestCategoryRequest,
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    cat_stmt = select(Category).where(Category.business_id == ctx.business.id)
    categories = (await db.execute(cat_stmt)).scalars().all()

    cats_dict = [{"id": str(c.id), "name": c.name, "type": c.type} for c in categories]

    suggestion = await AIClassificationService.suggest_category(
        description=body.description,
        amount=body.amount,
        currency=body.currency,
        available_categories=cats_dict,
    )

    return {
        "data": suggestion,
        "message": "Category suggestion generated successfully",
    }
