from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.core.models import ReturnCalc, ReturnInput
from app.core.slips import (
    sum_rrsp_contributions,
    sum_t4a_income,
    sum_t5_income,
)
from app.core.slips import t4 as t4mod
from app.core.provinces import get_provincial_calculator
from app.core.tax_years.y2024.federal import federal_nrtcs_2024, federal_tax_2024

D = Decimal


@dataclass(frozen=True)
class TaxBreakdown2024:
    federal_tax: D
    federal_credits: D
    provincial_tax: D
    provincial_credits: D
    provincial_additions: Mapping[str, D]
    total_payable: D

    @property
    def ontario_surtax(self) -> D:
        return self.provincial_additions.get("ontario_surtax", D("0.00"))

    @property
    def ontario_health_premium(self) -> D:
        return self.provincial_additions.get("ontario_health_premium", D("0.00"))


def compute_full_2024(
    taxable_income: D,
    net_income: D,
    personal_credit_amounts: dict[str, D] | None = None,
    province: str | None = None,
) -> TaxBreakdown2024:
    f_tax = federal_tax_2024(taxable_income)
    f_credits = federal_nrtcs_2024(net_income, personal_credit_amounts or {})
    calculator = get_provincial_calculator(2024, province)
    prov_tax = calculator.tax(taxable_income)
    prov_creds = calculator.credits()
    additions = dict(calculator.additions(taxable_income, prov_tax, prov_creds))
    prov_payable = max(D("0"), prov_tax - prov_creds)
    additions_total = sum(additions.values(), D("0.00"))
    total = max(D("0"), f_tax - f_credits) + prov_payable + additions_total
    return TaxBreakdown2024(
        federal_tax=f_tax,
        federal_credits=f_credits,
        provincial_tax=prov_tax,
        provincial_credits=prov_creds,
        provincial_additions=additions,
        total_payable=total.quantize(D("0.01")),
    )


def compute_return(in_: ReturnInput) -> ReturnCalc:
    employment_income = t4mod.sum_employment_income(in_.slips_t4)
    t4a_income = sum_t4a_income(in_.slips_t4a)
    t5_income = sum_t5_income(in_.slips_t5)
    total_income = employment_income + t4a_income + t5_income
    rrsp_deductions = in_.rrsp_contrib + sum_rrsp_contributions(in_.rrsp_receipts)
    taxable_income = total_income - rrsp_deductions
    breakdown = compute_full_2024(taxable_income, total_income, province=in_.province)
    cpp = t4mod.compute_cpp_2024(in_.slips_t4)
    ei = t4mod.compute_ei_2024(in_.slips_t4)

    line_items = {
        "income_total": total_income,
        "taxable_income": taxable_income,
        "federal_tax": breakdown.federal_tax,
        "prov_tax": breakdown.provincial_tax,
    }
    if breakdown.provincial_additions:
        line_items.update(breakdown.provincial_additions)
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
