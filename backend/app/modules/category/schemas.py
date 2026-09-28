import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    type: str  # INCOME, EXPENSE


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    type: str
    is_default: bool
    created_at: datetime
