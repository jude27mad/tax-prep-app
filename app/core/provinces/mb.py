from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


MB_BRACKETS_2025 = [
    (D("0"), D("47000"), D("0.1080")),
    (D("47000"), D("100000"), D("0.1275")),
    (D("100000"), None, D("0.1740")),
]

MB_NRTC_RATE_2025 = D("0.1080")
MB_BPA_2025 = D("15780")


def mb_tax_on_taxable_income_2025(taxable_income: D) -> D:
    return calculate_progressive_tax(MB_BRACKETS_2025, taxable_income)


def mb_credits_2025() -> D:
    return basic_personal_credit(MB_BPA_2025, MB_NRTC_RATE_2025)


def mb_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
