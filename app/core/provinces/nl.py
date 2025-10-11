from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


NL_BRACKETS_2024 = [
    (D("0"), D("41457"), D("0.0870")),
    (D("41457"), D("82913"), D("0.1450")),
    (D("82913"), D("148027"), D("0.1580")),
    (D("148027"), D("207239"), D("0.1730")),
    (D("207239"), D("264750"), D("0.1830")),
    (D("264750"), D("529500"), D("0.1980")),
    (D("529500"), D("1059000"), D("0.2080")),
    (D("1059000"), None, D("0.2130")),
]

NL_NRTC_RATE_2024 = D("0.0870")
NL_BPA_2024 = D("10929")


def nl_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NL_BRACKETS_2024, taxable_income)


def nl_credits_2024() -> D:
    return basic_personal_credit(NL_BPA_2024, NL_NRTC_RATE_2024)


def nl_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
