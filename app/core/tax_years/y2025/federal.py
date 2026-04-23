"""Federal tax calculators for tax year 2025.

The brackets, Basic Personal Amount, and NRTC rate are loaded from
``tax_rules/y2025/federal.toml`` via :mod:`app.core.rules`. The module-level
constants exported here (``BRACKETS_2025``, ``BPA_FULL_2025``, etc.) preserve
the same names and shapes they had when the values were hardcoded, so
callers do not need to change.

See strategy plan D1.2 / E6: rules-as-data migration with ITA / CRA guide
citations attached to every value.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.rules import load_federal_rules

D = Decimal

_RULES = load_federal_rules(2025)

BRACKETS_2025: list[tuple[Decimal, Decimal | None, Decimal]] = [
    (tier.lower, tier.upper, tier.rate) for tier in _RULES.brackets.tiers
]

BPA_FULL_2025 = _RULES.bpa.full
BPA_FLOOR_2025 = _RULES.bpa.floor
BPA_PHASE_START_2025 = _RULES.bpa.phase_start
BPA_PHASE_END_2025 = _RULES.bpa.phase_end
NRTC_RATE_2025 = _RULES.nrtc.rate


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
