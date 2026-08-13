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
    document_id: str | None = None

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
    document_id: str | None = None

    _quantize_optional_fields = field_validator(
        "interest_income",
        "eligible_dividends",
        "other_dividends",
        "capital_gains",
        "foreign_income",
        "foreign_tax_withheld",
        mode="after",
    )(_quantize_decimal)


class T4ESlip(BaseModel):
    """Statement of Employment Insurance and Other Benefits.

    Box 14 (total benefits paid) feeds T1 line 11900, net of box 18. Box 22
    (income tax deducted) feeds line 43700 alongside T4/T4A withholding.

    Box 18 (tax-exempt benefits) applies to individuals registered or
    eligible to be registered under the Indian Act whose benefits are
    connected to a reserve. It is a subset of box 14, already included in
    it, and CRA instructs reporting box 14 minus box 18 on line 11900 -- the
    exempt portion is excluded from income entirely, not merely from
    taxable income the way the T5007 line 25000 offset works.

    Box 7 (repayment rate) and box 15 (regular and other benefits paid) feed
    the line 23500/42200 social benefits repayment (EI "clawback") when net
    income exceeds the year's repayment threshold. That calculation is not
    yet implemented -- see the pre-submission gate in
    app.core.validate.pre_submit -- so a slip carrying a nonzero repayment
    rate against nonzero regular benefits is captured here but rejected
    before transmission rather than silently omitted from balance owing.
    """

    benefits_paid: Decimal = Decimal("0.00")
    tax_deducted: Decimal | None = None
    tax_exempt_benefits: Decimal | None = None
    repayment_rate: Decimal | None = None
    regular_benefits_paid: Decimal | None = None
    document_id: str | None = None

    _quantize_benefits_paid = field_validator(
        "benefits_paid",
        mode="after",
    )(_quantize_decimal)

    _quantize_optional_fields = field_validator(
        "tax_deducted",
        "tax_exempt_benefits",
        "repayment_rate",
        "regular_benefits_paid",
        mode="after",
    )(_quantize_decimal)


class T5007Slip(BaseModel):
    """Statement of Benefits: workers' compensation and social assistance.

    Box 10 (workers' compensation) feeds line 14400; box 11 (social
    assistance, including provincial/territorial supplements) feeds line
    14500. Both are included in total income and then fully offset by the
    line 25000 deduction -- taxed at 0% but still counted in net income for
    income-tested amounts. T5007 carries no tax-deducted box.
    """

    workers_compensation: Decimal | None = None
    social_assistance: Decimal | None = None
    document_id: str | None = None

    _quantize_optional_fields = field_validator(
        "workers_compensation",
        "social_assistance",
        mode="after",
    )(_quantize_decimal)


class RC210Slip(BaseModel):
    """Advance Canada Workers Benefit payments statement.

    Reports CWB amounts already advanced to the taxpayer during the year, to
    be reconciled against the Schedule 6 entitlement (CRA line 41500). Not
    income and not yet consumed by the calculation engine -- Schedule 6/CWB
    wiring is separate credit work.
    """

    advance_cwb_payments: Decimal = Decimal("0.00")
    document_id: str | None = None

    _quantize_advance_cwb_payments = field_validator(
        "advance_cwb_payments",
        mode="after",
    )(_quantize_decimal)


class TuitionSlip(BaseModel):
    institution_name: str | None = None
    eligible_tuition: Decimal = Decimal("0.00")
    months_full_time: int = 0
    months_part_time: int = 0
    document_id: str | None = None


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
    document_id: str | None = None

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
    document_id: str | None = None

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
    slips_t4e: list[T4ESlip] = Field(default_factory=list)
    slips_t5007: list[T5007Slip] = Field(default_factory=list)
    slips_rc210: list[RC210Slip] = Field(default_factory=list)
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
    """Deterministic output of a return computation.

    ``line_items`` holds the T1 lines proper (see :mod:`app.core.lines` for the
    canonical keys and their CRA line numbers). ``provincial_additions`` holds
    province-specific amounts added on top of provincial tax — Ontario surtax and
    health premium today — and is a **separate field on purpose**: consumers used
    to identify additions as "any ``line_items`` key I don't recognise", which
    silently reclassified every new line as a provincial addition. Additions are
    declared, not inferred.
    """

    tax_year: int
    province: str
    line_items: dict[str, Decimal]
    totals: dict[str, Decimal]
    cpp: dict[str, Decimal]
    ei: dict[str, Decimal]
    provincial_additions: dict[str, Decimal] = Field(default_factory=dict)
