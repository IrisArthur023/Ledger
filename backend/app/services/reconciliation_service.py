import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import Transaction, ReconciliationRecord, Account
from backend.app.services.audit_service import AuditService


class ReconciliationService:
    @classmethod
    async def match_external_transaction(
        cls,
        db: AsyncSession,
        business_id: uuid.UUID,
        provider: str,
        external_transaction_id: str,
        amount: Decimal,
        currency: str,
        transaction_timestamp: datetime,
        direction: str,  # INCOME or EXPENSE
        account_id: Optional[uuid.UUID] = None,
        timestamp_tolerance_seconds: int = settings.RECONCILIATION_TIMESTAMP_TOLERANCE_SECONDS,
        amount_tolerance: float = settings.RECONCILIATION_AMOUNT_TOLERANCE,
    ) -> ReconciliationRecord:
        # Build query to search for matching ledger transaction
        tx_ts = transaction_timestamp
        if tx_ts.tzinfo is None:
            tx_ts = tx_ts.replace(tzinfo=timezone.utc)
        time_min = tx_ts - timedelta(seconds=timestamp_tolerance_seconds)
        time_max = tx_ts + timedelta(seconds=timestamp_tolerance_seconds)
        amt_tolerance_dec = Decimal(str(amount_tolerance))

        query = select(Transaction).where(
            Transaction.business_id == business_id,
            Transaction.type == direction.upper(),
            Transaction.original_currency == currency.upper(),
            Transaction.status == "ACTIVE",
            Transaction.transaction_timestamp >= time_min,
            Transaction.transaction_timestamp <= time_max,
        )

        if account_id:
            query = query.where(Transaction.account_id == account_id)

        result = await db.execute(query)
        candidates = result.scalars().all()

        matched_tx: Optional[Transaction] = None
        for cand in candidates:
            diff = abs(cand.original_amount - Decimal(str(amount)))
            if diff <= amt_tolerance_dec:
                matched_tx = cand
                break

        if matched_tx:
            rec_record = ReconciliationRecord(
                id=uuid.uuid4(),
                business_id=business_id,
                transaction_id=matched_tx.id,
                external_transaction_id=external_transaction_id,
                provider=provider.lower(),
                status="MATCHED",
                mismatch_reason=None,
            )
        else:
            rec_record = ReconciliationRecord(
                id=uuid.uuid4(),
                business_id=business_id,
                transaction_id=None,
                external_transaction_id=external_transaction_id,
                provider=provider.lower(),
                status="UNMATCHED",
                mismatch_reason=f"No matching active {direction} transaction found within ±{timestamp_tolerance_seconds//3600}h and tolerance {amount_tolerance}",
            )

        db.add(rec_record)
        return rec_record

    @classmethod
    async def resolve_record(
        cls,
        db: AsyncSession,
        record: ReconciliationRecord,
        actor_user_id: uuid.UUID,
        resolution_status: str,  # RESOLVED or REJECTED
        notes: Optional[str] = None,
        linked_transaction_id: Optional[uuid.UUID] = None,
    ) -> ReconciliationRecord:
        before_val = {"status": record.status, "transaction_id": str(record.transaction_id) if record.transaction_id else None}
        
        record.status = resolution_status.upper()
        record.resolved_by_user_id = actor_user_id
        record.resolved_at = datetime.now(timezone.utc)
        if linked_transaction_id:
            record.transaction_id = linked_transaction_id
        if notes:
            record.mismatch_reason = f"{record.mismatch_reason or ''} | Resolution Note: {notes}"

        after_val = {"status": record.status, "transaction_id": str(record.transaction_id) if record.transaction_id else None, "notes": notes}

        await AuditService.log_action(
            db=db,
            business_id=record.business_id,
            actor_user_id=actor_user_id,
            entity_type="ReconciliationRecord",
            entity_id=record.id,
            action="RESOLVE",
            before_values=before_val,
            after_values=after_val,
        )

        return record
