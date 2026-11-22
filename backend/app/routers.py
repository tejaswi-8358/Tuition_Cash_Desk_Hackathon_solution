"""REST API routes for the Tuition Cash Desk backend.

Money is always integer minor units (paise) in both directions. Business rules live in
app.services; this module only validates input, loads rows, calls the services and shapes
responses. Python 3.9 compatible (typing generics only).
"""

import re
import urllib.parse
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Bill,
    Customer,
    Invoice,
    Payment,
    RecurringFee,
    Reminder,
    Setting,
)
from app.money import format_minor
from app.services import (
    aging_summary,
    bucket_for_invoice,
    build_overdue_list,
    create_invoice,
    days_overdue,
    derive_status,
    invoice_balance_minor,
    invoice_paid_minor,
    invoice_total_minor,
    payment_summary,
    recalculate_status,
    record_payment,
)

router = APIRouter(prefix="/api")

PHONE_RE = re.compile(r"[0-9]{8,15}")
INVOICE_STATUSES = ("draft", "sent", "part_paid", "paid", "void")
SETTING_DEFAULTS = {
    "business_name": "Sunrise Home Tuition",
    "currency_symbol": "₹",
    "opening_cash_minor": "0",
    "safe_balance_minor": "0",
}
INT_SETTINGS = ("opening_cash_minor", "safe_balance_minor")

PaymentMethod = Literal["cash", "bank", "upi", "other"]
BillCategory = Literal["rent", "salary", "materials", "transport", "utilities", "other"]
BillRecurrence = Literal["monthly", "weekly", "one_off"]
FeeCadence = Literal["monthly", "weekly"]


# ---------------------------------------------------------------- helpers

def normalise_phone(raw: str) -> str:
    """Strip spaces, '+' and '-'; the rest must be 8-15 ASCII digits."""
    cleaned = re.sub(r"[ +\-]", "", raw.strip())
    if not PHONE_RE.fullmatch(cleaned):
        raise ValueError("Phone must contain 8 to 15 digits (spaces, + and - are ignored)")
    return cleaned


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    stripped = value.strip()
    if not stripped:
        raise ValueError("Name cannot be blank")
    return stripped


def _whatsapp_url(phone: str, message: str) -> str:
    return "https://wa.me/%s?text=%s" % (phone, urllib.parse.quote(message))


