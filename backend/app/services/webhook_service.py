import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable, Tuple, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import WebhookEvent


class WebhookService:
    @classmethod
    async def process_webhook(
        cls,
        db: AsyncSession,
        provider: str,
        provider_event_id: str,
        event_type: str,
        payload: Dict[str, Any],
        handler: Optional[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = None,
    ) -> Tuple[WebhookEvent, bool]:
        """
        Processes webhook idempotently.
        Returns (WebhookEvent, was_already_processed: bool)
        """
        prov = provider.lower()
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider == prov,
            WebhookEvent.provider_event_id == provider_event_id,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if existing.status == "PROCESSED":
                return existing, True  # Idempotent skip
            # If FAILED or PENDING, retry processing

        event = existing or WebhookEvent(
            id=uuid.uuid4(),
            provider=prov,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
        )
        if not existing:
            db.add(event)
            await db.flush()

        if handler:
            try:
                await handler(payload)
                event.status = "PROCESSED"
                event.error_message = None
                event.processed_at = datetime.now(timezone.utc)
            except Exception as exc:
                event.status = "FAILED"
                event.error_message = str(exc)[:1000]
                # Event retained for inspection/retry
                raise exc

        else:
            event.status = "PROCESSED"
            event.processed_at = datetime.now(timezone.utc)

        return event, False
