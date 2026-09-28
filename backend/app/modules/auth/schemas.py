from pydantic import BaseModel, Field
from typing import Optional


class PhoneOTPRequest(BaseModel):
    phone: str = Field(..., json_schema_extra={"example": "+1234567890"})


class PhoneOTPVerify(BaseModel):
    phone: str = Field(..., json_schema_extra={"example": "+1234567890"})
    otp: str = Field(..., json_schema_extra={"example": "123456"})


class PasswordLoginRequest(BaseModel):
    phone: str = Field(..., json_schema_extra={"example": "+1234567890"})
    password: str = Field(..., json_schema_extra={"example": "Secret123!"})


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
