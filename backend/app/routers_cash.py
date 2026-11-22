"""Stage 4 cash routes: forecast, scenarios, alerts, chase list and AI insights.

Pure logic lives in app.forecast, app.alerts and app.ai_insights. This module loads rows
via SQLAlchemy, builds plain inputs for those functions and shapes responses. Money is
integer minor units. Python 3.9 compatible (typing generics only).
"""

import json
import urllib.parse
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.ai_insights import get_insights
from app.alerts import build_alerts, format_date_label
from app.db import get_db
from app.forecast import build_forecast, compare_scenarios
from app.models import Bill, Customer, Invoice, RecurringFee, Scenario, Setting
from app.money import format_minor
from app.services import (
    OPEN_EXCLUDED_STATUSES,
    aging_summary,
    build_overdue_list,
    customer_average_delay_days,
    derive_status,
    invoice_balance_minor,
    invoice_paid_minor,
    invoice_total_minor,
)

router = APIRouter(prefix="/api")

FORECAST_BASELINE_DAYS = 90
CHASE_LIMIT = 30
BUSINESS_NAME_DEFAULT = "Sunrise Home Tuition"
CURRENCY_DEFAULT = "₹"

BillCategory = Literal["rent", "salary", "materials", "transport", "utilities", "other"]


# ---------------------------------------------------------------- schemas

class ScenarioOverrides(BaseModel):
    late_customer_id: Optional[int] = None
    late_days: Optional[int] = Field(None, ge=0, le=120)
    expense_increase_pct: Optional[int] = Field(None, ge=0, le=200)
    expense_increase_category: Optional[BillCategory] = None
    lost_customer_id: Optional[int] = None

    @model_validator(mode="after")
    def _check_any_override(self) -> "ScenarioOverrides":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Set at least one scenario override")
        if self.late_days and self.late_customer_id is None:
            raise ValueError("late_days requires late_customer_id")
        return self


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    overrides: ScenarioOverrides

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank")
        return stripped


class ScenarioOut(BaseModel):
    id: int
    name: str
    overrides: Dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------- helpers

def _setting_text(db: Session, key: str, default: str) -> str:
    row = db.get(Setting, key)
    return row.value if row is not None and row.value else default


def _setting_int(db: Session, key: str) -> int:
    try:
        return int(_setting_text(db, key, "0"))
    except ValueError:
        return 0


def _parse_overrides(raw: Optional[str]) -> Dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _scenario_out(scenario: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=scenario.id,
        name=scenario.name,
        overrides=_parse_overrides(scenario.overrides_json),
        created_at=scenario.created_at,
    )


def _load_inputs(db: Session, today: date) -> Dict[str, Any]:
    """Plain inputs for the pure functions, plus the raw invoice rows for aging and overdue."""
    invoices = db.query(Invoice).all()

    by_customer: Dict[int, List[Invoice]] = {}
    for inv in invoices:
        by_customer.setdefault(inv.customer_id, []).append(inv)

    open_invoices: List[Dict[str, Any]] = []
    delays: Dict[int, int] = {}
    for inv in invoices:
        total = invoice_total_minor(inv)
        paid = invoice_paid_minor(inv)
        balance = invoice_balance_minor(inv)
        status = derive_status(total, paid, inv.due_date, today, inv.status)
        if status in OPEN_EXCLUDED_STATUSES or balance <= 0 or inv.customer is None:
            continue
        cid = inv.customer_id
        if cid not in delays:
            delays[cid] = customer_average_delay_days(by_customer.get(cid, []))
        open_invoices.append({
            "invoice_id": inv.id,
            "invoice_number": inv.number,
            "customer_id": cid,
            "customer_name": inv.customer.name,
            "balance_minor": balance,
            # Undated invoices are treated as due today.
            "due_date": inv.due_date or today,
            "customer_default_delay_days": inv.customer.default_delay_days or 0,
            "historical_delay_days": delays[cid],
        })

    bills = [
        {
            "bill_id": b.id,
            "payee": b.payee,
            "category": b.category,
            "amount_minor": int(b.amount_minor),
            "recurrence": b.recurrence,
            "due_day": b.due_day,
            "next_due_date": b.next_due_date,
        }
        for b in db.query(Bill).all()
        if b.active
    ]

    fees = [
        {
            "fee_id": f.id,
            "customer_id": f.customer_id,
            "customer_name": f.customer.name if f.customer is not None else "",
            "amount_minor": int(f.amount_minor),
            "cadence": f.cadence,
            "due_day": f.due_day,
            "next_due_date": f.next_due_date,
        }
        for f in db.query(RecurringFee).all()
        if f.active
    ]

    return {
        "invoices": invoices,
        "open_invoices": open_invoices,
        "bills": bills,
        "fees": fees,
        "customer_delays": delays,
        "opening": _setting_int(db, "opening_cash_minor"),
        "safe": _setting_int(db, "safe_balance_minor"),
        "business_name": _setting_text(db, "business_name", BUSINESS_NAME_DEFAULT),
        "currency_symbol": _setting_text(db, "currency_symbol", CURRENCY_DEFAULT),
    }


