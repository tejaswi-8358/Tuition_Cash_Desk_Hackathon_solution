"""Stage 2 business logic: invoice money, status, overdue, aging and payment rules.

Pure functions take plain values or ORM objects and never touch a DB session.
DB helpers (recalculate_status, record_payment, create_invoice) take a Session,
only flush, and leave committing to the caller. Money is integer minor units (paise).
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from app.models import Customer, Invoice, InvoiceItem, Payment

INVOICE_PREFIX = "TI"
PRIORITY_CAP = 10 ** 12
OPEN_EXCLUDED_STATUSES = ("paid", "void", "draft")
BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")
PAYMENT_METHODS = ("cash", "bank", "upi", "other")


# ---------------------------------------------------------------- money / status

def invoice_total_minor(invoice: Invoice) -> int:
    """Sum of quantity * unit_price_minor over the invoice's items."""
    return sum(int(i.quantity) * int(i.unit_price_minor) for i in (invoice.items or []))


def invoice_paid_minor(invoice: Invoice) -> int:
    """Sum of all payment amounts recorded against the invoice."""
    return sum(int(p.amount_minor) for p in (invoice.payments or []))


def invoice_balance_minor(invoice: Invoice) -> int:
    """Outstanding amount: total minus paid, never below 0."""
    return max(invoice_total_minor(invoice) - invoice_paid_minor(invoice), 0)


def derive_status(
    total_minor: int,
    paid_minor: int,
    due_date: Optional[date],
    today: date,
    current_status: Optional[str],
) -> str:
    """Stored status from money amounts. Overdue is NOT a stored status (see days_overdue).

    void and draft are sticky and returned unchanged. due_date and today are accepted
    for a uniform signature but do not change the stored status.
    """
    if current_status == "void":
        return "void"
    if current_status == "draft":
        return "draft"
    balance = max(total_minor - paid_minor, 0)
    if balance <= 0 and total_minor > 0:
        return "paid"
    if paid_minor > 0 and balance > 0:
        return "part_paid"
    return "sent"


def days_overdue(balance_minor: int, due_date: Optional[date], today: date) -> int:
    """Days past due for an unpaid balance; 0 if settled, not yet due, or undated."""
    if balance_minor <= 0 or due_date is None or due_date >= today:
        return 0
    return (today - due_date).days


def aging_bucket(days_overdue_value: int) -> str:
    """Aging bucket label for a number of days overdue."""
    if days_overdue_value <= 0:
        return "current"
    if days_overdue_value <= 30:
        return "1-30"
    if days_overdue_value <= 60:
        return "31-60"
    if days_overdue_value <= 90:
        return "61-90"
    return "90+"


def bucket_for_invoice(balance_minor: int, days: int) -> str:
    """Like aging_bucket, but a zero balance is 'settled'."""
    if balance_minor <= 0:
        return "settled"
    return aging_bucket(days)


def validate_payment_amount(amount_minor: int, balance_minor: int) -> None:
    """Raise ValueError if the payment is not positive or exceeds the balance."""
    if amount_minor <= 0:
        raise ValueError("Payment must be positive")
    if amount_minor > balance_minor:
        raise ValueError("Payment exceeds outstanding balance")


# ---------------------------------------------------------------- numbering / timing

def next_invoice_number(existing_numbers: List[str], issue_date: date) -> str:
    """Next 'TI-YYYYMM-NNN' after the highest existing number with the same YYYYMM prefix."""
    prefix = "%s-%s-" % (INVOICE_PREFIX, issue_date.strftime("%Y%m"))
    highest = 0
    for number in existing_numbers:
        if not number or not number.startswith(prefix):
            continue
        tail = number[len(prefix):]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return "%s%03d" % (prefix, highest + 1)


def customer_average_delay_days(invoices_with_payments: List[Invoice]) -> int:
    """Mean days from due date to the last payment, over fully paid invoices. Min 0."""
    delays = []
    for inv in invoices_with_payments:
        total = invoice_total_minor(inv)
        if total <= 0 or invoice_paid_minor(inv) < total or inv.due_date is None:
            continue
        dated = [p for p in (inv.payments or []) if p.paid_on is not None]
        if not dated:
            continue
        last = max(dated, key=lambda p: p.paid_on)
        delays.append((last.paid_on - inv.due_date).days)
    if not delays:
        return 0
    mean = sum(delays) / float(len(delays))
    return max(int(round(mean)), 0)


def expected_payment_date(
    due_date: date,
    customer_default_delay_days: Optional[int],
    historical_avg_delay: Optional[int],
) -> date:
    """Due date plus the larger of the customer's default delay and historical average delay."""
    delay = max(int(customer_default_delay_days or 0), int(historical_avg_delay or 0))
    return due_date + timedelta(days=delay)


# ---------------------------------------------------------------- lists / summaries

def _snapshot(invoice: Invoice, today: date):
    """Return (total, paid, balance, derived_status) for an invoice."""
    total = invoice_total_minor(invoice)
    paid = invoice_paid_minor(invoice)
    balance = max(total - paid, 0)
    status = derive_status(total, paid, invoice.due_date, today, invoice.status)
    return total, paid, balance, status


