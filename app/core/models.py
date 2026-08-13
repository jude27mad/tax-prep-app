from decimal import Decimal
from datetime import date, datetime
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


# --- Prior tax state -------------------------------------------------------
#
# Opening balances and limits a return *inherits* from prior years. They are
# inputs, never results: nothing here is computed from the current return, and
# nothing here is consumed by the current return's calculation. Roadmap PR 8
# establishes the contract only; Schedule 11 (tuition) and Schedule 7 (RRSP)
# consume it later, when the accounting relationships they close become real:
#
#     opening tuition + current tuition
#         = used + transferred + closing carryforward
#     opening unused RRSP contributions + current qualifying contributions
#         = claimed + closing unused contributions
#
# The right-hand side of each identity is a deterministic output or an
# election, so none of it belongs here. ``rrsp_contrib``, ``tuition_claim``,
# and ``tuition_transfer_to_spouse`` keep their existing meaning untouched.

#: Where a prior amount was obtained. Symbolic, matching the evidence-kind
#: pattern in :mod:`app.explain.models`; anything outside this set is rejected
#: rather than silently recorded as unknown provenance.
PriorAmountSource = Literal[
    "cra_afr",  # CRA Auto-fill My Return download
    "prior_noa",  # prior-year Notice of Assessment
    "prior_reassessment",  # prior-year Notice of Reassessment
    "prior_filed_return",  # the prior year's filed return
    "manual",  # keyed in by the preparer or taxpayer
]

#: Stable issue codes for prior-state rejections. Local slugs in the style of
#: :mod:`app.core.validate.pre_submit`'s ``IssueTemplate.local``. They are
#: raised inside pydantic validation messages, so a caller gets both the code
#: and pydantic's precise field path (``loc``) for the offending value.
ISSUE_PRIOR_AMOUNT_NEGATIVE = "prior_amount_negative"
ISSUE_PRIOR_AMOUNT_MISSING_PROVENANCE = "prior_amount_missing_provenance"
ISSUE_PRIOR_PROVENANCE_MISSING_REFERENCE = "prior_provenance_missing_reference"
ISSUE_PRIOR_PROVENANCE_NAIVE_TIMESTAMP = "prior_provenance_naive_timestamp"
ISSUE_PRIOR_STATE_MISSING_IDENTITY = "prior_state_missing_identity"
ISSUE_PRIOR_STATE_TAX_YEAR_MISMATCH = "prior_state_tax_year_mismatch"


class PriorAmountProvenance(BaseModel):
    """Where one prior amount came from, and how trusted it is.

    Provenance is per amount, not per state: a return's federal tuition
    carryforward may come from a CRA Auto-fill download while its RRSP
    deduction limit comes from a Notice of Assessment the taxpayer typed in.
    Collapsing those onto one record would attribute one document's trust
    level to figures it never covered.
    """

    model_config = ConfigDict(extra="forbid")

    source: PriorAmountSource
    #: The tax year the source document reports on, which is not necessarily
    #: the year the state applies to -- a reassessment of 2022 can restate a
    #: carryforward that opens 2025.
    source_tax_year: int
    #: When the value was captured. Timezone-aware so two captures from
    #: different machines remain orderable.
    captured_at: datetime
    #: Whether a human has confirmed/reviewed the amount against its source.
    confirmed: bool = False
    #: Identifier of the source document (AFR download id, NOA number, ...).
    reference_id: str | None = None
    #: Optional pointer to a review or manual override record.
    review_ref: str | None = None

    @field_validator("reference_id", "review_ref", mode="after")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("captured_at", mode="after")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                f"{ISSUE_PRIOR_PROVENANCE_NAIVE_TIMESTAMP}: "
                "captured_at must be timezone-aware."
            )
        return value

    @model_validator(mode="after")
    def _require_reference_for_documents(self) -> "PriorAmountProvenance":
        # A document-backed amount is only auditable if the document can be
        # named. Manual entry has no external document to cite, so it is the
        # one source permitted without a reference.
        if self.source != "manual" and not self.reference_id:
            raise ValueError(
                f"{ISSUE_PRIOR_PROVENANCE_MISSING_REFERENCE}: "
                f"source '{self.source}' requires a nonblank reference_id."
            )
        return self


