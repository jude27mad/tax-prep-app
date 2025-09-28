from decimal import Decimal
from app.core.models import Taxpayer, Household, T4Slip, ReturnInput


def make_min_input(tax_year: int = 2025) -> ReturnInput:
  tp = Taxpayer(
    sin="123456789",
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
  return ReturnInput(taxpayer=tp, household=hh, slips_t4=[t4], rrsp_contrib=Decimal("0.00"), province="ON", tax_year=tax_year)
