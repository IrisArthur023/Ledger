import uuid
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
from backend.app.db.models import ReconciliationRecord
from backend.app.services.reconciliation_service import ReconciliationService
from backend.app.modules.reconciliation.schemas import (
    MatchExternalTransactionRequest,
    ResolveReconciliationRequest,
    ReconciliationRecordResponse,
)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


@router.post("/match", response_model=dict, status_code=status.HTTP_201_CREATED)
async def match_external_transaction(
    body: MatchExternalTransactionRequest,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    record = await ReconciliationService.match_external_transaction(
        db=db,
        business_id=ctx.business.id,
        provider=body.provider,
        external_transaction_id=body.external_transaction_id,
        amount=body.amount,
        currency=body.currency,
        transaction_timestamp=body.transaction_timestamp,
        direction=body.direction,
        account_id=body.account_id,
    )
    await db.commit()
    await db.refresh(record)

    return {
        "data": ReconciliationRecordResponse.model_validate(record),
        "message": f"External transaction reconciliation attempt completed with status: {record.status}",
    }


@router.get("/records", response_model=dict)
async def list_reconciliation_records(
    status_filter: Optional[str] = Query(None, alias="status"),
    provider_filter: Optional[str] = Query(None, alias="provider"),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ReconciliationRecord).where(ReconciliationRecord.business_id == ctx.business.id)
    if status_filter:
        stmt = stmt.where(ReconciliationRecord.status == status_filter.upper())
    if provider_filter:
        stmt = stmt.where(ReconciliationRecord.provider == provider_filter.lower())

    stmt = stmt.order_by(ReconciliationRecord.created_at.desc())
    result = await db.execute(stmt)
    records = result.scalars().all()

    return {
        "data": [ReconciliationRecordResponse.model_validate(r) for r in records],
        "message": f"Retrieved {len(records)} reconciliation records",
    }


@router.post("/records/{record_id}/resolve", response_model=dict)
async def resolve_reconciliation_record(
    record_id: uuid.UUID,
    body: ResolveReconciliationRequest,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ReconciliationRecord).where(
        ReconciliationRecord.id == record_id,
        ReconciliationRecord.business_id == ctx.business.id,
    )
    record = (await db.execute(stmt)).scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECORD_NOT_FOUND", "message": "Reconciliation record not found"},
        )

    updated_record = await ReconciliationService.resolve_record(
        db=db,
        record=record,
        actor_user_id=ctx.user.id,
        resolution_status=body.resolution_status,
        notes=body.notes,
        linked_transaction_id=body.linked_transaction_id,
    )
    await db.commit()
    await db.refresh(updated_record)

    return {
        "data": ReconciliationRecordResponse.model_validate(updated_record),
        "message": "Reconciliation record status resolved successfully",
    }
