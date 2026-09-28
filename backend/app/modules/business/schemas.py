import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class BusinessCreate(BaseModel):
    name: str
    base_currency: str = "USD"
    settings: Optional[Dict[str, Any]] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    base_currency: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class BusinessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_currency: str
    settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MemberInvite(BaseModel):
    user_id: uuid.UUID
    role: str = "EMPLOYEE"  # OWNER, MANAGER, EMPLOYEE


class BusinessMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime
    user_phone: Optional[str] = None
    user_name: Optional[str] = None
