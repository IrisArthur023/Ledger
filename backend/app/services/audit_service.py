import uuid
from typing import Any, Optional, Dict
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import AuditLog


def sanitize_for_json(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            cleaned[key] = str(value)
        elif isinstance(value, (datetime, date)):
            cleaned[key] = value.isoformat()
        elif isinstance(value, uuid.UUID):
            cleaned[key] = str(value)
        elif isinstance(value, dict):
            cleaned[key] = sanitize_for_json(value)
        elif isinstance(value, list):
            cleaned[key] = [
                str(item) if isinstance(item, (Decimal, uuid.UUID, datetime, date)) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


class AuditService:
    @staticmethod
    async def log_action(
        db: AsyncSession,
        business_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        before_values: Optional[Dict[str, Any]] = None,
        after_values: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            business_id=business_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action.upper(),
            before_values=sanitize_for_json(before_values),
            after_values=sanitize_for_json(after_values),
        )
        db.add(audit_entry)
        # Session commit will occur with parent operation
        return audit_entry
