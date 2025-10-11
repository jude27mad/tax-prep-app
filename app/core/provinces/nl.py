from __future__ import annotations

from decimal import Decimal

from app.core.provinces._progressive import (
    basic_personal_credit,
    calculate_progressive_tax,
)
from decimal import Decimal, ROUND_HALF_UP

D = Decimal


NL_BRACKETS_2024 = [
    (D("0"), D("41457"), D("0.0870")),
    (D("41457"), D("82913"), D("0.1450")),
    (D("82913"), D("148027"), D("0.1580")),
    (D("148027"), D("207239"), D("0.1730")),
    (D("207239"), D("264750"), D("0.1830")),
    (D("264750"), D("529500"), D("0.1980")),
    (D("529500"), D("1059000"), D("0.2080")),
    (D("1059000"), None, D("0.2130")),
]

NL_NRTC_RATE_2024 = D("0.0870")
NL_BPA_2024 = D("10929")


def nl_tax_on_taxable_income_2024(taxable_income: D) -> D:
    return calculate_progressive_tax(NL_BRACKETS_2024, taxable_income)


def nl_credits_2024() -> D:
    return basic_personal_credit(NL_BPA_2024, NL_NRTC_RATE_2024)


def nl_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    return {}
NL_BRACKETS_2025 = [
    (D("0"), D("43198"), D("0.0870")),
    (D("43198"), D("86395"), D("0.1250")),
    (D("86395"), D("154244"), D("0.1330")),
    (D("154244"), D("196456"), D("0.1530")),
    (D("196456"), D("275862"), D("0.1730")),
    (D("275862"), D("551725"), D("0.1830")),
    (D("551725"), None, D("0.1980")),
]

NL_NRTC_RATE_2025 = D("0.0870")
NL_BPA_2025 = D("11866")


def nl_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in NL_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nl_credits_2025() -> D:
    return (NL_BPA_2025 * NL_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def nl_additions_2025(taxable_income: D, provincial_tax: D, provincial_credits: D) -> dict[str, D]:
    return {}

