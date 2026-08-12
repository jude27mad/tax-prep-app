from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.core.computation import TaxComputation
from app.core.lines import compute_income_lines
from app.core.models import ReturnCalc, ReturnInput
from app.core.slips import (
    sum_rrsp_contributions,
    sum_t4a_income,
    sum_t4a_tax_deducted,
    sum_t5_income,
)
from app.core.slips import t4 as t4mod
from app.core.provinces import get_provincial_calculator
from app.core.tax_years.y2024.federal import (
    federal_bpa_2024,
    federal_nrtcs_2024,
    federal_tax_2024,
)

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


def compute_from_amounts(
    total_income: D,
    division_b_deductions: D,
    *,
    province: str | None = None,
    withholding: D = D("0.00"),
    division_c_deductions: D = D("0.00"),
    tax_year: int = 2024,
) -> TaxComputation:
    """The one 2024 tax computation, expressed over plain amounts.

    Mirrors :func:`app.core.tax_years.y2025.calc.compute_from_amounts`; see that
    docstring for why the entry point is amount-shaped rather than
    :class:`~app.core.models.ReturnInput`-shaped.
    """
    # See app.core.lines: net income (not total income) drives income-tested
    # amounts such as the BPA phase-out.
    lines = compute_income_lines(
        total_income=total_income,
        division_b_deductions=division_b_deductions,
        division_c_deductions=division_c_deductions,
    )

    breakdown = compute_full_2024(
        lines.taxable_income,
        lines.net_income,
        province=province,
    )
    calculator = get_provincial_calculator(2024, province)

    net_federal_tax = max(D("0.00"), breakdown.federal_tax - breakdown.federal_credits)
    net_provincial_tax = (
        max(D("0.00"), breakdown.provincial_tax - breakdown.provincial_credits)
        + sum(breakdown.provincial_additions.values(), D("0.00"))
    ).quantize(D("0.01"))

    # Positive: balance owing (line 48500). Negative: refund (line 48400).
    balance = breakdown.total_payable - withholding

    return TaxComputation(
        tax_year=tax_year,
        province=calculator.code or (province or "ON").upper(),
        lines=lines,
        federal_bpa=federal_bpa_2024(lines.net_income),
        federal_tax=breakdown.federal_tax,
        federal_credits=breakdown.federal_credits,
        net_federal_tax=net_federal_tax,
        provincial_bpa=min(calculator.bpa, lines.taxable_income),
        provincial_tax=breakdown.provincial_tax,
        provincial_credits=breakdown.provincial_credits,
        provincial_additions=dict(breakdown.provincial_additions),
        net_provincial_tax=net_provincial_tax,
        net_tax=breakdown.total_payable,
        withholding=withholding,
        balance=balance,
    )


def compute_return(in_: ReturnInput) -> ReturnCalc:
    """Adapt a full :class:`ReturnInput` into the shared 2024 computation."""
    employment_income = t4mod.sum_employment_income(in_.slips_t4)
    t4a_income = sum_t4a_income(in_.slips_t4a)
    t5_income = sum_t5_income(in_.slips_t5)
    total_income = employment_income + t4a_income + t5_income
    rrsp_deductions = in_.rrsp_contrib + sum_rrsp_contributions(in_.rrsp_receipts)

    # T4 box 22 + T4A box 22 (CRA line 43700). T5's foreign_tax_withheld is
    # foreign-tax-credit territory (line 40500), not domestic withholding, and
    # is deliberately excluded -- see sum_t4a_tax_deducted.
    withholding = t4mod.sum_tax_deducted(in_.slips_t4) + sum_t4a_tax_deducted(in_.slips_t4a)

    computation = compute_from_amounts(
        total_income,
        rrsp_deductions,
        province=in_.province,
        withholding=withholding,
        tax_year=in_.tax_year,
    )

    return ReturnCalc(
        tax_year=in_.tax_year,
        province=in_.province,
        line_items=computation.as_line_items(),
        totals=computation.as_totals(),
        cpp=t4mod.compute_cpp_2024(in_.slips_t4),
        ei=t4mod.compute_ei_2024(in_.slips_t4),
        provincial_additions=dict(computation.provincial_additions),
    )
