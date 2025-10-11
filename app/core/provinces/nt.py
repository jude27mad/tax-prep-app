from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


NT_BRACKETS_2024 = [
    (D("0"), D("50597"), D("0.0590")),
    (D("50597"), D("101198"), D("0.0860")),
    (D("101198"), D("164525"), D("0.1220")),
    (D("164525"), None, D("0.1405")),
]

NT_NRTC_RATE_2024 = D("0.0590")
NT_BPA_2024 = D("16593")


def nt_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NT_BRACKETS_2024, taxable_income)


def nt_credits_2024() -> D:
    return basic_personal_credit(NT_BPA_2024, NT_NRTC_RATE_2024)


def nt_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
