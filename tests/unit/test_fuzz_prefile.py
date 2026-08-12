from decimal import Decimal

import hypothesis.strategies as st
from hypothesis import given

from app.core.tax_years._2025_alias import compute_return
from app.efile.service import PrefileValidationError, enforce_prefile_gates
from tests.fixtures.min_client import make_min_input


@given(st.integers(min_value=0, max_value=200000))
def test_random_income_passes_prefile(amount: int):
    req = make_min_input()
    req.slips_t4[0].employment_income = Decimal(amount)
    calc = compute_return(req)
    try:
        enforce_prefile_gates(req, calc)
    except PrefileValidationError as exc:
        assert False, f"Unexpected validation error for income {amount}: {exc.issues}"


@given(st.integers(max_value=-1))
def test_negative_income_rejected(amount: int):
    """Negative slip income is rejected as a bad *input*.

    This previously asserted code 30010 ("taxable income cannot be negative"),
    which only fired because a negative slip dragged the computed total below
    zero. That was an accidental backstop: the gate never validated the slips at
    all, because ``enforce_prefile_gates`` built its payload without them.

    Now the line architecture floors taxable income at zero (a T1 cannot report
    negative taxable income), so the derived signal is gone and the input check
    is the real one — code 60011, on the offending field.
    """
    req = make_min_input()
    req.slips_t4[0].employment_income = Decimal(amount)
    calc = compute_return(req)
    try:
        enforce_prefile_gates(req, calc)
    except PrefileValidationError as exc:
        codes = [issue.code for issue in exc.issues]
        assert "60011" in codes, f"expected T4 negative-amount code, got {codes}"
        fields = [issue.field for issue in exc.issues if issue.code == "60011"]
        assert "slips_t4[0].employment_income" in fields, fields
    else:
        assert False, "Negative income should fail validation"


@given(st.integers(max_value=-1))
def test_negative_income_never_yields_negative_taxable_income(amount: int):
    """Flooring guarantee: bad input cannot produce an impossible T1 line."""
    req = make_min_input()
    req.slips_t4[0].employment_income = Decimal(amount)
    calc = compute_return(req)
    assert calc.line_items["net_income"] >= 0
    assert calc.line_items["taxable_income"] >= 0
