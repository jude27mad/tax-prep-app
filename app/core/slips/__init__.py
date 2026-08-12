from __future__ import annotations

from decimal import Decimal
from typing import Sequence, Any

from app.core.models import RRSPReceipt, T4ASlip, T5Slip

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
