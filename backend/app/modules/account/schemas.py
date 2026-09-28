import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    name: str
    type: str  # BANK, CASH, MOBILE_MONEY, CREDIT
    currency: str
    opening_balance: Decimal = Decimal("0.0000")


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    currency: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    is_archived: Optional[bool] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    type: str
    currency: str
    opening_balance: Decimal
    current_balance: Decimal
    is_archived: bool
    created_at: datetime
    updated_at: datetime
