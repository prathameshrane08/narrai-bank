"""Database schema.

Every table carries `tenant_id` (the bank), and every query filters on it together
with the customer. Keeping the tenant on each row, not just on the customer, makes
isolation checkable per table and lets Postgres enforce it later with row-level security.

Amounts are stored as positive NUMERIC(12, 2); the category `Income` marks money in.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(12, 2)


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "external_ref", name="uq_customers_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    # The bank's own identifier for this customer (never a name or account number).
    external_ref: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    iban_masked: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    # SHA-256 of the full IBAN, to match statements to accounts without storing the IBAN itself.
    iban_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_tenant_account_date", "tenant_id", "account_id", "booked_on"),
        Index("uq_transactions_account_fingerprint", "account_id", "fingerprint", unique=True),
        CheckConstraint("direction IN ('in', 'out')", name="ck_transactions_direction"),
    )

    # BIGINT in Postgres; SQLite only auto-increments INTEGER primary keys.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    booked_on: Mapped[date] = mapped_column(Date)
    merchant: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    # "in" or "out": refunds and transfers from own accounts are money in without being income.
    direction: Mapped[str] = mapped_column(String(3), default="out", server_default="out")
    # Remittance information as the bank sent it (kept for re-categorisation and support).
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Identifies an imported row so re-importing the same statement never duplicates it.
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_budgets_amount_positive"),)

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    category: Mapped[str] = mapped_column(String(60), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ApiKey(Base):
    """A bank's server-to-server credential. Only the hash is stored; the key is shown once."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
