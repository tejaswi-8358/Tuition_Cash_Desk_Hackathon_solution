"""SQLAlchemy 2.0 ORM models. Money columns are integer paise."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    """Naive UTC timestamp (avoids the deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)  # digits only, with country code
    default_delay_days: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(500), default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    invoices: Mapped[List[Invoice]] = relationship(back_populates="customer")
    recurring_fees: Mapped[List[RecurringFee]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    issue_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    # allowed: draft, sent, part_paid, paid, void
    status: Mapped[str] = mapped_column(String(20), default="sent")
    notes: Mapped[str] = mapped_column(String(500), default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    customer: Mapped[Customer] = relationship(back_populates="invoices")
    items: Mapped[List[InvoiceItem]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.id",
    )
    payments: Mapped[List[Payment]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_minor: Mapped[int] = mapped_column(Integer)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    amount_minor: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(10), default="bank")  # cash, bank, upi, other
    note: Mapped[str] = mapped_column(String(200), default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    message: Mapped[str] = mapped_column(Text)


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payee: Mapped[str] = mapped_column(String(120))
    # rent, salary, materials, transport, utilities, other
    category: Mapped[str] = mapped_column(String(20))
    amount_minor: Mapped[int] = mapped_column(Integer)
    # monthly, weekly, one_off
    recurrence: Mapped[str] = mapped_column(String(10))
    due_day: Mapped[Optional[int]] = mapped_column(Integer)  # 1-31, for monthly
    next_due_date: Mapped[Optional[date]] = mapped_column(Date)  # for weekly / one_off
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)


class RecurringFee(Base):
    __tablename__ = "recurring_fees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE")
    )
    amount_minor: Mapped[int] = mapped_column(Integer)
    cadence: Mapped[str] = mapped_column(String(10))  # monthly, weekly
    due_day: Mapped[Optional[int]] = mapped_column(Integer)  # 1-31, for monthly
    next_due_date: Mapped[Optional[date]] = mapped_column(Date)  # for weekly
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(back_populates="recurring_fees")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    overrides_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
