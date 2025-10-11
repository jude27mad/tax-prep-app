from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

D = Decimal
Bracket = tuple[D, D | None, D]


def calculate_progressive_tax(brackets: Sequence[Bracket], taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in brackets:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def basic_personal_credit(bpa: D, rate: D) -> D:
    credit = bpa * rate
    return credit.quantize(D("0.01"), rounding=ROUND_HALF_UP)