def _as_int(value: Optional[str], default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _load_settings(db: Session) -> Dict[str, str]:
    values = dict(SETTING_DEFAULTS)
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def _settings_out(values: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(values)
    for key in INT_SETTINGS:
        out[key] = _as_int(values.get(key), 0)
    return out


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _figures(invoice: Invoice, today: date) -> Dict[str, Any]:
    total = invoice_total_minor(invoice)
    paid = invoice_paid_minor(invoice)
    balance = invoice_balance_minor(invoice)
    return {
        "total_minor": total,
        "paid_minor": paid,
        "balance_minor": balance,
        "status": derive_status(total, paid, invoice.due_date, today, invoice.status),
        "days_overdue": days_overdue(balance, invoice.due_date, today),
    }


def _invoice_summary(invoice: Invoice, today: date) -> "InvoiceSummaryOut":
    customer = invoice.customer
    return InvoiceSummaryOut(
        id=invoice.id,
        number=invoice.number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        customer_name=customer.name if customer is not None else "",
        customer_phone=customer.phone if customer is not None else "",
        **_figures(invoice, today)
    )


def _payment_out(payment: Payment) -> "PaymentOut":
    return PaymentOut(
        id=payment.id,
        amount_minor=payment.amount_minor,
        paid_on=payment.paid_on,
        method=payment.method,
        note=payment.note or "",
    )


def _invoice_detail(db: Session, invoice: Invoice, today: date) -> "InvoiceDetailOut":
    summary = _invoice_summary(invoice, today)
    phone = summary.customer_phone
    reminders = (
        db.query(Reminder)
        .filter(Reminder.invoice_id == invoice.id)
        .order_by(Reminder.sent_at.desc(), Reminder.id.desc())
        .all()
    )
    items = [
        InvoiceItemOut(
            id=item.id,
            description=item.description,
            quantity=item.quantity,
            unit_price_minor=item.unit_price_minor,
            line_total_minor=int(item.quantity) * int(item.unit_price_minor),
        )
        for item in invoice.items
    ]
    payments = sorted(invoice.payments, key=lambda p: (p.paid_on, p.id))
    return InvoiceDetailOut(
        **summary.model_dump(),
        notes=invoice.notes or "",
        bucket=bucket_for_invoice(summary.balance_minor, summary.days_overdue),
        items=items,
        payments=[_payment_out(p) for p in payments],
        reminders=[
            ReminderOut(
                id=r.id,
                sent_at=r.sent_at,
                message=r.message,
                channel=r.channel,
                whatsapp_url=_whatsapp_url(phone, r.message),
            )
            for r in reminders
        ],
    )


# ---------------------------------------------------------------- customer schemas

class CustomerOut(BaseModel):
    id: int
    name: str
    phone: str
    default_delay_days: int
    notes: str
    outstanding_minor: int
    overdue_minor: int


class InvoiceSummaryOut(BaseModel):
    id: int
    number: str
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    status: str
    total_minor: int
    paid_minor: int
    balance_minor: int
    days_overdue: int
    customer_name: str = ""
    customer_phone: str = ""


class CustomerDetailOut(CustomerOut):
    invoices: List[InvoiceSummaryOut]


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=1, max_length=40)
    default_delay_days: int = Field(0, ge=0, le=180)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return _clean_name(value)  # type: ignore[return-value]

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return normalise_phone(value)


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, min_length=1, max_length=40)
    default_delay_days: Optional[int] = Field(None, ge=0, le=180)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: Optional[str]) -> Optional[str]:
        return _clean_name(value)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalise_phone(value)


# ---------------------------------------------------------------- invoice schemas

class InvoiceItemIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(..., ge=1)
    unit_price_minor: int = Field(..., ge=0)


class InvoiceCreate(BaseModel):
    customer_id: int
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    items: List[InvoiceItemIn] = Field(..., min_length=1, max_length=50)
    notes: Optional[str] = Field(None, max_length=500)
    status: Literal["sent", "draft"] = "sent"


class InvoiceStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=20)


class InvoiceItemOut(BaseModel):
    id: int
    description: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int


class PaymentOut(BaseModel):
    id: int
    amount_minor: int
    paid_on: date
    method: str
    note: str


class ReminderOut(BaseModel):
    id: int
    sent_at: datetime
    message: str
    channel: str
    whatsapp_url: Optional[str] = None


class InvoiceDetailOut(InvoiceSummaryOut):
    notes: str
    bucket: str
    items: List[InvoiceItemOut]
    payments: List[PaymentOut]
    reminders: List[ReminderOut]


class PaymentCreate(BaseModel):
    amount_minor: int = Field(..., gt=0)
    paid_on: Optional[date] = None
    method: PaymentMethod = "upi"
    note: Optional[str] = Field(None, max_length=200)


class PaymentCreatedOut(BaseModel):
    payment: PaymentOut
    invoice: InvoiceSummaryOut


class ReminderCreate(BaseModel):
    message: Optional[str] = Field(None, max_length=1000)


# ---------------------------------------------------------------- bill / fee / dashboard / settings schemas

class BillCreate(BaseModel):
    payee: str = Field(..., min_length=1, max_length=120)
    category: BillCategory
    amount_minor: int = Field(..., gt=0)
    recurrence: BillRecurrence
    due_day: Optional[int] = Field(None, ge=1, le=31)
    next_due_date: Optional[date] = None

    @model_validator(mode="after")
    def _check_schedule(self) -> "BillCreate":
        if self.recurrence == "monthly" and self.due_day is None:
            raise ValueError("due_day is required for monthly bills")
        if self.recurrence in ("weekly", "one_off") and self.next_due_date is None:
            raise ValueError("next_due_date is required for weekly and one-off bills")
        return self


