from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)

D = Decimal


SK_BRACKETS_2024 = [
    (D("0"), D("49720"), D("0.105")),
    (D("49720"), D("142058"), D("0.125")),
    (D("142058"), None, D("0.145")),
]

SK_NRTC_RATE_2024 = D("0.105")
SK_BPA_2024 = D("19715")


def sk_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(SK_BRACKETS_2024, taxable_income)


def sk_credits_2024() -> D:
    return basic_personal_credit(SK_BPA_2024, SK_NRTC_RATE_2024)


def sk_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}


SK_BRACKETS_2025 = [
    (D("0"), D("52057"), D("0.105")),
    (D("52057"), D("148734"), D("0.125")),
    (D("148734"), None, D("0.145")),
]

SK_NRTC_RATE_2025 = D("0.105")
SK_BPA_2025 = D("19936")


def sk_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in SK_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def sk_credits_2025() -> D:
    return (SK_BPA_2025 * SK_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def sk_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

