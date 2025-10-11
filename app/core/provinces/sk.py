from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal


SK_BRACKETS_2024 = [
    (D("0"), D("52057"), D("0.1050")),
    (D("52057"), D("148734"), D("0.1250")),
    (D("148734"), None, D("0.1450")),
]

SK_NRTC_RATE_2024 = D("0.1050")
SK_BPA_2024 = D("18861")


def sk_tax_on_taxable_income_2024(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in SK_BRACKETS_2024:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def sk_credits_2024() -> D:
    return (SK_BPA_2024 * SK_NRTC_RATE_2024).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def sk_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
