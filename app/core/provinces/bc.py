from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


BC_BRACKETS_2025 = [
    (D("0"), D("47937"), D("0.0506")),
    (D("47937"), D("95875"), D("0.0770")),
    (D("95875"), D("110076"), D("0.1050")),
    (D("110076"), D("133664"), D("0.1229")),
    (D("133664"), D("181232"), D("0.1470")),
    (D("181232"), None, D("0.1680")),
]

BC_NRTC_RATE_2025 = D("0.0506")
BC_BPA_2025 = D("12580")


def bc_tax_on_taxable_income_2025(taxable_income: D) -> D:
    return calculate_progressive_tax(BC_BRACKETS_2025, taxable_income)


def bc_credits_2025() -> D:
    return basic_personal_credit(BC_BPA_2025, BC_NRTC_RATE_2025)


def bc_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
