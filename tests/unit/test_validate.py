from decimal import Decimal

from app.core.models import T4ASlip, T5Slip, TuitionSlip
from app.core.validate.pre_submit import validate_return_input, validate_before_efile, Identity
from tests.fixtures.min_client import make_min_input, make_provincial_examples


def test_validate_ok():
  issues = validate_return_input(make_min_input())
  assert issues == []


def test_validate_accepts_provincial_examples():
  examples = make_provincial_examples()
  for req in examples.values():
    issues = validate_return_input(req)
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


def test_validate_before_efile_detects_slip_count_mismatch():
  req = make_min_input(include_examples=True, province="BC")
  identity = Identity(
    sin="046454286",
    first_name="Test",
    last_name="User",
    dob_yyyy_mm_dd="1990-01-01",
    address_line1="1 Main St",
    city=req.taxpayer.city,
    province=req.taxpayer.province,
    postal_code=req.taxpayer.postal_code,
  )
  payload = {
    "tax_year": req.tax_year,
    "province": req.province,
    "taxable_income": "90000",
    "t183_signed_ts": req.t183_signed_ts,
    "t183_ip_hash": req.t183_ip_hash,
    "t183_user_agent_hash": req.t183_user_agent_hash,
    "slips_t4": [
      {
        key: str(value)
        for key, value in slip.model_dump().items()
        if value is not None
      }
      for slip in req.slips_t4
    ],
    "slips_t4a": [
      {
        key: str(value)
        for key, value in slip.model_dump().items()
        if value is not None
      }
      for slip in req.slips_t4a
    ],
    "slips_t5": [
      {
        key: str(value)
        for key, value in slip.model_dump().items()
        if value is not None
      }
      for slip in req.slips_t5
    ],
  }
  payload["slips_t4_count"] = len(req.slips_t4) + 1
  payload["slips_t5_count"] = len(req.slips_t5)
  issues = validate_before_efile(identity, payload)
  codes = {issue.code for issue in issues}
  assert "60012" in codes


def test_validate_rejects_negative_t4_amount():
  payload = make_min_input()
  payload.slips_t4[0].tax_deducted = Decimal("-1.00")
  issues = validate_return_input(payload)
  assert "t4_negative_amount" in issues


def test_validate_before_efile_requires_t4_income_box():
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
  payload = {
    "tax_year": 2025,
    "province": "ON",
    "taxable_income": "0",
    "t183_signed_ts": "2025-03-01T10:00:00",
    "t183_ip_hash": "ip",
    "t183_user_agent_hash": "ua",
    "slips_t4": [{"tax_deducted": "100"}],
  }
  issues = validate_before_efile(identity, payload)
  codes = {issue.code for issue in issues}
  assert "60010" in codes


def test_validate_t4a_requires_income_amount():
  payload = make_min_input()
  payload.slips_t4a = [T4ASlip()]
  issues = validate_return_input(payload)
  assert "t4a_missing_income" in issues


def test_validate_t4a_accepts_positive_income():
  payload = make_min_input()
  payload.slips_t4a = [T4ASlip(pension_income=Decimal("1200"), tax_deducted=Decimal("150"))]
  issues = validate_return_input(payload)
  assert "t4a_missing_income" not in issues
  assert "t4a_negative_amount" not in issues


def test_validate_t5_requires_income():
  payload = make_min_input()
  payload.slips_t5 = [T5Slip()]
  issues = validate_return_input(payload)
  assert "t5_missing_income" in issues


def test_validate_t5_foreign_tax_cannot_exceed_income():
  payload = make_min_input()
  payload.slips_t5 = [T5Slip(foreign_income=Decimal("100"), foreign_tax_withheld=Decimal("150"))]
  issues = validate_return_input(payload)
  assert "t5_foreign_tax_exceeds_income" in issues


def test_validate_t5_accepts_valid_amounts():
  payload = make_min_input()
  payload.slips_t5 = [T5Slip(interest_income=Decimal("250"), foreign_tax_withheld=Decimal("0"))]
  issues = validate_return_input(payload)
  assert "t5_missing_income" not in issues


def test_validate_tuition_claim_limits():
  payload = make_min_input()
  payload.tuition_slips = [
    TuitionSlip(institution_name="Uni", eligible_tuition=Decimal("1000"), months_full_time=4)
  ]
  payload.tuition_claim = Decimal("1200")
  issues = validate_return_input(payload)
  assert "tuition_claim_exceeds_total" in issues


def test_validate_tuition_transfer_limits():
  payload = make_min_input()
  payload.tuition_slips = [
    TuitionSlip(institution_name="Uni", eligible_tuition=Decimal("1000"), months_full_time=4)
  ]
  payload.tuition_claim = Decimal("900")
  payload.tuition_transfer_to_spouse = Decimal("200")
  issues = validate_return_input(payload)
  assert "tuition_transfer_exceeds_remaining" in issues


def test_validate_tuition_month_bounds():
  payload = make_min_input()
  payload.tuition_slips = [
    TuitionSlip(
      institution_name="Uni",
      eligible_tuition=Decimal("1000"),
      months_full_time=13,
    )
  ]
  issues = validate_return_input(payload)
  assert "tuition_invalid_months" in issues


def test_validate_tuition_accepts_balanced_claims():
  payload = make_min_input()
  payload.tuition_slips = [
    TuitionSlip(institution_name="Uni", eligible_tuition=Decimal("1000"), months_full_time=4)
  ]
  payload.tuition_claim = Decimal("800")
  payload.tuition_transfer_to_spouse = Decimal("200")
  issues = validate_return_input(payload)
  assert "tuition_claim_exceeds_total" not in issues
  assert "tuition_transfer_exceeds_remaining" not in issues


def test_validate_rrsp_requires_non_negative_amount():
  payload = make_min_input()
  payload.rrsp_contrib = Decimal("-10")
  issues = validate_return_input(payload)
  assert "rrsp_negative_amount" in issues


def test_validate_before_efile_t5_foreign_tax_rule():
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
  payload = {
    "tax_year": 2025,
    "province": "ON",
    "taxable_income": "0",
    "t183_signed_ts": "2025-03-01T10:00:00",
    "t183_ip_hash": "ip",
    "t183_user_agent_hash": "ua",
    "slips_t5": [
      {"foreign_income": "100", "foreign_tax_withheld": "150"}
    ],
  }
  issues = validate_before_efile(identity, payload)
  codes = {issue.code for issue in issues}
  assert "60017" in codes
