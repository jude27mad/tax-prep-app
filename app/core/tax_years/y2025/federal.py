from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

D = Decimal

BRACKETS_2025 = [
    (D("0"),       D("57375"),  D("0.145")),
    (D("57375"),   D("114750"), D("0.205")),
    (D("114750"),  D("177882"), D("0.26")),
    (D("177882"),  D("253414"), D("0.29")),
    (D("253414"),  None,        D("0.33")),
]

BPA_FULL_2025 = D("16129")
BPA_FLOOR_2025 = D("14538")
BPA_PHASE_START_2025 = D("177882")
BPA_PHASE_END_2025 = D("253414")
NRTC_RATE_2025 = D("0.145")


def federal_bpa_2025(net_income: D) -> D:
    if net_income <= BPA_PHASE_START_2025:
        return BPA_FULL_2025
    if net_income >= BPA_PHASE_END_2025:
        return BPA_FLOOR_2025
    ratio = (net_income - BPA_PHASE_START_2025) / (BPA_PHASE_END_2025 - BPA_PHASE_START_2025)
    amount = BPA_FULL_2025 - ratio * (BPA_FULL_2025 - BPA_FLOOR_2025)
    return amount.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def federal_tax_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def federal_nrtcs_2025(net_income: D, personal_credits: dict[str, D]) -> D:
    base = federal_bpa_2025(net_income)
    total_amount = base + sum((personal_credits or {}).values(), D("0"))
    return (total_amount * NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)
