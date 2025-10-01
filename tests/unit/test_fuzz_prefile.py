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
    req = make_min_input()
    req.slips_t4[0].employment_income = Decimal(amount)
    calc = compute_return(req)
    try:
        enforce_prefile_gates(req, calc)
    except PrefileValidationError as exc:
        codes = [issue.code for issue in exc.issues]
        assert "30010" in codes
    else:
        assert False, "Negative income should fail validation"
