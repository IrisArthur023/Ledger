import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, DateTime, Numeric, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # INCOME, EXPENSE
    original_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    base_currency_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    exchange_rate_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("exchange_rate_snapshots.id", ondelete="SET NULL"), nullable=True)

    transaction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, VOIDED
    sync_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="transactions")
    account: Mapped["Account"] = relationship(back_populates="transactions")
    category: Mapped["Category"] = relationship(back_populates="transactions")
    created_by_user: Mapped["User"] = relationship(back_populates="transactions")
    exchange_rate_snapshot: Mapped[Optional["ExchangeRateSnapshot"]] = relationship(foreign_keys=[exchange_rate_snapshot_id])
    reconciliation_records: Mapped[List["ReconciliationRecord"]] = relationship(back_populates="transaction")
