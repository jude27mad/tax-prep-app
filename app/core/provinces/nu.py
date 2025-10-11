from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)
from decimal import Decimal, ROUND_HALF_UP

D = Decimal


NU_BRACKETS_2024 = [
NU_BRACKETS_2025 = [
    (D("0"), D("53268"), D("0.0400")),
    (D("53268"), D("106537"), D("0.0700")),
    (D("106537"), D("172155"), D("0.0900")),
    (D("172155"), None, D("0.1150")),
]

NU_NRTC_RATE_2024 = D("0.0400")
NU_BPA_2024 = D("17925")


def nu_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NU_BRACKETS_2024, taxable_income)


def nu_credits_2024() -> D:
    return basic_personal_credit(NU_BPA_2024, NU_NRTC_RATE_2024)


def nu_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
NU_NRTC_RATE_2025 = D("0.0400")
NU_BPA_2025 = D("17925")


def nu_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in NU_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nu_credits_2025() -> D:
    return (NU_BPA_2025 * NU_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nu_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

