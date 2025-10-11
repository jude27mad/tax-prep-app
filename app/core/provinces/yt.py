from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)
from decimal import Decimal, ROUND_HALF_UP

D = Decimal


YT_BRACKETS_2024 = [
YT_BRACKETS_2025 = [
    (D("0"), D("55867"), D("0.0640")),
    (D("55867"), D("111733"), D("0.0900")),
    (D("111733"), D("173205"), D("0.1090")),
    (D("173205"), D("500000"), D("0.1280")),
    (D("500000"), None, D("0.1500")),
]

YT_NRTC_RATE_2024 = D("0.0640")
YT_BPA_2024 = D("15000")


def yt_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(YT_BRACKETS_2024, taxable_income)


def yt_credits_2024() -> D:
    return basic_personal_credit(YT_BPA_2024, YT_NRTC_RATE_2024)


def yt_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
YT_NRTC_RATE_2025 = D("0.0640")
YT_BPA_2025 = D("15000")


def yt_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in YT_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def yt_credits_2025() -> D:
    return (YT_BPA_2025 * YT_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def yt_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

