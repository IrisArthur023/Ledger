import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeRateSnapshot(Base):
    __tablename__ = "exchange_rate_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL", use_alter=True, name="fk_fx_transaction_id"), nullable=True, index=True)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="MANUAL")  # MANUAL, PROVIDER, HISTORICAL
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
