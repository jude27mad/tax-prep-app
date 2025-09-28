from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

D = Decimal

BRACKETS_2024 = [
    (D("0"),       D("55867"),  D("0.15")),
    (D("55867"),   D("111733"), D("0.205")),
    (D("111733"),  D("173205"), D("0.26")),
    (D("173205"),  D("246752"), D("0.29")),
    (D("246752"),  None,        D("0.33")),
]

# Basic Personal Amount (BPA) 2024 with enhanced phase-out.
# Full BPA applies up to 173,205; linearly phases down to 14,156 at 246,752+.
BPA_FULL_2024 = D("15705")
BPA_FLOOR_2024 = D("14156")
BPA_PHASE_START = D("173205")
BPA_PHASE_END   = D("246752")
NRTC_RATE = D("0.15")  # federal non-refundable credit rate

def _clamp(x: D, lo: D, hi: D) -> D:
    return max(lo, min(hi, x))

def federal_bpa_2024(net_income: D) -> D:
    if net_income <= BPA_PHASE_START:
        return BPA_FULL_2024
    if net_income >= BPA_PHASE_END:
        return BPA_FLOOR_2024
    # linear interpolation
    ratio = (net_income - BPA_PHASE_START) / (BPA_PHASE_END - BPA_PHASE_START)
    return (BPA_FULL_2024 - ratio * (BPA_FULL_2024 - BPA_FLOOR_2024)).quantize(D("0.01"), rounding=ROUND_HALF_UP)

def federal_tax_2024(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in BRACKETS_2024:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)

def federal_nrtcs_2024(net_income: D, personal_credits: dict[str, D]) -> D:
    """
    Build total non-refundable tax credits at 15%:
      - BPA (computed via income phase-out)
      - Plus any other base amounts passed in personal_credits,
        e.g., age amount (if you wire it), CPP/EI, tuition, etc.
    """
    base = federal_bpa_2024(net_income)
    total_amount = base + sum((personal_credits or {}).values(), D("0"))
    return (total_amount * NRTC_RATE).quantize(D("0.01"), rounding=ROUND_HALF_UP)
