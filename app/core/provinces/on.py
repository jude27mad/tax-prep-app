from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

D = Decimal

# ------------------------------ 2024 ---------------------------------
ON_BRACKETS_2024 = [
    (D("0"),       D("51446"),  D("0.0505")),
    (D("51446"),   D("102894"), D("0.0915")),
    (D("102894"),  D("150000"), D("0.1116")),
    (D("150000"),  D("220000"), D("0.1216")),
    (D("220000"),  None,        D("0.1316")),
]

ON_NRTC_RATE_2024 = D("0.0505")
ON_BPA_2024 = D("12399")
SURTAX_T1_2024 = (D("5554"), D("0.20"))
SURTAX_T2_2024 = (D("7108"), D("0.36"))

OHP_STEPS_2024 = [
    (D("0"),      D("20000"),  lambda ti: D("0")),
    (D("20000"),  D("25000"),  lambda ti: (ti - D("20000")) * D("0.06")),
    (D("25000"),  D("36000"),  lambda ti: D("300")),
    (D("36000"),  D("38500"),  lambda ti: D("300") + (ti - D("36000")) * D("0.06")),
    (D("38500"),  D("48600"),  lambda ti: D("450")),
    (D("48600"),  D("72000"),  lambda ti: D("450") + (ti - D("48600")) * D("0.25")),
    (D("72000"),  D("200000"), lambda ti: D("600") + (ti - D("72000")) * D("0.25")),
    (D("200000"), D("220000"), lambda ti: D("750") + (ti - D("200000")) * D("0.25")),
    (D("220000"), None,         lambda ti: D("900")),
]


def on_tax_on_taxable_income_2024(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in ON_BRACKETS_2024:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_credits_2024() -> D:
    return (ON_BPA_2024 * ON_NRTC_RATE_2024).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_surtax_2024(ont_tax_before_surtax: D) -> D:
    s = D("0")
    if ont_tax_before_surtax > SURTAX_T1_2024[0]:
        s += (ont_tax_before_surtax - SURTAX_T1_2024[0]) * SURTAX_T1_2024[1]
    if ont_tax_before_surtax > SURTAX_T2_2024[0]:
        s += (ont_tax_before_surtax - SURTAX_T2_2024[0]) * SURTAX_T2_2024[1]
    return s.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_health_premium_2024(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    premium = D("0")
    for lo, hi, f in OHP_STEPS_2024:
        if ti > lo and (hi is None or ti <= hi):
            premium = f(ti)
            break
    return premium.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_additions_2024(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    on_before_surtax = max(D("0"), provincial_tax - provincial_credits)
    on_surtax = on_surtax_2024(on_before_surtax)
    on_hp = on_health_premium_2024(taxable_income)
    return {
        "ontario_surtax": on_surtax,
        "ontario_health_premium": on_hp,
    }


# ------------------------------ 2025 ---------------------------------
ON_BRACKETS_2025 = [
    (D("0"),       D("52886"),  D("0.0505")),
    (D("52886"),   D("105775"), D("0.0915")),
    (D("105775"),  D("150000"), D("0.1116")),
    (D("150000"),  D("220000"), D("0.1216")),
    (D("220000"),  None,        D("0.1316")),
]

ON_NRTC_RATE_2025 = D("0.0505")
ON_BPA_2025 = D("12747")
SURTAX_T1_2025 = (D("5710"), D("0.20"))
SURTAX_T2_2025 = (D("7307"), D("0.36"))


def on_tax_on_taxable_income_2025(taxable_income: D) -> D:
    ti = max(D("0"), taxable_income)
    tax = D("0")
    for lo, hi, rate in ON_BRACKETS_2025:
        upper = hi if hi is not None else ti
        if ti > lo:
            span = min(ti, upper) - lo
            if span > 0:
                tax += span * rate
        if hi is not None and ti <= hi:
            break
    return tax.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_credits_2025() -> D:
    return (ON_BPA_2025 * ON_NRTC_RATE_2025).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_surtax_2025(ont_tax_before_surtax: D) -> D:
    s = D("0")
    if ont_tax_before_surtax > SURTAX_T1_2025[0]:
        s += (ont_tax_before_surtax - SURTAX_T1_2025[0]) * SURTAX_T1_2025[1]
    if ont_tax_before_surtax > SURTAX_T2_2025[0]:
        s += (ont_tax_before_surtax - SURTAX_T2_2025[0]) * SURTAX_T2_2025[1]
    return s.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def on_health_premium_2025(taxable_income: D) -> D:
    # Reuse 2024 schedule until CRA publishes ON428 2025 updates.
    return on_health_premium_2024(taxable_income)


def on_additions_2025(
    taxable_income: D, provincial_tax: D, provincial_credits: D
) -> dict[str, D]:
    on_before_surtax = max(D("0"), provincial_tax - provincial_credits)
    on_surtax = on_surtax_2025(on_before_surtax)
    on_hp = on_health_premium_2025(taxable_income)
    return {
        "ontario_surtax": on_surtax,
        "ontario_health_premium": on_hp,
    }
