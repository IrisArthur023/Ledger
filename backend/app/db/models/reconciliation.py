import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True)
    external_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNMATCHED")  # MATCHED, UNMATCHED, RESOLVED, REJECTED
    mismatch_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="reconciliation_records")
    transaction: Mapped[Optional["Transaction"]] = relationship(back_populates="reconciliation_records")
    resolved_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[resolved_by_user_id])
