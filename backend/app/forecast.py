"""Pure 90-day cash forecast engine (Stage 4).

No database access and no clock reads: `today` is always passed in. Money is integer minor
units (paise). Deterministic. Python 3.9 compatible (typing generics only).
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Any, Dict, List, Optional


def _monthly_dates(today: date, end: date, due_day: Optional[int]) -> List[date]:
    """Each month's due_day (clamped to the month length) within [today, end]."""
    if due_day is None:
        return []
    out: List[date] = []
    year, month = today.year, today.month
    while True:
        last = monthrange(year, month)[1]
        candidate = date(year, month, max(1, min(int(due_day), last)))
        if candidate > end:
            break
        if candidate >= today:
            out.append(candidate)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return out


def _weekly_dates(today: date, end: date, anchor: Optional[date]) -> List[date]:
    """Every 7 days from anchor, stepped (forward or backward) to the first date >= today."""
    if anchor is None:
        return []
    delta = (today - anchor).days
    steps = -((-delta) // 7)  # ceiling division
    current = anchor + timedelta(days=7 * steps)
    out: List[date] = []
    while current <= end:
        out.append(current)
        current += timedelta(days=7)
    return out


def _schedule(
    today: date,
    end: date,
    recurrence: str,
    due_day: Optional[int],
    next_due: Optional[date],
) -> List[date]:
    """Occurrences in [today, end] for 'monthly', 'weekly' or a one-off (anything else)."""
    if recurrence == "monthly":
        return _monthly_dates(today, end, due_day)
    if recurrence == "weekly":
        return _weekly_dates(today, end, next_due)
    if next_due is not None and today <= next_due <= end:
        return [next_due]
    return []


def _adjusted_bill_amount(amount_minor: int, category: str, overrides: Dict[str, Any]) -> int:
    """Apply expense_increase_pct (integer math), optionally restricted to one category."""
    pct = int(overrides.get("expense_increase_pct") or 0)
    if pct == 0:
        return amount_minor
    only_category = overrides.get("expense_increase_category")
    if only_category and category != only_category:
        return amount_minor
    return amount_minor + (amount_minor * pct) // 100


def build_forecast(
    today: date,
    days: int,
    opening_cash_minor: int,
    open_invoices: List[Dict[str, Any]],
    bills: List[Dict[str, Any]],
    recurring_fees: List[Dict[str, Any]],
    customer_delays: Dict[int, int],
    overrides: Optional[Dict[str, Any]] = None,
    safe_balance_minor: int = 0,
) -> Dict[str, Any]:
    """Day-by-day cash projection for [today, today + days].

    Expected invoice receipt = due_date + max(default delay, historical delay, customer_delays
    floor) + late_days (for late_customer_id only); never earlier than today.
    customer_delays is an optional per-customer minimum delay; it can only raise the delay.
    """
    ov = dict(overrides or {})
    days = int(days)
    end = today + timedelta(days=days)
    lost_id = ov.get("lost_customer_id")
    late_id = ov.get("late_customer_id")
    late_days = int(ov.get("late_days") or 0)
    delays = customer_delays or {}
    safe = int(safe_balance_minor)

    receipts: List[Dict[str, Any]] = []
    payments: List[Dict[str, Any]] = []

    # Open invoices: one expected receipt each (balance is collected in full on that date).
    for inv in open_invoices:
        cid = inv["customer_id"]
        balance = int(inv["balance_minor"])
        if balance <= 0 or (lost_id is not None and cid == lost_id):
            continue
        due = inv.get("due_date") or today
        base_delay = max(
            int(inv.get("customer_default_delay_days") or 0),
            int(inv.get("historical_delay_days") or 0),
            int(delays.get(cid) or 0),
        )
        extra = late_days if (late_id is not None and cid == late_id) else 0
        expected = due + timedelta(days=base_delay + extra)
        if expected < today:
            # Overdue: expected today, pushed back by the late customer's late_days (0 otherwise).
            expected = today + timedelta(days=extra)
        if expected > end:
            continue
        receipts.append({
            "date": expected,
            "amount_minor": balance,
            "label": "Invoice %s - %s" % (inv.get("invoice_number", ""), inv.get("customer_name", "")),
        })

    # Recurring fees: expected receipts. Lost customers excluded. A late customer's fees are pushed back by late_days.
    for fee in recurring_fees:
        cid = fee["customer_id"]
        if lost_id is not None and cid == lost_id:
            continue
        amount = int(fee["amount_minor"])
        fee_shift = late_days if (late_id is not None and cid == late_id) else 0
        for when in _schedule(today, end, fee.get("cadence", ""), fee.get("due_day"), fee.get("next_due_date")):
            when = when + timedelta(days=fee_shift)
            if when > end:
                continue
            receipts.append({
                "date": when,
                "amount_minor": amount,
                "label": "Fee - %s" % fee.get("customer_name", ""),
            })

    # Bills: scheduled payments, with the expense increase applied.
    for bill in bills:
        category = bill.get("category", "")
        amount = _adjusted_bill_amount(int(bill["amount_minor"]), category, ov)
        for when in _schedule(today, end, bill.get("recurrence", ""), bill.get("due_day"), bill.get("next_due_date")):
            payments.append({
                "date": when,
                "amount_minor": amount,
                "label": "%s (%s)" % (bill.get("payee", ""), category),
            })

    receipts.sort(key=lambda r: (r["date"], r["label"]))
    payments.sort(key=lambda p: (p["date"], p["label"]))

    inflow_by_day: Dict[date, int] = {}
    outflow_by_day: Dict[date, int] = {}
    events_by_day: Dict[date, List[str]] = {}
    for r in receipts:
        inflow_by_day[r["date"]] = inflow_by_day.get(r["date"], 0) + r["amount_minor"]
        events_by_day.setdefault(r["date"], []).append("In: " + r["label"])
    for p in payments:
        outflow_by_day[p["date"]] = outflow_by_day.get(p["date"], 0) + p["amount_minor"]
        events_by_day.setdefault(p["date"], []).append("Out: " + p["label"])

    daily: List[Dict[str, Any]] = []
    running = int(opening_cash_minor)
    min_balance: Optional[int] = None
    min_date: Optional[date] = None
    first_negative: Optional[date] = None
    first_below_safe: Optional[date] = None
    total_in = 0
    total_out = 0
    for i in range(days + 1):
        d = today + timedelta(days=i)
        inflow = inflow_by_day.get(d, 0)
        outflow = outflow_by_day.get(d, 0)
        running = running + inflow - outflow
        total_in += inflow
        total_out += outflow
        if min_balance is None or running < min_balance:
            min_balance = running
            min_date = d
        if running < 0 and first_negative is None:
            first_negative = d
        if running < safe and first_below_safe is None:
            first_below_safe = d
        daily.append({
            "date": d.isoformat(),
            "inflow_minor": inflow,
            "outflow_minor": outflow,
            "closing_minor": running,
            "events": events_by_day.get(d, []),
        })

    expected_income = sum(int(r["amount_minor"]) for r in receipts)
    expected_expenses = sum(int(p["amount_minor"]) for p in payments)
    lowest_balance = int(min_balance if min_balance is not None else opening_cash_minor)
    assumptions: List[str] = [
        "Invoices are collected on their due date plus the customer's delay (default, historical or customer-specific), and the full outstanding balance arrives on that one date. Partial payments are not modelled.",
        "Recurring tuition fees are counted on each scheduled date, shifted by any late-payment scenario.",
        "Business expenses are paid on their due date and are not delayed by the late-payment scenario.",
        "Overdue invoices are assumed to be paid from today; a late-payment scenario delays them from today.",
        "A fee and an invoice are NOT matched against each other: if the same tuition is both an open invoice and a recurring fee, it may be counted twice. No link exists in the data model to prevent this.",
        "Sample records, if present, are included in the forecast.",
        "The forecast starts from the server's current date and runs for the requested number of days (30, 60 or 90). Each horizon is the first N days of the same daily projection.",
        "The safe balance defaults to 0 if not set in settings.",
    ]

    return {
        "start": today.isoformat(),
        "days": days,
        "opening_cash_minor": int(opening_cash_minor),
        "daily": daily,
        "min_balance_minor": lowest_balance,
        "min_balance_date": (min_date or today).isoformat(),
        "lowest_balance_minor": lowest_balance,
        "lowest_balance_date": (min_date or today).isoformat(),
        "first_negative_date": first_negative.isoformat() if first_negative else None,
        "safe_balance_minor": safe,
        "first_below_safe_date": first_below_safe.isoformat() if first_below_safe else None,
        "total_inflow_minor": total_in,
        "total_outflow_minor": total_out,
        "expected_income_minor": expected_income,
        "expected_expenses_minor": expected_expenses,
        "assumptions": assumptions,
        "receipts": [
            {"date": r["date"].isoformat(), "amount_minor": r["amount_minor"], "label": r["label"]}
            for r in receipts
        ],
        "payments": [
            {"date": p["date"].isoformat(), "amount_minor": p["amount_minor"], "label": p["label"]}
            for p in payments
        ],
    }


def compare_scenarios(baseline_forecast: Dict[str, Any], scenario_forecast: Dict[str, Any]) -> Dict[str, Any]:
    """Headline differences between a baseline forecast and a scenario forecast."""
    base_min = int(baseline_forecast["min_balance_minor"])
    scen_min = int(scenario_forecast["min_balance_minor"])
    return {
        "baseline_min_minor": base_min,
        "scenario_min_minor": scen_min,
        "delta_min_minor": scen_min - base_min,
        "baseline_first_negative": baseline_forecast.get("first_negative_date"),
        "scenario_first_negative": scenario_forecast.get("first_negative_date"),
        "delta_total_inflow_minor": int(scenario_forecast["total_inflow_minor"])
        - int(baseline_forecast["total_inflow_minor"]),
        "delta_total_outflow_minor": int(scenario_forecast["total_outflow_minor"])
        - int(baseline_forecast["total_outflow_minor"]),
    }
