"""Benchmark slip models: T4E, T5007, RC210 (Plan V3 execution roadmap PR 7).

The TY2025 benchmark return needs EI income (T4E), social assistance income
plus its line 25000 offset (T5007), and CWB advance reconciliation data
(RC210). T2202 already exists as ``TuitionSlip`` and needs no new model.

RC210 is captured here but deliberately not wired into any computation --
CWB/Schedule 6 reconciliation is later credit work (plan PR 11). T4E and
T5007 income *are* wired, because including a slip's income and applying its
one deterministic offset is not "credit work" in the sense the plan defers --
it is the same income-line plumbing T4/T4A/T5 already have.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.lines import CRA_LINE_NUMBERS
from app.core.models import (
    RC210Slip,
    ReturnInput,
    T4ESlip,
    T4Slip,
    T5007Slip,
    Taxpayer,
)
from app.core.slips import (
    sum_t4e_income,
    sum_t4e_tax_deducted,
    sum_t5007_income,
    sum_t5007_offset,
)
from app.core.tax_years.y2024.calc import compute_return as compute_2024
from app.core.tax_years.y2025.calc import compute_return as compute_2025
from app.core.validate.pre_submit import validate_return_input

D = Decimal


def _taxpayer() -> Taxpayer:
    return Taxpayer(
        sin="000000000",
        first_name="Benchmark",
        last_name="Slips",
        dob="1980-01-01",
        address_line1="1 Main St",
        city="Toronto",
        province="ON",
        postal_code="M1M1M1",
        residency_status="resident",
    )


def _input(
    *,
    t4_income: str = "0.00",
    t4e_benefits: str | None = None,
    t4e_tax_deducted: str | None = None,
    t4e_tax_exempt: str | None = None,
    t4e_repayment_rate: str | None = None,
    t4e_regular_benefits: str | None = None,
    t5007_wc: str | None = None,
    t5007_sa: str | None = None,
    tax_year: int = 2025,
) -> ReturnInput:
    slips_t4e = []
    if t4e_benefits is not None:
        slips_t4e = [
            T4ESlip(
                benefits_paid=D(t4e_benefits),
                tax_deducted=D(t4e_tax_deducted) if t4e_tax_deducted is not None else None,
                tax_exempt_benefits=D(t4e_tax_exempt) if t4e_tax_exempt is not None else None,
                repayment_rate=D(t4e_repayment_rate) if t4e_repayment_rate is not None else None,
                regular_benefits_paid=(
                    D(t4e_regular_benefits) if t4e_regular_benefits is not None else None
                ),
            )
        ]
    slips_t5007 = []
    if t5007_wc is not None or t5007_sa is not None:
        slips_t5007 = [
            T5007Slip(
                workers_compensation=D(t5007_wc) if t5007_wc is not None else None,
                social_assistance=D(t5007_sa) if t5007_sa is not None else None,
            )
        ]
    return ReturnInput(
        taxpayer=_taxpayer(),
        slips_t4=[T4Slip(employment_income=D(t4_income))] if t4_income != "0.00" else [],
        slips_t4e=slips_t4e,
        slips_t5007=slips_t5007,
        province="ON",
        tax_year=tax_year,
    )


# --- slip model basics ------------------------------------------------------


def test_t4e_slip_quantizes_amounts():
    slip = T4ESlip(benefits_paid=D("500"), tax_deducted=D("50"))
    assert slip.benefits_paid == D("500.00")
    assert slip.tax_deducted == D("50.00")


def test_t5007_slip_has_no_tax_deducted_box():
    slip = T5007Slip(workers_compensation=D("1000"), social_assistance=D("2000"))
    assert not hasattr(slip, "tax_deducted")


def test_rc210_slip_quantizes_amount():
    slip = RC210Slip(advance_cwb_payments=D("123.4"))
    assert slip.advance_cwb_payments == D("123.40")


# --- sum helpers -------------------------------------------------------------


def test_sum_t4e_income_and_tax_deducted():
    slips = [
        T4ESlip(benefits_paid=D("4000.00"), tax_deducted=D("300.00")),
        T4ESlip(benefits_paid=D("1000.00")),
    ]
    assert sum_t4e_income(slips) == D("5000.00")
    assert sum_t4e_tax_deducted(slips) == D("300.00")


def test_sum_t4e_income_nets_tax_exempt_benefits():
    # Box 18 is a subset of box 14 that CRA instructs be excluded from line
    # 11900 entirely -- unlike the T5007 line 25000 offset, it never reaches
    # income even transiently.
    slips = [
        T4ESlip(benefits_paid=D("4000.00"), tax_exempt_benefits=D("1500.00")),
        T4ESlip(benefits_paid=D("1000.00")),
    ]
    assert sum_t4e_income(slips) == D("3500.00")


def test_sum_t5007_income_combines_both_boxes():
    slips = [T5007Slip(workers_compensation=D("1000.00"), social_assistance=D("2500.00"))]
    assert sum_t5007_income(slips) == D("3500.00")


def test_sum_t5007_offset_equals_income():
    # The line 25000 offset is always the full T5007 total -- never a partial
    # or claimed amount, unlike RRSP or tuition.
    slips = [T5007Slip(workers_compensation=D("1000.00"), social_assistance=D("2500.00"))]
    assert sum_t5007_offset(slips) == sum_t5007_income(slips) == D("3500.00")


# --- wiring into compute_return: both year handlers share the contract -----


@pytest.mark.parametrize(
    ("compute", "tax_year"), [(compute_2025, 2025), (compute_2024, 2024)]
)
class TestT4EAndT5007Wiring:
    def test_t4e_income_reaches_total_income(self, compute, tax_year):
        calc = compute(_input(t4e_benefits="5000.00", tax_year=tax_year))
        assert calc.line_items["income_total"] == D("5000.00")

    def test_t4e_tax_deducted_reaches_withholding(self, compute, tax_year):
        calc = compute(
            _input(t4e_benefits="5000.00", t4e_tax_deducted="400.00", tax_year=tax_year)
        )
        assert calc.totals["withholding"] == D("400.00")

    def test_t4e_tax_exempt_benefits_are_excluded_from_total_income(self, compute, tax_year):
        # Box 18 never reaches income -- not net income, not taxable income --
        # unlike the T5007 line 25000 offset, which stays in net income.
        calc = compute(
            _input(t4e_benefits="5000.00", t4e_tax_exempt="2000.00", tax_year=tax_year)
        )
        assert calc.line_items["income_total"] == D("3000.00")
        assert calc.line_items["net_income"] == D("3000.00")
        assert calc.line_items["taxable_income"] == D("3000.00")

    def test_t5007_income_reaches_total_income(self, compute, tax_year):
        calc = compute(
            _input(t5007_wc="1000.00", t5007_sa="2000.00", tax_year=tax_year)
        )
        assert calc.line_items["income_total"] == D("3000.00")

    def test_t5007_offset_is_a_division_c_deduction(self, compute, tax_year):
        """The regression app.core.lines was built ahead of: net and taxable
        income diverge for the first time once a T5007 slip is present."""
        calc = compute(
            _input(t4_income="50000.00", t5007_wc="1000.00", t5007_sa="2000.00", tax_year=tax_year)
        )
        # Net income includes the T5007 amounts (still counted for
        # income-tested amounts); taxable income excludes them (taxed at 0%).
        assert calc.line_items["net_income"] == D("53000.00")
        assert calc.line_items["taxable_income"] == D("50000.00")
        assert calc.line_items["net_income"] != calc.line_items["taxable_income"]
        assert calc.line_items["division_c_deductions"] == D("3000.00")

    def test_no_t5007_slip_leaves_taxable_income_equal_to_net_income(
        self, compute, tax_year
    ):
        calc = compute(_input(t4_income="50000.00", tax_year=tax_year))
        assert calc.line_items["net_income"] == calc.line_items["taxable_income"]
        assert calc.line_items["division_c_deductions"] == D("0.00")


def test_division_c_deductions_has_a_cra_line_citation():
    assert CRA_LINE_NUMBERS["division_c_deductions"] == "25000"


# --- pre-submission validation: negative amounts are rejected --------------


def test_negative_t4e_benefits_paid_is_rejected():
    req = _input(t4e_benefits="-100.00")
    issues = validate_return_input(req)
    assert "t4e_negative_amount" in issues


def test_negative_t5007_amount_is_rejected():
    req = _input(t5007_wc="-1.00")
    issues = validate_return_input(req)
    assert "t5007_negative_amount" in issues


def test_negative_rc210_amount_is_rejected():
    req = _input()
    req.slips_rc210 = [RC210Slip(advance_cwb_payments=D("-1.00"))]
    issues = validate_return_input(req)
    assert "rc210_negative_amount" in issues


def test_t4e_tax_exempt_exceeding_benefits_paid_is_rejected():
    req = _input(t4e_benefits="1000.00", t4e_tax_exempt="1000.01")
    issues = validate_return_input(req)
    assert "t4e_tax_exempt_exceeds_benefits_paid" in issues


def test_t4e_repayment_indicators_are_rejected_as_unsupported():
    # Box 7 (repayment rate) against box 15 (regular benefits) signals the
    # line 23500/42200 social benefits repayment, which is not implemented --
    # this must be gated rather than silently omitted from balance owing.
    req = _input(
        t4e_benefits="20000.00",
        t4e_repayment_rate="30.00",
        t4e_regular_benefits="20000.00",
    )
    issues = validate_return_input(req)
    assert "t4e_repayment_unsupported" in issues


@pytest.mark.parametrize(
    ("repayment_rate", "regular_benefits"),
    [
        (None, "20000.00"),  # no rate quoted -- no repayment signalled
        ("30.00", None),  # no regular-benefits figure to apply the rate to
        ("0.00", "20000.00"),  # explicit zero rate
        ("30.00", "0.00"),  # explicit zero regular benefits
    ],
)
def test_t4e_without_both_repayment_indicators_is_not_gated(
    repayment_rate, regular_benefits
):
    req = _input(
        t4e_benefits="20000.00",
        t4e_repayment_rate=repayment_rate,
        t4e_regular_benefits=regular_benefits,
    )
    issues = validate_return_input(req)
    assert "t4e_repayment_unsupported" not in issues
