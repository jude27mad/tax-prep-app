from __future__ import annotations

from decimal import Decimal
from typing import Sequence, Any

from app.core.models import RRSPReceipt, T4ASlip, T4ESlip, T5007Slip, T5Slip

FieldNames = tuple[str, ...]


def _sum_fields(slips: Sequence[Any], fields: FieldNames) -> Decimal:
    total = Decimal("0.00")
    for slip in slips:
        for field in fields:
            value = getattr(slip, field, None)
            if value:
                total += value
    return total


def sum_t4a_income(slips: Sequence[T4ASlip]) -> Decimal:
    return _sum_fields(
        slips,
        (
            "pension_income",
            "other_income",
            "self_employment_commissions",
            "research_grants",
        ),
    )


def sum_t5_income(slips: Sequence[T5Slip]) -> Decimal:
    return _sum_fields(
        slips,
        (
            "interest_income",
            "eligible_dividends",
            "other_dividends",
            "capital_gains",
            "foreign_income",
        ),
    )


def sum_rrsp_contributions(receipts: Sequence[RRSPReceipt]) -> Decimal:
    total = Decimal("0.00")
    for receipt in receipts:
        if receipt.contribution_amount:
            total += receipt.contribution_amount
    return total


def sum_t4a_tax_deducted(slips: Sequence[T4ASlip]) -> Decimal:
    """Income tax withheld at source across T4A box 22 (CRA line 43700).

    T5 slips carry ``foreign_tax_withheld`` instead, which is foreign-tax-credit
    territory (line 40500) and is not domestic withholding netted against
    balance owing here -- deliberately excluded.
    """
    return _sum_fields(slips, ("tax_deducted",))


def sum_t4e_income(slips: Sequence[T4ESlip]) -> Decimal:
    """T4E box 14 minus box 18, per slip (CRA line 11900).

    Box 18 (tax-exempt benefits, connected to a reserve under the Indian Act)
    is a subset of box 14 that CRA instructs be excluded from line 11900
    entirely -- unlike the T5007 line 25000 offset, which stays in net income
    and is only removed on the way to taxable income, box 18 never enters
    income at all. Netting per slip (not via _sum_fields, which only adds)
    keeps a slip's own exempt amount from ever appearing as taxable income
    even transiently.
    """
    total = Decimal("0.00")
    for slip in slips:
        benefits_paid = slip.benefits_paid or Decimal("0.00")
        tax_exempt = slip.tax_exempt_benefits or Decimal("0.00")
        total += benefits_paid - tax_exempt
    return total


def sum_t4e_tax_deducted(slips: Sequence[T4ESlip]) -> Decimal:
    """T4E box 22, income tax withheld at source (CRA line 43700)."""
    return _sum_fields(slips, ("tax_deducted",))


def sum_t5007_income(slips: Sequence[T5007Slip]) -> Decimal:
    """T5007 boxes 10 + 11: workers' compensation (14400) + social assistance
    (14500), included in total income before the line 25000 offset."""
    return _sum_fields(slips, ("workers_compensation", "social_assistance"))


def sum_t5007_offset(slips: Sequence[T5007Slip]) -> Decimal:
    """The line 25000 deduction: always equal to :func:`sum_t5007_income`.

    Workers' compensation and social assistance are included in total income
    and then deducted in full, so they are taxed at 0% while still counting
    toward net income for income-tested amounts. This is a Division C
    deduction -- it bridges net income to taxable income, not total income to
    net income -- and it is always the full T5007 amount, never a partial or
    claimed figure, unlike RRSP or tuition.
    """
    return sum_t5007_income(slips)
