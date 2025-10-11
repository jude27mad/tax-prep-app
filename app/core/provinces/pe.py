from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal


PE_BRACKETS_2025 = [
    (D("0"), D("35812"), D("0.0965")),
    (D("35812"), D("71625"), D("0.1363")),
    (D("71625"), None, D("0.1665")),
]

PE_NRTC_RATE_2025 = D("0.0965")
PE_BPA_2025 = D("13500")


def pe_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in PE_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def pe_credits_2025() -> D:
    return (PE_BPA_2025 * PE_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def pe_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

