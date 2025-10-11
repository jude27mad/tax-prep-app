from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

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
NB_BPA_2024 = D("13044")


def nb_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NB_BRACKETS_2024, taxable_income)


def nb_credits_2024() -> D:
    return basic_personal_credit(NB_BPA_2024, NB_NRTC_RATE_2024)


def nb_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}


NB_BRACKETS_2025 = [
    (D("0"), D("49958"), D("0.0940")),
    (D("49958"), D("99916"), D("0.1400")),
    (D("99916"), D("185064"), D("0.1600")),
    (D("185064"), None, D("0.1900")),
]

NB_NRTC_RATE_2025 = D("0.0940")
NB_BPA_2025 = D("12758")


def nb_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in NB_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nb_credits_2025() -> D:
    return (NB_BPA_2025 * NB_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nb_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

