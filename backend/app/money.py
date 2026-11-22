"""Decimal-safe money helpers. All amounts are integer minor units (paise)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

_PAISE = Decimal("0.01")


def to_minor(value: Union[float, str, Decimal]) -> int:
    """Convert a rupee amount (float or string) to integer paise, rounding half-up."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money amount: {value!r}") from exc
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_minor(amount_minor: int, symbol: str = "₹") -> str:
    """Format paise as a display string, e.g. 450000 -> '₹4,500.00', -120000 -> '-₹1,200.00'."""
    rupees = (Decimal(abs(int(amount_minor))) / 100).quantize(_PAISE, rounding=ROUND_HALF_UP)
    body = f"{symbol}{rupees:,.2f}"
    return f"-{body}" if amount_minor < 0 else body
