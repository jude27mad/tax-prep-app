from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import date, datetime

class Taxpayer(BaseModel):
  sin: str
  first_name: str
  last_name: str
  dob: date
  address_line1: str
  city: str
  province: str
  postal_code: str
  residency_status: str

class Household(BaseModel):
  marital_status: str
  spouse_sin: str | None = None
  dependants: list[str] = Field(default_factory=list)

class T4Slip(BaseModel):
  employment_income: Decimal
  cpp_contrib: Decimal | None = None
  ei_premiums: Decimal | None = None
  pensionable_earnings: Decimal | None = None
  insurable_earnings: Decimal | None = None
  tax_deducted: Decimal | None = None

class ReturnInput(BaseModel):
  taxpayer: Taxpayer
  household: Household | None = None
  slips_t4: list[T4Slip] = Field(default_factory=list)
  rrsp_contrib: Decimal = Decimal("0.00")
  t183_signed_ts: datetime | None = None
  t183_ip_hash: str | None = None
  t183_user_agent_hash: str | None = None
  t183_pdf_path: str | None = None
  province: str = "ON"
  tax_year: int = 2025

class ReturnCalc(BaseModel):
  tax_year: int
  province: str
  line_items: dict[str, Decimal]
  totals: dict[str, Decimal]
  cpp: dict[str, Decimal]
  ei: dict[str, Decimal]
