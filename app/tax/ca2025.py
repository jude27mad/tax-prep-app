from dataclasses import dataclass

@dataclass(frozen=True)
class Bracket:
    up_to: float | None
    rate: float

# Federal brackets (2025, effective 14.5% lowest rate)
FEDERAL_2025 = [
    Bracket(57375, 0.145),
    Bracket(114750, 0.205),
    Bracket(177882, 0.26),
    Bracket(253414, 0.29),
    Bracket(None, 0.33),
]

FED_CREDIT_RATE = 0.145  # same as lowest rate in 2025
FED_BPA_BASE = 14538.0
FED_BPA_MAX  = 16129.0   # base + additional amount
# The additional amount phases out between 177,882 and 253,414
def federal_bpa_2025(net_income: float) -> float:
    base = FED_BPA_BASE
    extra = FED_BPA_MAX - FED_BPA_BASE  # 1,591
    if net_income <= 177_882:
        return FED_BPA_MAX
    if net_income >= 253_414:
        return base
    frac = (net_income - 177_882) / (253_414 - 177_882)
    return round(base + extra * (1 - frac), 2)

def tax_from_brackets(taxable: float, brackets) -> float:
    tax, prev = 0.0, 0.0
    for b in brackets:
        cap = taxable if b.up_to is None else min(taxable, b.up_to)
        amt = max(0.0, cap - prev)
        tax += amt * b.rate
        prev = b.up_to if b.up_to is not None else taxable
        if prev >= taxable:
            break
    return round(tax, 2)
