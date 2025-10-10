from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal


MB_BRACKETS_2025 = [
    (D("0"), D("47000"), D("0.1080")),
    (D("47000"), D("100000"), D("0.1275")),
    (D("100000"), None, D("0.1740")),
]

MB_NRTC_RATE_2025 = D("0.1080")
MB_BPA_2025 = D("15780")


def mb_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in MB_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def mb_credits_2025() -> D:
    return (MB_BPA_2025 * MB_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def mb_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
