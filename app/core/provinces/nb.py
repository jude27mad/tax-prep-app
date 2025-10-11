from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


NB_BRACKETS_2024 = [
    (D("0"), D("49958"), D("0.0940")),
    (D("49958"), D("99916"), D("0.1400")),
    (D("99916"), D("185064"), D("0.1600")),
    (D("185064"), None, D("0.1900")),
]

NB_NRTC_RATE_2024 = D("0.0940")
NB_BPA_2024 = D("12623")


def nb_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NB_BRACKETS_2024, taxable_income)


def nb_credits_2024() -> D:
    return basic_personal_credit(NB_BPA_2024, NB_NRTC_RATE_2024)


def nb_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