class BillUpdate(BaseModel):
    active: Optional[bool] = None
    amount_minor: Optional[int] = Field(None, gt=0)


class BillOut(BaseModel):
    id: int
    payee: str
    category: str
    amount_minor: int
    recurrence: str
    due_day: Optional[int] = None
    next_due_date: Optional[date] = None
    active: bool


class RecurringFeeCreate(BaseModel):
    customer_id: int
    amount_minor: int = Field(..., gt=0)
    cadence: FeeCadence
    due_day: Optional[int] = Field(None, ge=1, le=31)
    next_due_date: Optional[date] = None

    @model_validator(mode="after")
    def _check_schedule(self) -> "RecurringFeeCreate":
        if self.cadence == "monthly" and self.due_day is None:
            raise ValueError("due_day is required for monthly fees")
        if self.cadence == "weekly" and self.next_due_date is None:
            raise ValueError("next_due_date is required for weekly fees")
        return self


class RecurringFeeOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    amount_minor: int
    cadence: str
    due_day: Optional[int] = None
    next_due_date: Optional[date] = None
    active: bool


class OverdueRowOut(BaseModel):
    invoice_id: int
    invoice_number: str
    customer_id: int
    customer_name: str
    customer_phone: str
    balance_minor: int
    due_date: Optional[date] = None
    days_overdue: int
    bucket: str
    total_minor: int
    paid_minor: int


class DashboardOut(BaseModel):
    today: date
    business_name: str
    currency_symbol: str
    total_outstanding_minor: int
    total_overdue_minor: int
    overdue_count: int
    aging: Dict[str, Any]
    payments: Dict[str, int]
    overdue: List[OverdueRowOut]
    customer_count: int
    invoice_count: int


class SettingsUpdate(BaseModel):
    business_name: Optional[str] = Field(None, min_length=1, max_length=120)
    currency_symbol: Optional[str] = Field(None, min_length=1, max_length=5)
    opening_cash_minor: Optional[int] = Field(None, ge=0)
    safe_balance_minor: Optional[int] = Field(None, ge=0)


# ---------------------------------------------------------------- customers

def _customer_out(customer: Customer, today: date) -> CustomerOut:
    figures = aging_summary(list(customer.invoices), today)
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        default_delay_days=customer.default_delay_days or 0,
        notes=customer.notes or "",
        outstanding_minor=int(figures["total_outstanding_minor"]),
        overdue_minor=int(figures["total_overdue_minor"]),
    )


@router.get("/customers", response_model=List[CustomerOut])
def list_customers(db: Session = Depends(get_db)) -> List[CustomerOut]:
    today = date.today()
    customers = db.query(Customer).order_by(Customer.name, Customer.id).all()
    return [_customer_out(c, today) for c in customers]


@router.post("/customers", status_code=201, response_model=CustomerOut)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> CustomerOut:
    today = date.today()
    if db.query(Customer.id).filter(Customer.phone == payload.phone).first() is not None:
        raise HTTPException(status_code=409, detail="A customer with this phone already exists")
    customer = Customer(
        name=payload.name,
        phone=payload.phone,
        default_delay_days=payload.default_delay_days,
        notes=payload.notes or "",
        is_sample=False,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _customer_out(customer, today)


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerDetailOut:
    today = date.today()
    customer = _get_customer_or_404(db, customer_id)
    invoices = sorted(customer.invoices, key=lambda i: (i.issue_date or date.min, i.id), reverse=True)
    base = _customer_out(customer, today)
    return CustomerDetailOut(
        **base.model_dump(),
        invoices=[_invoice_summary(inv, today) for inv in invoices],
    )


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
) -> CustomerOut:
    today = date.today()
    customer = _get_customer_or_404(db, customer_id)
    changes = payload.model_dump(exclude_unset=True)

    for key in ("name", "phone", "default_delay_days"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=422, detail="%s cannot be null" % key)

    if "phone" in changes:
        clash = (
            db.query(Customer.id)
            .filter(Customer.phone == changes["phone"], Customer.id != customer.id)
            .first()
        )
        if clash is not None:
            raise HTTPException(status_code=409, detail="A customer with this phone already exists")
    if "name" in changes:
        customer.name = changes["name"]
    if "phone" in changes:
        customer.phone = changes["phone"]
    if "default_delay_days" in changes:
        customer.default_delay_days = changes["default_delay_days"]
    if "notes" in changes:
        customer.notes = changes["notes"] or ""

    db.commit()
    db.refresh(customer)
    return _customer_out(customer, today)