class PriorAmount(BaseModel):
    """A prior-year amount together with its own provenance.

    Zero means "no opening balance", which needs no document. Any positive
    amount reduces tax or expands a limit, so it must say where it came from.
    """

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Decimal("0.00")
    provenance: PriorAmountProvenance | None = None

    _quantize_amount = field_validator("amount", mode="after")(_quantize_decimal)

    @model_validator(mode="after")
    def _require_provenance_for_positive_amounts(self) -> "PriorAmount":
        if self.amount < 0:
            raise ValueError(
                f"{ISSUE_PRIOR_AMOUNT_NEGATIVE}: prior amounts cannot be negative."
            )
        if self.amount > 0 and self.provenance is None:
            raise ValueError(
                f"{ISSUE_PRIOR_AMOUNT_MISSING_PROVENANCE}: "
                "a positive prior amount requires provenance."
            )
        return self


class PriorTaxState(BaseModel):
    """Opening balances and limits inherited from prior tax years.

    Federal and Ontario tuition carryforwards are tracked separately because
    they are separate balances under separate rules -- they diverge whenever
    the two jurisdictions allow different amounts, and a single combined
    figure could not be reconciled against either Schedule 11.
    """

    model_config = ConfigDict(extra="forbid")

    #: The return year this state opens. ``None`` means no prior state has
    #: been established, which is the default for every existing caller.
    applies_to_tax_year: int | None = None
    #: The date the state was established -- the "as of" date of the CRA
    #: account view, notice, or manual capture the amounts were read from.
    established_as_of: date | None = None

    opening_federal_tuition_carryforward: PriorAmount = Field(default_factory=PriorAmount)
    opening_ontario_tuition_carryforward: PriorAmount = Field(default_factory=PriorAmount)
    rrsp_deduction_limit: PriorAmount = Field(default_factory=PriorAmount)
    opening_unused_rrsp_contributions: PriorAmount = Field(default_factory=PriorAmount)
    hbp_required_repayment: PriorAmount = Field(default_factory=PriorAmount)
    llp_required_repayment: PriorAmount = Field(default_factory=PriorAmount)

    def amounts(self) -> Mapping[str, PriorAmount]:
        """Every prior amount keyed by field name, for callers that iterate."""
        return {
            "opening_federal_tuition_carryforward": self.opening_federal_tuition_carryforward,
            "opening_ontario_tuition_carryforward": self.opening_ontario_tuition_carryforward,
            "rrsp_deduction_limit": self.rrsp_deduction_limit,
            "opening_unused_rrsp_contributions": self.opening_unused_rrsp_contributions,
            "hbp_required_repayment": self.hbp_required_repayment,
            "llp_required_repayment": self.llp_required_repayment,
        }

    def is_established(self) -> bool:
        """Whether any prior amount has actually been supplied."""
        return any(entry.amount > 0 for entry in self.amounts().values())

    @model_validator(mode="after")
    def _require_identity_once_established(self) -> "PriorTaxState":
        # An all-zero state is "nothing carried forward" and needs no identity.
        # The moment a real balance is present, the state has to say which year
        # it opens and when it was read, or it cannot be re-verified later.
        if self.is_established() and (
            self.applies_to_tax_year is None or self.established_as_of is None
        ):
            raise ValueError(
                f"{ISSUE_PRIOR_STATE_MISSING_IDENTITY}: a prior state carrying "
                "amounts must set applies_to_tax_year and established_as_of."
            )
        return self


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
    # Opening balances inherited from prior years. Defaulted, so every existing
    # caller and fixture keeps working, and calculation-neutral: no computation
    # handler reads it yet (see PriorTaxState).
    prior_tax_state: PriorTaxState = Field(default_factory=PriorTaxState)
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

    @model_validator(mode="after")
    def _prior_state_matches_tax_year(self) -> "ReturnInput":
        # Opening balances are year-specific: a carryforward that opens 2024 is
        # not the carryforward that opens 2025. Attaching one to the wrong
        # return would silently misstate every amount derived from it later.
        applies_to = self.prior_tax_state.applies_to_tax_year
        if applies_to is not None and applies_to != self.tax_year:
            raise ValueError(
                f"{ISSUE_PRIOR_STATE_TAX_YEAR_MISMATCH}: prior_tax_state applies "
                f"to tax year {applies_to}, but the return is for {self.tax_year}."
            )
        return self


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
