"""Database tables: packages, clients and payments.

Money is stored in cents (integers) so amounts never pick up floating-point rounding errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitpay.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def new_reference() -> str:
    return uuid.uuid4().hex


class Billing(StrEnum):
    MONTHLY = "monthly"
    ONCE_OFF = "once_off"


class PaymentMethod(StrEnum):
    PAYFAST = "payfast"
    EFT = "eft"
    CASH = "cash"
    CARD = "card"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int]
    billing: Mapped[Billing] = mapped_column(Enum(Billing, native_enum=False, length=20))
    # How many months one payment covers: 1 for monthly plans, e.g. 3 for a 12-week program.
    months: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), default=None)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id"), default=None)
    start_date: Mapped[date]
    notes: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    package: Mapped[Package | None] = relationship(lazy="joined")
    payments: Mapped[list[Payment]] = relationship(
        back_populates="client", order_by="Payment.id", lazy="selectin"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id"), default=None)
    amount_cents: Mapped[int]
    months: Mapped[int] = mapped_column(default=1)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, native_enum=False, length=20))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=20), default=PaymentStatus.PENDING
    )
    # Our own reference, sent to PayFast as m_payment_id.
    reference: Mapped[str] = mapped_column(String(64), unique=True, default=new_reference)
    # PayFast's id for the payment, set when its notification arrives.
    pf_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True, default=None)
    paid_on: Mapped[date | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    client: Mapped[Client] = relationship(back_populates="payments")
