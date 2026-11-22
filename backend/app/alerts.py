"""Pure alert rules for the cash desk (Stage 4). No DB access. Money is integer minor units."""

from datetime import date
from typing import Any, Dict, List, Union

from app.money import format_minor

MAX_ALERTS = 20
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def format_date_label(value: Union[date, str, None]) -> str:
    """Readable date, e.g. '05 Mar 2025'. Accepts a date or an ISO string."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d %b %Y")


def build_alerts(
    today: date,
    overdue_list: List[Dict[str, Any]],
    forecast: Dict[str, Any],
    safe_balance_minor: int,
) -> List[Dict[str, Any]]:
    """Alerts from overdue invoices and the baseline forecast, sorted and capped at 20."""
    alerts: List[Dict[str, Any]] = []

    for row in overdue_list:
        days = int(row["days_overdue"])
        if days <= 0:
            continue
        invoice_id = row["invoice_id"]
        name = row["customer_name"]
        balance = int(row["balance_minor"])
        detail = "%s is %d days overdue on invoice %s." % (
            format_minor(balance), days, row["invoice_number"]
        )
        if days >= 30:
            alerts.append({
                "id": "overdue-%s" % invoice_id,
                "severity": "critical",
                "title": "Chase %s today" % name,
                "detail": detail,
                "action_label": "Chase today",
                "action_type": "chase_invoice",
                "action_target": invoice_id,
                "amount_minor": balance,
            })
        else:
            alerts.append({
                "id": "overdue-%s" % invoice_id,
                "severity": "warning",
                "title": "Follow up with %s" % name,
                "detail": detail,
                "action_label": "Send reminder",
                "action_type": "chase_invoice",
                "action_target": invoice_id,
                "amount_minor": balance,
            })

    first_negative = forecast.get("first_negative_date")
    first_below_safe = forecast.get("first_below_safe_date")
    if first_negative:
        shortfall = max(-int(forecast.get("min_balance_minor", 0)), 0)
        alerts.append({
            "id": "forecast-negative",
            "severity": "critical",
            "title": "Cash goes negative on %s" % format_date_label(first_negative),
            "detail": "Projected shortfall of %s at the lowest point, on %s." % (
                format_minor(shortfall), format_date_label(forecast.get("min_balance_date"))
            ),
            "action_label": "Collect overdue balances before %s" % format_date_label(first_negative),
            "action_type": "review_forecast",
            "action_target": None,
            "amount_minor": shortfall,
        })
    elif first_below_safe:
        alerts.append({
            "id": "forecast-safe-balance",
            "severity": "warning",
            "title": "Cash falls below safe balance on %s" % format_date_label(first_below_safe),
            "detail": "Safe balance is %s; projected cash drops under it." % format_minor(
                int(safe_balance_minor)
            ),
            "action_label": "Review forecast",
            "action_type": "review_forecast",
            "action_target": None,
            "amount_minor": int(safe_balance_minor),
        })

    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), -int(a["amount_minor"])))
    return alerts[:MAX_ALERTS]