def _run_forecast(data: Dict[str, Any], today: date, days: int, overrides: Dict[str, Any]) -> Dict[str, Any]:
    return build_forecast(
        today,
        days,
        data["opening"],
        data["open_invoices"],
        data["bills"],
        data["fees"],
        data["customer_delays"],
        overrides,
        safe_balance_minor=data["safe"],
    )


def _tone_for(days_overdue: int) -> str:
    if days_overdue <= 14:
        return "friendly"
    if days_overdue <= 44:
        return "firm"
    return "final"


def _first_name(full_name: str) -> str:
    parts = (full_name or "").split()
    return parts[0] if parts else "there"


def _chase_message(row: Dict[str, Any], business_name: str, symbol: str) -> str:
    return (
        "Hi %s, a friendly reminder that invoice %s for %s was due on %s. "
        "Could you please arrange payment at your earliest? Thank you - %s"
    ) % (
        _first_name(row["customer_name"]),
        row["invoice_number"],
        format_minor(int(row["balance_minor"]), symbol),
        format_date_label(row["due_date"]),
        business_name,
    )


def _ensure_customers_exist(db: Session, overrides: Dict[str, Any]) -> None:
    for key in ("late_customer_id", "lost_customer_id"):
        value = overrides.get(key)
        if value is not None and db.get(Customer, value) is None:
            raise HTTPException(status_code=404, detail="Customer not found for %s" % key)


# ---------------------------------------------------------------- forecast

@router.get("/forecast")
def get_forecast(
    days: int = Query(90, ge=30, le=90),
    scenario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    today = date.today()
    data = _load_inputs(db, today)
    baseline = _run_forecast(data, today, days, {})

    scenario_forecast: Optional[Dict[str, Any]] = None
    comparison: Optional[Dict[str, Any]] = None
    if scenario_id is not None:
        scenario = db.get(Scenario, scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        scenario_forecast = _run_forecast(data, today, days, _parse_overrides(scenario.overrides_json))
        comparison = compare_scenarios(baseline, scenario_forecast)

    return {"baseline": baseline, "scenario": scenario_forecast, "comparison": comparison}


# ---------------------------------------------------------------- scenarios

@router.get("/scenarios", response_model=List[ScenarioOut])
def list_scenarios(db: Session = Depends(get_db)) -> List[ScenarioOut]:
    rows = db.query(Scenario).order_by(Scenario.id).all()
    return [_scenario_out(s) for s in rows]


@router.post("/scenarios", status_code=201, response_model=ScenarioOut)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)) -> ScenarioOut:
    overrides = payload.overrides.model_dump(exclude_none=True)
    _ensure_customers_exist(db, overrides)
    scenario = Scenario(
        name=payload.name,
        overrides_json=json.dumps(overrides, sort_keys=True),
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return _scenario_out(scenario)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)) -> Response:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    db.delete(scenario)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- alerts / chase / insights

@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    today = date.today()
    data = _load_inputs(db, today)
    baseline = _run_forecast(data, today, FORECAST_BASELINE_DAYS, {})
    overdue = build_overdue_list(data["invoices"], today)
    return build_alerts(today, overdue, baseline, data["safe"])


@router.get("/chase-list")
def get_chase_list(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    today = date.today()
    data = _load_inputs(db, today)
    rows = build_overdue_list(data["invoices"], today)[:CHASE_LIMIT]
    symbol = data["currency_symbol"]
    out: List[Dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        message = _chase_message(row, data["business_name"], symbol)
        phone = row["customer_phone"]
        out.append({
            **row,
            "priority_rank": rank,
            "tone": _tone_for(int(row["days_overdue"])),
            "message": message,
            "whatsapp_url": "https://wa.me/%s?text=%s" % (phone, urllib.parse.quote(message)),
        })
    return out


@router.get("/insights")
def get_insights_route(db: Session = Depends(get_db)) -> Dict[str, Any]:
    today = date.today()
    data = _load_inputs(db, today)
    baseline = _run_forecast(data, today, FORECAST_BASELINE_DAYS, {})
    overdue = build_overdue_list(data["invoices"], today)
    aging = aging_summary(data["invoices"], today)
    return get_insights(overdue, baseline, aging, data["safe"])
