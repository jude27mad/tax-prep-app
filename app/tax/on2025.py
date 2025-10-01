from dataclasses import dataclass


@dataclass(frozen=True)
class Bracket:
    up_to: float | None
    rate: float


ONTARIO_2025 = [
    Bracket(52_886, 0.0505),
    Bracket(105_775, 0.0915),
    Bracket(150_000, 0.1116),
    Bracket(220_000, 0.1216),
    Bracket(None, 0.1316),
]

ON_BPA_2025 = 12_747.0
ON_CREDIT_RATE = 0.0505


def tax_from_brackets(taxable: float, brackets=ONTARIO_2025) -> float:
    tax = 0.0
    prev = 0.0
    for bracket in brackets:
        cap = taxable if bracket.up_to is None else min(taxable, bracket.up_to)
        amount = max(0.0, cap - prev)
        tax += amount * bracket.rate
        prev = bracket.up_to if bracket.up_to is not None else taxable
        if prev >= taxable:
            break
    return round(tax, 2)


def health_premium_2025(taxable: float) -> float:
    t = taxable
    if t <= 20_000:
        return 0.0
    if t <= 36_000:
        return min(300.0, 0.06 * (t - 20_000))
    if t <= 48_000:
        return min(450.0, 300.0 + 0.06 * (t - 36_000))
    if t <= 72_000:
        return min(600.0, 450.0 + 0.25 * (t - 48_000))
    if t <= 200_000:
        return min(750.0, 600.0 + 0.25 * (t - 72_000))
    return min(900.0, 750.0 + 0.25 * (t - 200_000))


def surtax_2025(ont_tax_after_credits: float) -> float:
    t = ont_tax_after_credits
    if t <= 5_710:
        return 0.0
    if t <= 7_307:
        return round(0.20 * (t - 5_710), 2)
    return round(0.20 * (7_307 - 5_710) + 0.36 * (t - 7_307), 2)
