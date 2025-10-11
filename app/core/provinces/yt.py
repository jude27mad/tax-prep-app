from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


YT_BRACKETS_2024 = [
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
