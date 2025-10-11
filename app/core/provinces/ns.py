from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal


NS_BRACKETS_2025 = [
    (D("0"), D("29590"), D("0.0879")),
    (D("29590"), D("59180"), D("0.1495")),
    (D("59180"), D("93000"), D("0.1667")),
    (D("93000"), D("150000"), D("0.1750")),
    (D("150000"), None, D("0.2100")),
]

NS_NRTC_RATE_2025 = D("0.0879")
NS_BPA_2025 = D("11481")


def ns_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in NS_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def ns_credits_2025() -> D:
    return (NS_BPA_2025 * NS_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def ns_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

