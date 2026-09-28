from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/{provider}", response_model=dict)
async def receive_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_event_id: str = Header(None, alias="X-Event-ID"),
):
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "Payload must be valid JSON"},
        )

    # Extract event ID from headers or payload
    event_id = x_event_id or payload.get("id") or payload.get("event_id") or str(payload.get("data", {}).get("id"))
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_EVENT_ID", "message": "Provider event ID not found in payload or header"},
        )

    event_type = payload.get("event") or payload.get("type") or "generic.payment"

    webhook_event, already_processed = await WebhookService.process_webhook(
        db=db,
        provider=provider,
        provider_event_id=str(event_id),
        event_type=str(event_type),
        payload=payload,
    )

    await db.commit()

    return {
        "data": {
            "event_id": str(webhook_event.id),
            "provider": webhook_event.provider,
            "provider_event_id": webhook_event.provider_event_id,
            "status": webhook_event.status,
            "already_processed": already_processed,
        },
        "message": "Webhook processed idempotently",
    }
