from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


AB_BRACKETS_2025 = [
    (D("0"), D("148269"), D("0.10")),
    (D("148269"), D("177922"), D("0.12")),
    (D("177922"), D("237230"), D("0.13")),
    (D("237230"), D("355845"), D("0.14")),
    (D("355845"), None, D("0.15")),
]

AB_NRTC_RATE_2025 = D("0.10")
AB_BPA_2025 = D("21885")


def ab_tax_on_taxable_income_2025(taxable_income: D) -> D:
    return calculate_progressive_tax(AB_BRACKETS_2025, taxable_income)


def ab_credits_2025() -> D:
    return basic_personal_credit(AB_BPA_2025, AB_NRTC_RATE_2025)


def ab_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
