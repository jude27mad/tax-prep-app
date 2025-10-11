from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


NS_BRACKETS_2024 = [
    (D("0"), D("29590"), D("0.0879")),
    (D("29590"), D("59180"), D("0.1495")),
    (D("59180"), D("93000"), D("0.1667")),
    (D("93000"), D("150000"), D("0.1750")),
    (D("150000"), None, D("0.2100")),
]

NS_NRTC_RATE_2024 = D("0.0879")
NS_BPA_2024 = D("11481")


def ns_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NS_BRACKETS_2024, taxable_income)


def ns_credits_2024() -> D:
    return basic_personal_credit(NS_BPA_2024, NS_NRTC_RATE_2024)


def ns_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