def build_overdue_list(invoices: List[Invoice], today: date) -> List[Dict[str, object]]:
    """Overdue, open invoices with customer info, sorted by days overdue (desc)."""
    rows = []
    for inv in invoices:
        total, paid, balance, status = _snapshot(inv, today)
        if status in OPEN_EXCLUDED_STATUSES or balance <= 0:
            continue
        if inv.due_date is None or inv.due_date >= today:
            continue
        days = days_overdue(balance, inv.due_date, today)
        customer = inv.customer
        rows.append({
            "invoice_id": inv.id,
            "invoice_number": inv.number,
            "customer_id": inv.customer_id,
            "customer_name": customer.name if customer is not None else "",
            "customer_phone": customer.phone if customer is not None else "",
            "balance_minor": balance,
            "due_date": inv.due_date,
            "days_overdue": days,
            "bucket": aging_bucket(days),
            "total_minor": total,
            "paid_minor": paid,
        })
    rows.sort(key=lambda r: (-r["days_overdue"], r["invoice_id"] or 0))
    return rows


def aging_summary(invoices: List[Invoice], today: date) -> Dict[str, object]:
    """Open balances grouped into aging buckets (current = not yet due or due today)."""
    buckets = {b: {"count": 0, "amount_minor": 0} for b in BUCKETS}
    total_outstanding = 0
    total_overdue = 0
    overdue_count = 0
    for inv in invoices:
        _, _, balance, status = _snapshot(inv, today)
        if status in OPEN_EXCLUDED_STATUSES or balance <= 0:
            continue
        days = days_overdue(balance, inv.due_date, today)
        entry = buckets[aging_bucket(days)]
        entry["count"] += 1
        entry["amount_minor"] += balance
        total_outstanding += balance
        if days > 0:
            total_overdue += balance
            overdue_count += 1
    result: Dict[str, object] = dict(buckets)
    result["total_outstanding_minor"] = total_outstanding
    result["total_overdue_minor"] = total_overdue
    result["overdue_count"] = overdue_count
    return result


def payment_summary(
    payments: List[Payment],
    today: date,
    month_start: date,
    month_end: date,
) -> Dict[str, int]:
    """Totals received overall, within [month_start, month_end], and the payment count."""
    received_total = 0
    received_month = 0
    count = 0
    for p in payments:
        amount = int(p.amount_minor)
        received_total += amount
        count += 1
        if p.paid_on is not None and month_start <= p.paid_on <= month_end:
            received_month += amount
    return {
        "received_this_month_minor": received_month,
        "received_total_minor": received_total,
        "count": count,
    }


def priority_score(balance_minor: int, days_overdue_value: int) -> int:
    """Chase-priority sort key: (balance in whole rupees) * max(days overdue, 1), capped."""
    score = (int(balance_minor) // 100) * max(int(days_overdue_value), 1)
    return min(score, PRIORITY_CAP)


# ---------------------------------------------------------------- DB helpers

def recalculate_status(invoice: Invoice, today: Optional[date] = None) -> None:
    """Set invoice.status from its current totals. Does not commit."""
    if today is None:
        today = date.today()
    total = invoice_total_minor(invoice)
    paid = invoice_paid_minor(invoice)
    invoice.status = derive_status(total, paid, invoice.due_date, today, invoice.status)


def record_payment(
    db,
    invoice: Invoice,
    amount_minor: int,
    paid_on: date,
    method: str = "bank",
    note: str = "",
    today: Optional[date] = None,
) -> Payment:
    """Validate and add a payment, flush, and refresh status. Caller commits."""
    if invoice.status in ("draft", "void"):
        raise ValueError("Cannot record a payment on a %s invoice" % invoice.status)
    if method not in PAYMENT_METHODS:
        raise ValueError("Unknown payment method: %s" % method)
    validate_payment_amount(int(amount_minor), invoice_balance_minor(invoice))
    payment = Payment(
        invoice=invoice,
        amount_minor=int(amount_minor),
        paid_on=paid_on,
        method=method,
        note=note or "",
        is_sample=False,
    )
    db.add(payment)
    db.flush()
    recalculate_status(invoice, today)
    return payment


def create_invoice(
    db,
    customer: Customer,
    issue_date: date,
    due_date: Optional[date],
    items: List[Dict[str, object]],
    notes: str = "",
    status: str = "sent",
) -> Invoice:
    """Create an invoice with items and a generated number. Caller commits.

    items: dicts with description, quantity (>=1) and unit_price_minor (>=0).
    status: 'sent' (default) or 'draft'.
    """
    if customer is None:
        raise ValueError("Customer is required")
    if issue_date is None:
        raise ValueError("Issue date is required")
    if status not in ("sent", "draft"):
        raise ValueError("Invoice status must be 'sent' or 'draft'")
    if not items:
        raise ValueError("Invoice needs at least one item")

    cleaned = []
    for raw in items:
        description = str(raw.get("description", "")).strip()
        quantity = raw.get("quantity")
        unit_price = raw.get("unit_price_minor")
        if not description:
            raise ValueError("Item description is required")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError("Item quantity must be an integer of at least 1")
        if not isinstance(unit_price, int) or isinstance(unit_price, bool) or unit_price < 0:
            raise ValueError("Item unit_price_minor must be an integer of at least 0")
        cleaned.append((description, quantity, unit_price))

    existing = [row[0] for row in db.query(Invoice.number).all()]
    number = next_invoice_number(existing, issue_date)

    invoice = Invoice(
        customer=customer,
        number=number,
        issue_date=issue_date,
        due_date=due_date,
        status=status,
        notes=notes or "",
        is_sample=False,
    )
    for description, quantity, unit_price in cleaned:
        invoice.items.append(
            InvoiceItem(
                description=description,
                quantity=quantity,
                unit_price_minor=unit_price,
            )
        )
    db.add(invoice)
    db.flush()
    return invoice
