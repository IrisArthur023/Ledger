import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class MatchExternalTransactionRequest(BaseModel):
    provider: str  # paystack, momo, bank_csv
    external_transaction_id: str
    amount: Decimal
    currency: str
    transaction_timestamp: datetime
    direction: str  # INCOME, EXPENSE
    account_id: Optional[uuid.UUID] = None


class ResolveReconciliationRequest(BaseModel):
    resolution_status: str  # RESOLVED, REJECTED
    linked_transaction_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None


class ReconciliationRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    transaction_id: Optional[uuid.UUID]
    external_transaction_id: str
    provider: str
    status: str
    mismatch_reason: Optional[str]
    resolved_by_user_id: Optional[uuid.UUID]
    resolved_at: Optional[datetime]
    created_at: datetime
