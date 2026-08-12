"""T1 line architecture tests (see :mod:`app.core.lines`).

Covers the structural bridge total income → net income → taxable income, and the
regression that motivated it: both year handlers passed *total* income where
*net* income was expected, so the Basic Personal Amount phase-out was computed
against the wrong figure and overstated tax for anyone with deductions.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.lines import CRA_LINE_NUMBERS, compute_income_lines
from app.core.models import ReturnInput, RRSPReceipt, T4Slip, Taxpayer
from app.core.tax_years.y2024.calc import compute_return as compute_2024
from app.core.tax_years.y2025.calc import compute_return as compute_2025

D = Decimal


def _input(income: str, rrsp: str = "0.00", *, tax_year: int = 2025) -> ReturnInput:
    return ReturnInput(
        taxpayer=Taxpayer(
            sin="000000000",
            first_name="Line",
            last_name="Architecture",
            dob="1980-01-01",
            address_line1="1 Main St",
            city="Toronto",
            province="ON",
            postal_code="M1M1M1",
            residency_status="resident",
        ),
        slips_t4=[T4Slip(employment_income=D(income))],
        rrsp_receipts=[RRSPReceipt(contribution_amount=D(rrsp))] if rrsp != "0.00" else [],
        province="ON",
        tax_year=tax_year,
    )


# --- the structural bridge -------------------------------------------------


def test_bridge_total_to_net_to_taxable():
    lines = compute_income_lines(
        total_income=D("100000.00"),
        division_b_deductions=D("10000.00"),
        division_c_deductions=D("5000.00"),
    )
    assert lines.total_income == D("100000.00")
    assert lines.total_deductions == D("10000.00")
    assert lines.net_income == D("90000.00")
    assert lines.taxable_income == D("85000.00")


def test_net_and_taxable_are_equal_but_distinct_without_division_c():
    # Numerically equal today (no Division C deduction is modelled yet), but
    # they are separate lines and must both be reported. Collapsing them would
    # break the moment the line 25000 offset lands.
    lines = compute_income_lines(
        total_income=D("50000.00"), division_b_deductions=D("5000.00")
    )
    assert lines.net_income == lines.taxable_income == D("45000.00")
    assert "net_income" in lines.as_line_items()
    assert "taxable_income" in lines.as_line_items()


@pytest.mark.parametrize(
    ("total", "div_b", "div_c"),
    [
        ("1000.00", "5000.00", "0.00"),  # deduction exceeds income
        ("0.00", "0.00", "0.00"),
        ("1000.00", "0.00", "5000.00"),  # Division C exceeds net income
    ],
)
def test_lines_never_go_negative(total, div_b, div_c):
    # A T1 cannot report negative net or taxable income, and a negative figure
    # must never reach the bracket or phase-out arithmetic.
    lines = compute_income_lines(
        total_income=D(total),
        division_b_deductions=D(div_b),
        division_c_deductions=D(div_c),
    )
    assert lines.net_income >= 0
    assert lines.taxable_income >= 0


def test_cra_line_numbers_cover_the_emitted_lines():
    # The explanation engine cites these, so every structural line needs one.
    emitted = set(
        compute_income_lines(D("1.00"), D("0.00")).as_line_items()
    )
    assert emitted <= set(CRA_LINE_NUMBERS)
    assert CRA_LINE_NUMBERS["net_income"] == "23600"
    assert CRA_LINE_NUMBERS["taxable_income"] == "26000"
    assert CRA_LINE_NUMBERS["income_total"] == "15000"


# --- the regression: net income drives the BPA phase-out -------------------


@pytest.mark.parametrize(
    ("compute", "tax_year"), [(compute_2025, 2025), (compute_2024, 2024)]
)
def test_deductions_are_reflected_in_net_income(compute, tax_year):
    # Both year handlers emit the same line structure — that shared structure is
    # the point of app.core.lines. The rates differ; the lines do not.
    calc = compute(_input("100000.00", "10000.00", tax_year=tax_year))
    assert calc.tax_year == tax_year
    assert calc.line_items["income_total"] == D("100000.00")
    assert calc.line_items["total_deductions"] == D("10000.00")
    assert calc.line_items["net_income"] == D("90000.00")


def test_bpa_phase_out_uses_net_income_not_total_income():
    """The bug this PR fixes.

    Total income sits inside the BPA phase-out band; net income, after a large
    RRSP deduction, sits below it. The taxpayer is entitled to the *full* BPA.
    Passing total income as net income phased the BPA down and overstated tax.
    """
    from app.core.tax_years.y2025.federal import (
        BPA_FULL_2025,
        BPA_PHASE_START_2025,
        federal_bpa_2025,
    )

    total_income = D("200000.00")
    rrsp = D("30000.00")
    net_income = total_income - rrsp

    assert total_income > BPA_PHASE_START_2025, "fixture must start inside the band"
    assert net_income < BPA_PHASE_START_2025, "fixture must land below the band"

    # Full BPA at net income; a reduced one at total income.
    assert federal_bpa_2025(net_income) == BPA_FULL_2025
    assert federal_bpa_2025(total_income) < BPA_FULL_2025

    calc = compute_2025(_input(str(total_income), str(rrsp)))
    assert calc.line_items["net_income"] == net_income

    # The engine must have used the full BPA, so its federal tax is lower than
    # the old (total-income) behaviour by the phased-out credit amount.
    from app.core.tax_years.y2025.calc import compute_full_2025

    correct = compute_full_2025(net_income, net_income, province="ON")
    wrong = compute_full_2025(net_income, total_income, province="ON")
    assert correct.federal_credits > wrong.federal_credits
    assert correct.total_payable < wrong.total_payable
    assert calc.totals["net_tax"] == correct.total_payable


# --- provincial additions are declared, not inferred ----------------------


def test_provincial_additions_are_a_separate_field():
    # Consumers used to treat "any unrecognised line_items key" as a provincial
    # addition, which silently reclassified each new T1 line as one.
    calc = compute_2025(_input("90000.00"))
    assert "ontario_health_premium" in calc.provincial_additions
    assert "ontario_health_premium" not in calc.line_items
    assert not set(calc.provincial_additions) & set(calc.line_items)
