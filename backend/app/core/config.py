import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "LLC Ledger"
    API_V1_STR: str = "/api/v1"
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./llc_ledger.db"
    
    # Security
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    
    # Auth0
    AUTH0_DOMAIN: Optional[str] = None
    AUTH0_CLIENT_ID: Optional[str] = None
    AUTH0_CLIENT_SECRET: Optional[str] = None
    AUTH0_SECRET: Optional[str] = None       # 64-char hex used to sign session cookies
    APP_BASE_URL: str = "http://localhost:8000"

    # Integration & Third Party Secrets (from environment variables)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    PAYSTACK_SECRET_KEY: Optional[str] = None
    MOMO_PRIMARY_KEY: Optional[str] = None
    FX_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Financial Configuration Defaults
    DEFAULT_BASE_CURRENCY: str = "USD"
    RECONCILIATION_TIMESTAMP_TOLERANCE_SECONDS: int = 7200  # 2 hours
    RECONCILIATION_AMOUNT_TOLERANCE: float = 0.05  # $0.05 or 5%
    AI_CONFIDENCE_THRESHOLD: float = 0.70
    FORECAST_MINIMUM_HISTORY_DAYS: int = 30
    ANOMALY_SENSITIVITY: float = 2.5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
