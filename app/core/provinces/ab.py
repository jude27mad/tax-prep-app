from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal


AB_BRACKETS_2025 = [
    (D("0"), D("148269"), D("0.10")),
    (D("148269"), D("177922"), D("0.12")),
    (D("177922"), D("237230"), D("0.13")),
    (D("237230"), D("355845"), D("0.14")),
    (D("355845"), None, D("0.15")),
]

AB_NRTC_RATE_2025 = D("0.10")
AB_BPA_2025 = D("21885")


def ab_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in AB_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def ab_credits_2025() -> D:
    return (AB_BPA_2025 * AB_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def ab_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
