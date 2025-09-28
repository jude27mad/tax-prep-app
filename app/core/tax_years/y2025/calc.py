from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.models import ReturnCalc, ReturnInput
from app.core.slips import t4 as t4mod
from app.core.tax_years.y2025.federal import federal_nrtcs_2025, federal_tax_2025
from app.core.provinces.on import (
    on_health_premium_2025,
    on_credits_2025,
    on_surtax_2025,
    on_tax_on_taxable_income_2025,
)

D = Decimal


@dataclass(frozen=True)
class TaxBreakdown2025:
    federal_tax: D
    federal_credits: D
    provincial_tax: D
    provincial_credits: D
    ontario_surtax: D
    ontario_health_premium: D
    total_payable: D


def compute_full_2025(
    taxable_income: D,
    net_income: D,
    personal_credit_amounts: dict[str, D] | None = None,
) -> TaxBreakdown2025:
    f_tax = federal_tax_2025(taxable_income)
    f_credits = federal_nrtcs_2025(net_income, personal_credit_amounts or {})
    on_tax = on_tax_on_taxable_income_2025(taxable_income)
    on_creds = on_credits_2025()
    on_before_surtax = max(D("0"), on_tax - on_creds)
    on_surtax = on_surtax_2025(on_before_surtax)
    on_hp = on_health_premium_2025(taxable_income)
    total = max(D("0"), f_tax - f_credits) + on_before_surtax + on_surtax + on_hp
    return TaxBreakdown2025(
        federal_tax=f_tax,
        federal_credits=f_credits,
        provincial_tax=on_tax,
        provincial_credits=on_creds,
        ontario_surtax=on_surtax,
        ontario_health_premium=on_hp,
        total_payable=total.quantize(D("0.01")),
    )


def compute_return(in_: ReturnInput) -> ReturnCalc:
    income = t4mod.sum_employment_income(in_.slips_t4)
    taxable_income = income - in_.rrsp_contrib
    breakdown = compute_full_2025(taxable_income, income)
    cpp = t4mod.compute_cpp_2024(in_.slips_t4)
    ei = t4mod.compute_ei_2024(in_.slips_t4)
    line_items = {
        "income_total": income,
        "taxable_income": taxable_income,
        "federal_tax": breakdown.federal_tax,
        "prov_tax": breakdown.provincial_tax,
    }
    totals = {
        "net_tax": breakdown.total_payable,
    }
    return ReturnCalc(
        tax_year=in_.tax_year,
        province=in_.province,
        line_items=line_items,
        totals=totals,
        cpp=cpp,
        ei=ei,
    )
