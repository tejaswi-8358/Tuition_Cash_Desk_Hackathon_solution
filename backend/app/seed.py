"""Sample data for "Sunrise Home Tuition", a home-tutor business in India (INR, ₹).

Run from the backend folder:  python -m app.seed
The __main__ block drops and recreates every table, then seeds, so re-running it is safe.
Values are deterministic (random.Random(42)); all dates are relative to date.today().
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine, init_db
from app.models import Bill, Customer, Invoice, InvoiceItem, Payment, RecurringFee, Setting
from app.money import to_minor

BUSINESS_NAME = "Sunrise Home Tuition"
CURRENCY_SYMBOL = "₹"
OPENING_CASH_MINOR = 3_800_000  # ₹38,000.00
SAFE_BALANCE_MINOR = 1_500_000  # ₹15,000.00

STUDENT_NAMES: List[str] = [
    "Aarav Sharma", "Ananya Iyer", "Vihaan Reddy", "Diya Patel", "Ishaan Gupta",
    "Saanvi Nair", "Reyansh Verma", "Aadhya Menon", "Kabir Singh", "Myra Kapoor",
    "Advik Joshi", "Kiara Das", "Arnav Chopra", "Pari Bose", "Dhruv Malhotra",
    "Riya Pillai", "Shaurya Rao", "Anika Desai", "Rudra Mishra", "Tara Banerjee",
    "Yuvaan Khanna", "Sara Ahmed", "Atharv Kulkarni", "Meera Shetty", "Zoya Qureshi",
]
SUBJECTS: List[str] = ["Maths", "Science", "English", "Hindi", "Social Studies", "Physics", "Chemistry"]
PAYMENT_METHODS: List[str] = ["cash", "bank", "upi", "other"]
LATE_PAYER_COUNT = 6
PART_PAID_COUNT = 2


@dataclass
class _Student:
    customer: Customer
    fee_rupees: int
    grade: int
    subject: str
    due_day: int
    late: bool
    part_paid: bool


def _month_start(today: date, months_back: int) -> date:
    """First day of the calendar month `months_back` months before today's month."""
    index = today.year * 12 + (today.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def _mobile(rng: random.Random, used: set) -> str:
    """Unique 10-digit Indian mobile number (starts 6-9), prefixed with country code 91."""
    while True:
        number = rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))
        if number not in used:
            used.add(number)
            return "91" + number


def seed_sample_data(db: Session) -> bool:
    """Insert sample settings, students, invoices, payments, bills and fees.

    Returns False (and changes nothing) if sample customers already exist.
    """
    already = db.scalars(
        select(Customer.id).where(Customer.is_sample.is_(True)).limit(1)
    ).first()
    if already is not None:
        return False

    rng = random.Random(42)
    today = date.today()

    for key, value in {
        "business_name": BUSINESS_NAME,
        "currency_symbol": CURRENCY_SYMBOL,
        "opening_cash_minor": str(OPENING_CASH_MINOR),
        "safe_balance_minor": str(SAFE_BALANCE_MINOR),
        "data_mode": "sample",
    }.items():
        db.merge(Setting(key=key, value=value))

    late_idx = set(rng.sample(range(len(STUDENT_NAMES)), LATE_PAYER_COUNT))
    on_time_idx = [i for i in range(len(STUDENT_NAMES)) if i not in late_idx]
    part_paid_idx = set(rng.sample(on_time_idx, PART_PAID_COUNT))

    used_phones: set = set()
    students: List[_Student] = []
    for i, name in enumerate(STUDENT_NAMES):
        late = i in late_idx
        customer = Customer(
            name=name,
            phone=_mobile(rng, used_phones),
            default_delay_days=rng.randint(15, 45) if late else 0,
            notes="Pays late - needs regular chasing" if late else "",
            is_sample=True,
        )
        students.append(_Student(
            customer=customer,
            fee_rupees=rng.randrange(3000, 6001, 100),
            grade=rng.randint(6, 12),
            subject=rng.choice(SUBJECTS),
            due_day=rng.randint(5, 10),
            late=late,
            part_paid=i in part_paid_idx,
        ))
    db.add_all([s.customer for s in students])

    db.add_all([
        RecurringFee(customer=s.customer, amount_minor=to_minor(s.fee_rupees), cadence="monthly",
                     due_day=s.due_day, active=True, is_sample=True)
        for s in students
    ])

    counters: Dict[str, int] = {}

    def next_number(issue: date) -> str:
        ym = issue.strftime("%Y%m")
        counters[ym] = counters.get(ym, 0) + 1
        return f"TI-{ym}-{counters[ym]:03d}"

    invoices: List[Invoice] = []
    for months_back in (2, 1, 0):  # oldest first, so invoice numbers run in date order
        for s in students:
            cust = s.customer
            if s.late and months_back == 0:
                # Chronically late: this month's invoice issued 20-45 days ago, still unpaid, overdue.
                issue = today - timedelta(days=rng.randint(20, 45))
                due = issue + timedelta(days=7)
                paid_on = None
            else:
                issue = _month_start(today, months_back)
                due = date(issue.year, issue.month, s.due_day)
                paid_on = due + timedelta(days=cust.default_delay_days + rng.randint(0, 3))

            if s.part_paid and months_back == 1:
                status, amount = "part_paid", s.fee_rupees // 2
            elif paid_on is not None and paid_on <= today:
                status, amount = "paid", s.fee_rupees
            else:
                status, amount = "sent", 0

            inv = Invoice(customer=cust, number=next_number(issue), issue_date=issue,
                          due_date=due, status=status, is_sample=True)
            inv.items.append(InvoiceItem(
                description=f"Monthly tuition - Class {s.grade} ({s.subject})",
                quantity=1, unit_price_minor=to_minor(s.fee_rupees),
            ))
            if amount:
                inv.payments.append(Payment(
                    amount_minor=to_minor(amount), paid_on=paid_on,
                    method=rng.choice(PAYMENT_METHODS), is_sample=True,
                ))
            invoices.append(inv)
    db.add_all(invoices)

    db.add_all([
        Bill(payee="Tutor's room rent", category="rent", amount_minor=to_minor(12000),
             recurrence="monthly", due_day=5, active=True, is_sample=True),
        Bill(payee="Part-time helper salary", category="salary", amount_minor=to_minor(6000),
             recurrence="monthly", due_day=1, active=True, is_sample=True),
        Bill(payee="Study material supplier", category="materials", amount_minor=to_minor(3500),
             recurrence="monthly", due_day=15, active=True, is_sample=True),
        Bill(payee="Internet provider", category="utilities", amount_minor=to_minor(999),
             recurrence="monthly", due_day=10, active=True, is_sample=True),
        Bill(payee="Auto fare for home visits", category="transport", amount_minor=to_minor(1500),
             recurrence="weekly", next_due_date=today + timedelta(days=rng.randint(1, 7)),
             active=True, is_sample=True),
    ])

    db.commit()
    return True


if __name__ == "__main__":
    init_db()  # ensures backend/data exists and models are registered on Base.metadata
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_sample_data(session)
        customers = session.scalar(select(func.count()).select_from(Customer))
        invoices = session.scalar(select(func.count()).select_from(Invoice))
        payments = session.scalar(select(func.count()).select_from(Payment))
        bills = session.scalar(select(func.count()).select_from(Bill))
    print(f"customers={customers} invoices={invoices} payments={payments} bills={bills}")
