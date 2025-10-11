from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


PE_BRACKETS_2024 = [
    (D("0"), D("31984"), D("0.0965")),
    (D("31984"), D("63969"), D("0.1363")),
    (D("63969"), None, D("0.1665")),
]

PE_NRTC_RATE_2024 = D("0.0965")
PE_BPA_2024 = D("12750")


def pe_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(PE_BRACKETS_2024, taxable_income)


def pe_credits_2024() -> D:
    return basic_personal_credit(PE_BPA_2024, PE_NRTC_RATE_2024)


def pe_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
