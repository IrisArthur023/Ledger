import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    category_id: uuid.UUID
    type: str  # INCOME, EXPENSE
    original_amount: Decimal
    original_currency: str
    description: str = ""
    transaction_timestamp: Optional[datetime] = None
    manual_exchange_rate: Optional[Decimal] = None
    sync_metadata: Optional[Dict[str, Any]] = None


class TransactionUpdate(BaseModel):
    account_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    type: Optional[str] = None
    original_amount: Optional[Decimal] = None
    original_currency: Optional[str] = None
    description: Optional[str] = None
    transaction_timestamp: Optional[datetime] = None
    manual_exchange_rate: Optional[Decimal] = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    account_id: uuid.UUID
    category_id: uuid.UUID
    created_by_user_id: uuid.UUID
    type: str
    original_amount: Decimal
    original_currency: str
    base_currency_amount: Decimal
    exchange_rate_snapshot_id: Optional[uuid.UUID]
    transaction_timestamp: datetime
    description: str
    status: str
    sync_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SuggestCategoryRequest(BaseModel):
    description: str
    amount: Decimal
    currency: str = "USD"
