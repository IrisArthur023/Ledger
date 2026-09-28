import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from backend.app.core.dependencies import (
    get_current_business,
    CurrentBusinessContext,
    require_manager,
)
from backend.app.db.database import get_db
from backend.app.db.models import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    actor_user_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before_values: Optional[dict]
    after_values: Optional[dict]
    timestamp: datetime


@router.get("", response_model=dict)
async def list_audit_logs(
    entity_type: Optional[str] = Query(None),
    actor_user_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).where(AuditLog.business_id == ctx.business.id)

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return {
        "data": [AuditLogResponse.model_validate(log) for log in logs],
        "message": f"Retrieved {len(logs)} audit log entries",
        "pagination": {"limit": limit, "offset": offset},
    }
