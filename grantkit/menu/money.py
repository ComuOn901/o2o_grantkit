"""Shared numeric formatting for budget output and gate messages."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext

Money = int | float | Decimal


def _is_finite(value: Money) -> bool:
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, int):
        return True
    return math.isfinite(value)


def round_half_up(value: Money) -> int:
    """Round to a whole dollar, half up (not banker's rounding)."""
    if not _is_finite(value):
        raise ValueError("money value must be finite")
    return int(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))


def format_money(value: Money, currency: str) -> str:
    """Format a finite value as whole currency units."""
    return f"{currency} {round_half_up(value):,}"


def format_percent(value: Money, places: int = 2) -> str:
    """Format a ratio as a bounded-precision, truthful percentage."""
    if not _is_finite(value):
        raise ValueError("percentage value must be finite")
    percent = Decimal(str(value)) * 100
    quantum = Decimal(1).scaleb(-places)
    if 0 < percent < quantum:
        return f"<{format(quantum, 'f')}%"
    if percent.adjusted() >= 9:
        return f"{percent:.3E}%"
    with localcontext() as context:
        context.prec = max(28, percent.adjusted() + places + 2)
        rounded = percent.quantize(quantum, rounding=ROUND_HALF_UP)
    if percent > 100 and rounded == 100:
        return ">100%"
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return f"{text}%"
