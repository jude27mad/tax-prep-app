"""Federal tax calculators for tax year 2024.

Brackets, Basic Personal Amount (with phase-out), and NRTC rate are loaded
from ``tax_rules/y2024/federal.toml`` via :mod:`app.core.rules`. Module-level
constant names (``BRACKETS_2024``, ``BPA_FULL_2024``, ``BPA_PHASE_START``,
etc.) match the historical hardcoded surface, so existing callers keep
working unchanged.

See strategy plan D1.2 / E6: rules-as-data migration with ITA / CRA guide
citations attached to every value.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.rules import load_federal_rules

D = Decimal

_RULES = load_federal_rules(2024)

BRACKETS_2024: list[tuple[Decimal, Decimal | None, Decimal]] = [
    (tier.lower, tier.upper, tier.rate) for tier in _RULES.brackets.tiers
]

BPA_FULL_2024 = _RULES.bpa.full
BPA_FLOOR_2024 = _RULES.bpa.floor
BPA_PHASE_START = _RULES.bpa.phase_start
BPA_PHASE_END = _RULES.bpa.phase_end
NRTC_RATE = _RULES.nrtc.rate


def _clamp(x: D, lo: D, hi: D) -> D:
    return max(lo, min(hi, x))


def federal_bpa_2024(net_income: D) -> D:
    if net_income <= BPA_PHASE_START:
        return BPA_FULL_2024
    if net_income >= BPA_PHASE_END:
        return BPA_FLOOR_2024
    ratio = (net_income - BPA_PHASE_START) / (BPA_PHASE_END - BPA_PHASE_START)
    return (BPA_FULL_2024 - ratio * (BPA_FULL_2024 - BPA_FLOOR_2024)).quantize(
        D("0.01"), rounding=ROUND_HALF_UP
    )


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
    """Build total non-refundable tax credits at the 2024 federal rate.

    Includes the BPA (with income phase-out) plus any base amounts passed in
    ``personal_credits`` (age amount, CPP/EI contributions, tuition, etc.).
    """
    base = federal_bpa_2024(net_income)
    total_amount = base + sum((personal_credits or {}).values(), D("0"))
    return (total_amount * NRTC_RATE).quantize(D("0.01"), rounding=ROUND_HALF_UP)
