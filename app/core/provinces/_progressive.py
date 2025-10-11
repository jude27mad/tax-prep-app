from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

D = Decimal


@dataclass(frozen=True)
class TaxBracket:
    lower: D
    upper: D | None
    rate: D


def calculate_progressive_tax(
    brackets: Iterable[TaxBracket | tuple[D, D | None, D]],
    taxable_income: D,
) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for bracket in brackets:
        lower, upper, rate = bracket
        hi = upper if upper is not None else ti
        if ti > lower:
            span = min(ti, hi) - lower
            if span > 0:
                tax += span * rate
        if upper is not None and ti <= upper:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def basic_personal_credit(amount: D, rate: D) -> D:
    return (amount * rate).quantize(D("0.01"), rounding=ROUND_HALF_UP)


__all__ = [
    "TaxBracket",
    "calculate_progressive_tax",
    "basic_personal_credit",
]
