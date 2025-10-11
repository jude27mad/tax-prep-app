from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


SK_BRACKETS_2024 = [
    (D("0"), D("52057"), D("0.1050")),
    (D("52057"), D("148734"), D("0.1250")),
    (D("148734"), None, D("0.1450")),
]

SK_NRTC_RATE_2024 = D("0.1050")
SK_BPA_2024 = D("18861")


def sk_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(SK_BRACKETS_2024, taxable_income)


def sk_credits_2024() -> D:
    return basic_personal_credit(SK_BPA_2024, SK_NRTC_RATE_2024)


def sk_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
