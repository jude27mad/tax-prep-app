"""Withholding and refund/balance owing (Plan V3 execution roadmap PR 5).

Covers app.core.tax_years.{y2024,y2025}.calc.compute_return's addition of
ReturnCalc.totals["withholding"] and ["balance"]: T4 + T4A box 22 income tax
deducted, netted against total tax payable to produce a signed balance
(positive = balance owing, CRA line 48500; negative = refund, line 48400).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.lines import BALANCE_OWING_LINE_NUMBER, CRA_LINE_NUMBERS, REFUND_LINE_NUMBER
from app.core.models import (
    ReturnInput,
    T4ASlip,
    T4Slip,
    T5Slip,
    Taxpayer,
)
from app.core.tax_years.y2024.calc import compute_return as compute_2024
from app.core.tax_years.y2025.calc import compute_return as compute_2025

D = Decimal


def _taxpayer() -> Taxpayer:
    return Taxpayer(
        sin="000000000",
        first_name="With",
        last_name="Holding",
        dob="1980-01-01",
        address_line1="1 Main St",
        city="Toronto",
        province="ON",
        postal_code="M1M1M1",
        residency_status="resident",
    )


def _input(
    *,
    t4_income: str = "50000.00",
    t4_tax_deducted: str | None = None,
    t4a_tax_deducted: str | None = None,
    t5_foreign_tax_withheld: str | None = None,
    tax_year: int = 2025,
) -> ReturnInput:
    slips_t4a = []
    if t4a_tax_deducted is not None:
        slips_t4a = [T4ASlip(pension_income=D("0.00"), tax_deducted=D(t4a_tax_deducted))]
    slips_t5 = []
    if t5_foreign_tax_withheld is not None:
        slips_t5 = [
            T5Slip(
                interest_income=D("0.00"),
                foreign_income=D("100.00"),
                foreign_tax_withheld=D(t5_foreign_tax_withheld),
            )
        ]
    return ReturnInput(
        taxpayer=_taxpayer(),
        slips_t4=[
            T4Slip(
                employment_income=D(t4_income),
                tax_deducted=D(t4_tax_deducted) if t4_tax_deducted is not None else None,
            )
        ],
        slips_t4a=slips_t4a,
        slips_t5=slips_t5,
        province="ON",
        tax_year=tax_year,
    )


@pytest.mark.parametrize(
    ("compute", "tax_year"), [(compute_2025, 2025), (compute_2024, 2024)]
)
class TestWithholdingAndBalance:
    """Both year handlers share the same withholding/balance contract."""

    def test_withholding_sums_t4_and_t4a_tax_deducted(self, compute, tax_year):
        calc = compute(
            _input(
                t4_tax_deducted="4000.00",
                t4a_tax_deducted="500.00",
                tax_year=tax_year,
            )
        )
        assert calc.totals["withholding"] == D("4500.00")

    def test_t5_foreign_tax_withheld_is_excluded_from_withholding(self, compute, tax_year):
        # foreign_tax_withheld feeds the foreign tax credit (line 40500), not
        # domestic withholding netted against balance owing. Including it here
        # would understate balance owing / overstate refund.
        calc = compute(
            _input(
                t4_tax_deducted="4000.00",
                t5_foreign_tax_withheld="200.00",
                tax_year=tax_year,
            )
        )
        assert calc.totals["withholding"] == D("4000.00")

    def test_withholding_defaults_to_zero_with_no_slips_reporting_it(self, compute, tax_year):
        calc = compute(_input(tax_year=tax_year))
        assert calc.totals["withholding"] == D("0.00")

    def test_balance_is_net_tax_minus_withholding(self, compute, tax_year):
        calc = compute(_input(t4_income="50000.00", t4_tax_deducted="1.00", tax_year=tax_year))
        assert calc.totals["balance"] == calc.totals["net_tax"] - calc.totals["withholding"]

    def test_over_withholding_produces_a_negative_balance_ie_a_refund(self, compute, tax_year):
        # A modest income with large withholding must land in refund territory.
        calc = compute(
            _input(t4_income="20000.00", t4_tax_deducted="10000.00", tax_year=tax_year)
        )
        assert calc.totals["balance"] < 0
        assert calc.totals["balance"] == calc.totals["net_tax"] - D("10000.00")

    def test_under_withholding_produces_a_positive_balance_owing(self, compute, tax_year):
        calc = compute(
            _input(t4_income="120000.00", t4_tax_deducted="0.00", tax_year=tax_year)
        )
        assert calc.totals["balance"] > 0
        assert calc.totals["balance"] == calc.totals["net_tax"]

    def test_exact_withholding_produces_a_zero_balance(self, compute, tax_year):
        calc = compute(_input(t4_income="50000.00", tax_year=tax_year))
        net_tax = calc.totals["net_tax"]
        exact = compute(
            _input(t4_income="50000.00", t4_tax_deducted=str(net_tax), tax_year=tax_year)
        )
        assert exact.totals["balance"] == D("0.00")


def test_withholding_has_a_cra_line_citation():
    assert CRA_LINE_NUMBERS["withholding"] == "43700"


def test_refund_and_balance_owing_are_distinct_lines():
    # Deliberately not in CRA_LINE_NUMBERS: which line applies depends on the
    # sign of totals["balance"], not a fixed key -- see app.core.lines.
    assert REFUND_LINE_NUMBER == "48400"
    assert BALANCE_OWING_LINE_NUMBER == "48500"
    assert REFUND_LINE_NUMBER != BALANCE_OWING_LINE_NUMBER
    assert "balance" not in CRA_LINE_NUMBERS
