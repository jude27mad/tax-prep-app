from decimal import Decimal
from app.core.models import (
  Taxpayer,
  Household,
  T4Slip,
  T4ASlip,
  T5Slip,
  RRSPReceipt,
  DeductionCreditInputs,
  ReturnInput,
)


def make_min_input(tax_year: int = 2025, include_examples: bool = False) -> ReturnInput:
  tp = Taxpayer(
    sin="046454286",
    first_name="Test",
    last_name="User",
    dob="1990-01-01",
    address_line1="1 Main St",
    city="Toronto",
    province="ON",
    postal_code="M1M1M1",
    residency_status="resident",
  )
  hh = Household(marital_status="single")
  t4 = T4Slip(employment_income=Decimal("60000.00"), tax_deducted=Decimal("9000.00"))
  slips_t4a = []
  slips_t5 = []
  rrsp_receipts = []
  deductions = DeductionCreditInputs()
  if include_examples:
    slips_t4a.append(
      T4ASlip(
        pension_income=Decimal("1200.00"),
        other_income=Decimal("300.00"),
        tax_deducted=Decimal("150.00"),
      )
    )
    slips_t5.append(
      T5Slip(
        interest_income=Decimal("45.50"),
        eligible_dividends=Decimal("12.34"),
        foreign_income=Decimal("25.00"),
        foreign_tax_paid=Decimal("3.75"),
      )
    )
    rrsp_receipts.append(
      RRSPReceipt(
        contribution_amount=Decimal("1000.00"),
        issuer="Sample Bank",
        receipt_type="official",
      )
    )
    deductions = DeductionCreditInputs(
      tuition_fees=Decimal("2000.00"),
      medical_expenses=Decimal("450.00"),
      charitable_donations=Decimal("250.00"),
      student_loan_interest=Decimal("125.00"),
    )
  return ReturnInput(
    taxpayer=tp,
    household=hh,
    slips_t4=[t4],
    slips_t4a=slips_t4a,
    slips_t5=slips_t5,
    rrsp_receipts=rrsp_receipts,
    deductions=deductions,
    rrsp_contrib=Decimal("0.00"),
    province="ON",
    tax_year=tax_year,
    t183_signed_ts="2025-02-15T09:00:00",
    t183_ip_hash="hash-ip",
    t183_user_agent_hash="hash-ua",
    t183_pdf_path="/tmp/t183.pdf",
  )