# ---------------------------------------------------------------- invoices

@router.get("/invoices", response_model=List[InvoiceSummaryOut])
def list_invoices(
    status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> List[InvoiceSummaryOut]:
    today = date.today()
    if status is not None and status not in INVOICE_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown invoice status: %s" % status)
    query = db.query(Invoice)
    if customer_id is not None:
        query = query.filter(Invoice.customer_id == customer_id)
    invoices = query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()
    rows = [_invoice_summary(inv, today) for inv in invoices]
    if status is not None:
        rows = [row for row in rows if row.status == status]
    return rows


@router.post("/invoices", status_code=201, response_model=InvoiceDetailOut)
def create_invoice_endpoint(payload: InvoiceCreate, db: Session = Depends(get_db)) -> InvoiceDetailOut:
    today = date.today()
    customer = _get_customer_or_404(db, payload.customer_id)
    issue = payload.issue_date or today
    due = payload.due_date or (issue + timedelta(days=7))
    if due < issue:
        raise HTTPException(status_code=422, detail="due_date cannot be before issue_date")
    items = [item.model_dump() for item in payload.items]
    try:
        invoice = create_invoice(
            db,
            customer,
            issue,
            due,
            items,
            notes=payload.notes or "",
            status=payload.status,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(invoice)
    return _invoice_detail(db, invoice, today)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceDetailOut:
    today = date.today()
    invoice = _get_invoice_or_404(db, invoice_id)
    return _invoice_detail(db, invoice, today)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceDetailOut)
def update_invoice_status(
    invoice_id: int, payload: InvoiceStatusUpdate, db: Session = Depends(get_db)
) -> InvoiceDetailOut:
    today = date.today()
    invoice = _get_invoice_or_404(db, invoice_id)
    new_status = payload.status
    if new_status in ("paid", "part_paid"):
        raise HTTPException(
            status_code=400, detail="paid and part_paid are set automatically from payments"
        )
    if new_status not in ("draft", "sent", "void"):
        raise HTTPException(status_code=422, detail="Status must be draft, sent or void")
    if len(invoice.payments) > 0 and new_status in ("draft", "void"):
        raise HTTPException(
            status_code=409,
            detail="Cannot set an invoice with payments to %s" % new_status,
        )
    invoice.status = new_status
    recalculate_status(invoice, today)
    db.commit()
    db.refresh(invoice)
    return _invoice_detail(db, invoice, today)


@router.post("/invoices/{invoice_id}/payments", status_code=201, response_model=PaymentCreatedOut)
def add_payment(
    invoice_id: int, payload: PaymentCreate, db: Session = Depends(get_db)
) -> PaymentCreatedOut:
    today = date.today()
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status in ("draft", "void"):
        raise HTTPException(
            status_code=409, detail="Cannot record a payment on a %s invoice" % invoice.status
        )
    paid_on = payload.paid_on or today
    if paid_on > today:
        raise HTTPException(status_code=422, detail="paid_on cannot be in the future")
    try:
        payment = record_payment(
            db,
            invoice,
            payload.amount_minor,
            paid_on,
            method=payload.method,
            note=payload.note or "",
            today=today,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(payment)
    db.refresh(invoice)
    return PaymentCreatedOut(
        payment=_payment_out(payment),
        invoice=_invoice_summary(invoice, today),
    )


@router.delete("/invoices/{invoice_id}/payments/{payment_id}", status_code=204)
def delete_payment(invoice_id: int, payment_id: int, db: Session = Depends(get_db)) -> Response:
    today = date.today()
    invoice = _get_invoice_or_404(db, invoice_id)
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id, Payment.invoice_id == invoice.id)
        .first()
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found on this invoice")
    db.delete(payment)
    db.flush()
    db.expire(invoice, ["payments"])
    recalculate_status(invoice, today)
    db.commit()
    return Response(status_code=204)


@router.post("/invoices/{invoice_id}/reminders", status_code=201, response_model=ReminderOut)
def create_reminder(
    invoice_id: int, payload: ReminderCreate, db: Session = Depends(get_db)
) -> ReminderOut:
    today = date.today()
    invoice = _get_invoice_or_404(db, invoice_id)
    status = _figures(invoice, today)["status"]
    if status in ("paid", "void"):
        raise HTTPException(
            status_code=409, detail="Cannot send a reminder for a %s invoice" % status
        )

    customer = invoice.customer
    customer_name = customer.name if customer is not None else ""
    phone = customer.phone if customer is not None else ""
    name_parts = customer_name.split()
    first_name = name_parts[0] if name_parts else "there"

    settings = _load_settings(db)
    business_name = settings["business_name"]
    currency = settings["currency_symbol"]
    balance = invoice_balance_minor(invoice)
    due_text = invoice.due_date.strftime("%d %b %Y") if invoice.due_date else "on receipt"

    message = (payload.message or "").strip()
    if not message:
        message = (
            "Hi %s, a friendly reminder that invoice %s for %s (due %s) is still outstanding. "
            "Could you please arrange payment at your earliest? Thank you - %s"
            % (first_name, invoice.number, format_minor(balance, currency), due_text, business_name)
        )

    reminder = Reminder(
        invoice_id=invoice.id,
        channel="whatsapp",
        sent_at=datetime.utcnow(),
        message=message,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return ReminderOut(
        id=reminder.id,
        sent_at=reminder.sent_at,
        message=reminder.message,
        channel=reminder.channel,
        whatsapp_url=_whatsapp_url(phone, reminder.message),
    )


# ---------------------------------------------------------------- bills

@router.get("/bills", response_model=List[BillOut])
def list_bills(db: Session = Depends(get_db)) -> List[BillOut]:
    bills = db.query(Bill).order_by(Bill.id).all()
    return [
        BillOut(
            id=b.id,
            payee=b.payee,
            category=b.category,
            amount_minor=b.amount_minor,
            recurrence=b.recurrence,
            due_day=b.due_day,
            next_due_date=b.next_due_date,
            active=bool(b.active),
        )
        for b in bills
    ]


@router.post("/bills", status_code=201, response_model=BillOut)
def create_bill(payload: BillCreate, db: Session = Depends(get_db)) -> BillOut:
    monthly = payload.recurrence == "monthly"
    bill = Bill(
        payee=payload.payee.strip(),
        category=payload.category,
        amount_minor=payload.amount_minor,
        recurrence=payload.recurrence,
        due_day=payload.due_day if monthly else None,
        next_due_date=None if monthly else payload.next_due_date,
        active=True,
        is_sample=False,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return BillOut(
        id=bill.id,
        payee=bill.payee,
        category=bill.category,
        amount_minor=bill.amount_minor,
        recurrence=bill.recurrence,
        due_day=bill.due_day,
        next_due_date=bill.next_due_date,
        active=bool(bill.active),
    )


@router.patch("/bills/{bill_id}", response_model=BillOut)
def update_bill(bill_id: int, payload: BillUpdate, db: Session = Depends(get_db)) -> BillOut:
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    changes = payload.model_dump(exclude_unset=True)
    if "active" in changes:
        if changes["active"] is None:
            raise HTTPException(status_code=422, detail="active cannot be null")
        bill.active = changes["active"]
    if "amount_minor" in changes:
        if changes["amount_minor"] is None:
            raise HTTPException(status_code=422, detail="amount_minor cannot be null")
        bill.amount_minor = changes["amount_minor"]
    db.commit()
    db.refresh(bill)
    return BillOut(
        id=bill.id,
        payee=bill.payee,
        category=bill.category,
        amount_minor=bill.amount_minor,
        recurrence=bill.recurrence,
        due_day=bill.due_day,
        next_due_date=bill.next_due_date,
        active=bool(bill.active),
    )


@router.delete("/bills/{bill_id}", status_code=204)
def delete_bill(bill_id: int, db: Session = Depends(get_db)) -> Response:
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    db.delete(bill)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- recurring fees

def _fee_out(fee: RecurringFee) -> RecurringFeeOut:
    customer = fee.customer
    return RecurringFeeOut(
        id=fee.id,
        customer_id=fee.customer_id,
        customer_name=customer.name if customer is not None else "",
        amount_minor=fee.amount_minor,
        cadence=fee.cadence,
        due_day=fee.due_day,
        next_due_date=fee.next_due_date,
        active=bool(fee.active),
    )


@router.get("/recurring-fees", response_model=List[RecurringFeeOut])
def list_recurring_fees(db: Session = Depends(get_db)) -> List[RecurringFeeOut]:
    fees = db.query(RecurringFee).order_by(RecurringFee.id).all()
    return [_fee_out(f) for f in fees]


@router.post("/recurring-fees", status_code=201, response_model=RecurringFeeOut)
def create_recurring_fee(
    payload: RecurringFeeCreate, db: Session = Depends(get_db)
) -> RecurringFeeOut:
    _get_customer_or_404(db, payload.customer_id)
    monthly = payload.cadence == "monthly"
    fee = RecurringFee(
        customer_id=payload.customer_id,
        amount_minor=payload.amount_minor,
        cadence=payload.cadence,
        due_day=payload.due_day if monthly else None,
        next_due_date=None if monthly else payload.next_due_date,
        active=True,
        is_sample=False,
    )
    db.add(fee)
    db.commit()
    db.refresh(fee)
    return _fee_out(fee)


@router.delete("/recurring-fees/{fee_id}", status_code=204)
def delete_recurring_fee(fee_id: int, db: Session = Depends(get_db)) -> Response:
    fee = db.get(RecurringFee, fee_id)
    if fee is None:
        raise HTTPException(status_code=404, detail="Recurring fee not found")
    db.delete(fee)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- dashboard

@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardOut:
    today = date.today()
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])

    invoices = db.query(Invoice).all()
    payments = db.query(Payment).all()
    settings = _load_settings(db)

    aging = aging_summary(invoices, today)
    payments_summary = payment_summary(payments, today, month_start, month_end)
    overdue_rows = build_overdue_list(invoices, today)[:50]
    customer_count = db.query(func.count(Customer.id)).scalar() or 0

    return DashboardOut(
        today=today,
        business_name=settings["business_name"],
        currency_symbol=settings["currency_symbol"],
        total_outstanding_minor=int(aging["total_outstanding_minor"]),
        total_overdue_minor=int(aging["total_overdue_minor"]),
        overdue_count=int(aging["overdue_count"]),
        aging=aging,
        payments=payments_summary,
        overdue=[OverdueRowOut(**row) for row in overdue_rows],
        customer_count=int(customer_count),
        invoice_count=len(invoices),
    )


# ---------------------------------------------------------------- settings

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return _settings_out(_load_settings(db))


@router.patch("/settings")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    for key, value in payload.model_dump(exclude_none=True).items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    return _settings_out(_load_settings(db))
