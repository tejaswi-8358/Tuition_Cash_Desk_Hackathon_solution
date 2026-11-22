"""AI-style insights for the cash desk (Stage 4).

deterministic_insights() is always available and needs no network. llm_insights() calls the
Anthropic Messages API only when ANTHROPIC_API_KEY is set, and returns None on any failure.
Nothing here raises. Money is integer minor units.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app import config
from app.alerts import format_date_label
from app.money import format_minor

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
SYSTEM_PROMPT = (
    "You are a finance assistant for a home tutor or small tuition business. "
    "Give exactly 3 short, actionable finance insights based on the JSON the user sends. "
    "Use only the numbers provided; do not compute or estimate any new numbers. "
    "Write one insight per line, plain sentences, no headings."
)
_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")


def deterministic_insights(
    overdue_list: List[Dict[str, Any]],
    forecast: Dict[str, Any],
    aging: Dict[str, Any],
    safe_balance_minor: int,
) -> List[str]:
    """3-5 plain-English sentences computed directly from the data."""
    sentences: List[str] = []
    overdue_count = int(aging.get("overdue_count", 0))
    total_overdue = int(aging.get("total_overdue_minor", 0))

    if overdue_count == 0 or not overdue_list:
        sentences.append("No invoices are overdue right now, so collections are on track.")
    else:
        sentences.append("You have %d overdue invoice%s totalling %s." % (
            overdue_count, "" if overdue_count == 1 else "s", format_minor(total_overdue)
        ))
        over_30 = [r for r in overdue_list if int(r["days_overdue"]) >= 30]
        if over_30:
            over_30_total = sum(int(r["balance_minor"]) for r in over_30)
            sentences.append("%d invoice%s are 30 or more days late, worth %s." % (
                len(over_30), "" if len(over_30) == 1 else "s", format_minor(over_30_total)
            ))
        else:
            sentences.append("None of the overdue invoices are 30 or more days late yet.")

        by_customer: Dict[str, Dict[str, int]] = {}
        for row in overdue_list:
            entry = by_customer.setdefault(row["customer_name"], {"balance": 0, "days": 0})
            entry["balance"] += int(row["balance_minor"])
            entry["days"] = max(entry["days"], int(row["days_overdue"]))
        top_name = max(by_customer, key=lambda n: by_customer[n]["balance"])
        top = by_customer[top_name]
        sentences.append("%s owes the most at %s, with the oldest invoice %d days overdue." % (
            top_name, format_minor(top["balance"]), top["days"]
        ))

    days = int(forecast.get("days", 0))
    sentences.append("Lowest projected cash over the next %d days is %s on %s." % (
        days,
        format_minor(int(forecast.get("min_balance_minor", 0))),
        format_date_label(forecast.get("min_balance_date")),
    ))
    first_negative = forecast.get("first_negative_date")
    if first_negative:
        sentences.append(
            "Cash is projected to go negative on %s, so collect overdue balances before then." %
            format_date_label(first_negative)
        )
    else:
        sentences.append("Cash stays above zero for the whole forecast window; your safe balance is %s." %
                         format_minor(int(safe_balance_minor)))
    return sentences[:5]


def llm_insights(context: Dict[str, Any]) -> Optional[List[str]]:
    """Ask Claude Haiku for short insights. Returns None when no key is set or on any failure."""
    try:
        if not config.ANTHROPIC_API_KEY:
            return None
        import httpx

        headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": 400,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": json.dumps(context, default=str)}],
        }
        with httpx.Client(timeout=15.0) as client:
            response = client.post(ANTHROPIC_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = str(block.get("text", ""))
                break
        lines: List[str] = []
        for raw in text.splitlines():
            line = _BULLET_RE.sub("", raw).strip()
            if line:
                lines.append(line)
        lines = lines[:5]
        return lines or None
    except Exception:
        return None


def get_insights(
    overdue_list: List[Dict[str, Any]],
    forecast: Dict[str, Any],
    aging: Dict[str, Any],
    safe_balance_minor: int,
) -> Dict[str, Any]:
    """LLM insights when available, otherwise deterministic rules. 'source' says which."""
    context = {
        "overdue_top": [
            {
                "customer_name": r["customer_name"],
                "invoice_number": r["invoice_number"],
                "balance_minor": int(r["balance_minor"]),
                "days_overdue": int(r["days_overdue"]),
            }
            for r in overdue_list[:10]
        ],
        "aging": {
            "total_overdue_minor": int(aging.get("total_overdue_minor", 0)),
            "total_outstanding_minor": int(aging.get("total_outstanding_minor", 0)),
            "overdue_count": int(aging.get("overdue_count", 0)),
        },
        "forecast": {
            "days": forecast.get("days"),
            "opening_cash_minor": forecast.get("opening_cash_minor"),
            "min_balance_minor": forecast.get("min_balance_minor"),
            "min_balance_date": forecast.get("min_balance_date"),
            "first_negative_date": forecast.get("first_negative_date"),
            "first_below_safe_date": forecast.get("first_below_safe_date"),
        },
        "safe_balance_minor": int(safe_balance_minor),
    }
    llm = llm_insights(context)
    if llm:
        return {"source": "llm", "insights": llm}
    return {
        "source": "rules",
        "insights": deterministic_insights(overdue_list, forecast, aging, safe_balance_minor),
    }
