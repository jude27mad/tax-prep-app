from __future__ import annotations

from dataclasses import dataclass

from app.tax.ca2025 import Bracket, tax_from_brackets as _tax_from_brackets
from app.tax.prov.base import ProvincialAdapter, basic_personal_amount


@dataclass(frozen=True)
class OntarioSurtaxThreshold:
    threshold: float
    rate: float


ONTARIO_2025 = (
    Bracket(52_886, 0.0505),
    Bracket(105_775, 0.0915),
    Bracket(150_000, 0.1116),
    Bracket(220_000, 0.1216),
    Bracket(None, 0.1316),
)

ON_BPA_2025 = 12_747.0
ON_CREDIT_RATE = 0.0505

_SURTAX_BRACKETS = (
    OntarioSurtaxThreshold(5_710.0, 0.20),
    OntarioSurtaxThreshold(7_307.0, 0.36),
)


def tax_from_brackets(taxable: float, brackets: tuple[Bracket, ...] = ONTARIO_2025) -> float:
    return _tax_from_brackets(taxable, brackets)


def health_premium_2025(taxable: float) -> float:
    t = taxable
    if t <= 20_000:
        return 0.0
    if t <= 36_000:
        return round(min(300.0, 0.06 * (t - 20_000)), 2)
    if t <= 48_000:
        return round(min(450.0, 300.0 + 0.06 * (t - 36_000)), 2)
    if t <= 72_000:
        return round(min(600.0, 450.0 + 0.25 * (t - 48_000)), 2)
    if t <= 200_000:
        return round(min(750.0, 600.0 + 0.25 * (t - 72_000)), 2)
    return round(min(900.0, 750.0 + 0.25 * (t - 200_000)), 2)


def surtax_2025(after_credits: float) -> float:
    t = after_credits
    if t <= _SURTAX_BRACKETS[0].threshold:
        return 0.0
    first = _SURTAX_BRACKETS[0].rate * (min(t, _SURTAX_BRACKETS[1].threshold) - _SURTAX_BRACKETS[0].threshold)
    if t <= _SURTAX_BRACKETS[1].threshold:
        return round(first, 2)
    second = _SURTAX_BRACKETS[1].rate * (t - _SURTAX_BRACKETS[1].threshold)
    return round(first + second, 2)


def _additions(taxable: float, after: float) -> dict[str, float]:
    return {
        "surtax": surtax_2025(after),
        "health_premium": health_premium_2025(taxable),
    }


adapter = ProvincialAdapter(
    code="ON",
    name="Ontario",
    brackets=ONTARIO_2025,
    credit_rate=ON_CREDIT_RATE,
    bpa_fn=basic_personal_amount(ON_BPA_2025),
    additions_fn=_additions,
)
