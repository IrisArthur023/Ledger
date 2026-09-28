import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, DateTime, JSON, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String as StringType
from backend.app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    memberships: Mapped[List["BusinessMembership"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    accounts: Mapped[List["Account"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    categories: Mapped[List["Category"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    reconciliation_records: Mapped[List["ReconciliationRecord"]] = relationship(back_populates="business", cascade="all, delete-orphan")


class BusinessMembership(Base):
    __tablename__ = "business_memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="EMPLOYEE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "user_id", name="uq_business_user_membership"),
    )

    # Relationships
    business: Mapped["Business"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")
