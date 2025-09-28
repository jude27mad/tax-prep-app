from app.core.validate.pre_submit import validate_return_input, validate_before_efile, Identity
from tests.fixtures.min_client import make_min_input


def test_validate_ok():
  issues = validate_return_input(make_min_input())
  assert issues == []


def test_validate_postal_and_year():
  payload = make_min_input(tax_year=2026)
  payload.taxpayer.postal_code = "123456"
  issues = validate_return_input(payload)
  assert "invalid_postal_code" in issues
  assert "unsupported_year" in issues


def test_validate_before_efile_requires_t183():
  identity = Identity(
    sin="123456789",
    first_name="Test",
    last_name="User",
    dob_yyyy_mm_dd="1990-01-01",
    address_line1="1 Main St",
    city="Toronto",
    province="ON",
    postal_code="M1M1M1",
  )
  issues = validate_before_efile(identity, {"taxable_income": "1000"})
  codes = {issue.code for issue in issues}
  assert "50010" in codes


def test_validate_before_efile_bad_postal():
  identity = Identity(
    sin="12345678A",
    first_name=" ",
    last_name="User",
    dob_yyyy_mm_dd="1990-31-01",
    address_line1=" ",
    city="",
    province="XX",
    postal_code="123456",
  )
  issues = validate_before_efile(identity, {"taxable_income": "-1", "t183_signed_ts": ""})
  codes = {issue.code for issue in issues}
  assert "10001" in codes
  assert "10002" in codes
  assert "10003" in codes
  assert "10004" in codes
  assert "10005" in codes
  assert "10006" in codes
  assert "30010" in codes
  assert "50010" in codes
