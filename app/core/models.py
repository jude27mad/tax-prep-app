from decimal import Decimal
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


_CENT = Decimal("0.01")


def _quantize_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_CENT)


class T4ASlip(BaseModel):
    pension_income: Decimal | None = None
    other_income: Decimal | None = None
    self_employment_commissions: Decimal | None = None
    research_grants: Decimal | None = None
    tax_deducted: Decimal | None = None

    _quantize_optional_fields = field_validator(
        "pension_income",
        "other_income",
        "self_employment_commissions",
        "research_grants",
        "tax_deducted",
        mode="after",
    )(_quantize_decimal)


class T5Slip(BaseModel):
    interest_income: Decimal | None = None
    eligible_dividends: Decimal | None = None
    other_dividends: Decimal | None = None
    capital_gains: Decimal | None = None
    foreign_income: Decimal | None = None
    foreign_tax_withheld: Decimal | None = None

    _quantize_optional_fields = field_validator(
        "interest_income",
        "eligible_dividends",
        "other_dividends",
        "capital_gains",
        "foreign_income",
        "foreign_tax_withheld",
        mode="after",
    )(_quantize_decimal)


class TuitionSlip(BaseModel):
    institution_name: str | None = None
    eligible_tuition: Decimal = Decimal("0.00")
    months_full_time: int = 0
    months_part_time: int = 0


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

    _quantize_employment_income = field_validator(
        "employment_income",
        mode="after",
    )(_quantize_decimal)

    _quantize_optional_fields = field_validator(
        "cpp_contrib",
        "ei_premiums",
        "pensionable_earnings",
        "insurable_earnings",
        "tax_deducted",
        mode="after",
    )(_quantize_decimal)


class RRSPReceipt(BaseModel):
    contribution_amount: Decimal
    issuer: str | None = None
    receipt_type: str | None = None
    period_start: date | None = None
    period_end: date | None = None

    _quantize_amount = field_validator(
        "contribution_amount",
        mode="after",
    )(_quantize_decimal)


class DeductionCreditInputs(BaseModel):
    tuition_fees: Decimal | None = None
    medical_expenses: Decimal | None = None
    charitable_donations: Decimal | None = None
    student_loan_interest: Decimal | None = None

    _quantize_optional_fields = field_validator(
        "tuition_fees",
        "medical_expenses",
        "charitable_donations",
        "student_loan_interest",
        mode="after",
    )(_quantize_decimal)


class ReturnInput(BaseModel):
    taxpayer: Taxpayer
    household: Household | None = None
    slips_t4: list[T4Slip] = Field(default_factory=list)
    slips_t4a: list[T4ASlip] = Field(default_factory=list)
    slips_t5: list[T5Slip] = Field(default_factory=list)
    tuition_slips: list[TuitionSlip] = Field(default_factory=list)
    rrsp_receipts: list[RRSPReceipt] = Field(default_factory=list)
    deductions: DeductionCreditInputs = Field(default_factory=DeductionCreditInputs)
    rrsp_contrib: Decimal = Decimal("0.00")
    tuition_claim: Decimal = Decimal("0.00")
    tuition_transfer_to_spouse: Decimal = Decimal("0.00")
    t183_signed_ts: datetime | None = None
    t183_ip_hash: str | None = None
    t183_user_agent_hash: str | None = None
    t183_pdf_path: str | None = None
    province: str = "ON"
    tax_year: int = 2025
    transmitter_account_mm: str | None = None
    rep_id: str | None = None


class ReturnCalc(BaseModel):
    tax_year: int
    province: str
    line_items: dict[str, Decimal]
    totals: dict[str, Decimal]
    cpp: dict[str, Decimal]
    ei: dict[str, Decimal]
