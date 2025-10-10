from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from ..models import ReturnInput, Taxpayer

_ALLOWED_PROVINCES = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}


@dataclass
class Identity:
    sin: str
    first_name: str
    last_name: str
    dob_yyyy_mm_dd: str
    address_line1: str
    city: str
    province: str
    postal_code: str


@dataclass
class ValidationIssue:
    code: str
    message: str
    field: Optional[str] = None
    severity: str = "error"


@dataclass(frozen=True)
class IssueTemplate:
    local: str
    cra: str
    message: str


_POSTAL_TEMPLATE = "A1A1A1"
_MAX_SLIPS_PER_TYPE = 50

ISSUE_T4_MISSING_BOX14 = IssueTemplate(
    "t4_missing_box_14",
    "60010",
    "T4 slip is missing employment income (Box 14).",
)
ISSUE_T4_NEGATIVE_AMOUNT = IssueTemplate(
    "t4_negative_amount",
    "60011",
    "T4 slip amounts must be zero or positive.",
)
ISSUE_T4_COUNT_LIMIT = IssueTemplate(
    "t4_slip_count_exceeded",
    "60018",
    "T4 slip count exceeds CRA maximum of 50 per return.",
)
ISSUE_T4_COUNT_MISMATCH = IssueTemplate(
    "t4_slip_count_mismatch",
    "60012",
    "T4 slip summary count does not match provided slips.",
)
ISSUE_T4A_MISSING_INCOME = IssueTemplate(
    "t4a_missing_income",
    "60013",
    "T4A slip must include at least one income amount (boxes 16/18/20/48).",
)
ISSUE_T4A_NEGATIVE_AMOUNT = IssueTemplate(
    "t4a_negative_amount",
    "60014",
    "T4A slip amounts must be zero or positive.",
)
ISSUE_T4A_COUNT_LIMIT = IssueTemplate(
    "t4a_slip_count_exceeded",
    "60018",
    "T4A slip count exceeds CRA maximum of 50 per return.",
)
ISSUE_T4A_COUNT_MISMATCH = IssueTemplate(
    "t4a_slip_count_mismatch",
    "60012",
    "T4A slip summary count does not match provided slips.",
)
ISSUE_T5_MISSING_AMOUNT = IssueTemplate(
    "t5_missing_income",
    "60015",
    "T5 slip must include at least one income or dividend amount.",
)
ISSUE_T5_NEGATIVE_AMOUNT = IssueTemplate(
    "t5_negative_amount",
    "60016",
    "T5 slip amounts must be zero or positive.",
)
ISSUE_T5_FOREIGN_TAX = IssueTemplate(
    "t5_foreign_tax_exceeds_income",
    "60017",
    "Foreign tax withheld on a T5 slip cannot exceed the related foreign income.",
)
ISSUE_T5_COUNT_LIMIT = IssueTemplate(
    "t5_slip_count_exceeded",
    "60018",
    "T5 slip count exceeds CRA maximum of 50 per return.",
)
ISSUE_T5_COUNT_MISMATCH = IssueTemplate(
    "t5_slip_count_mismatch",
    "60012",
    "T5 slip summary count does not match provided slips.",
)
ISSUE_TUITION_NEGATIVE = IssueTemplate(
    "tuition_negative_amount",
    "61010",
    "Tuition slips must report a non-negative eligible tuition amount.",
)
ISSUE_TUITION_MONTHS = IssueTemplate(
    "tuition_invalid_months",
    "61011",
    "Tuition slip months must be whole numbers between 0 and 12.",
)
ISSUE_TUITION_CLAIM_NEGATIVE = IssueTemplate(
    "tuition_claim_negative",
    "61012",
    "Tuition amount claimed cannot be negative.",
)
ISSUE_TUITION_TRANSFER_NEGATIVE = IssueTemplate(
    "tuition_transfer_negative",
    "61013",
    "Tuition amount transferred cannot be negative.",
)
ISSUE_TUITION_CLAIM_EXCEEDS = IssueTemplate(
    "tuition_claim_exceeds_total",
    "61014",
    "Tuition amount claimed exceeds the total eligible tuition.",
)
ISSUE_TUITION_TRANSFER_EXCEEDS = IssueTemplate(
    "tuition_transfer_exceeds_remaining",
    "61015",
    "Tuition amount transferred exceeds the remaining eligible tuition.",
)
ISSUE_RRSP_NEGATIVE = IssueTemplate(
    "rrsp_negative_amount",
    "30011",
    "RRSP contributions claimed must be zero or positive.",
)


def _validate_postal_code(value: str) -> bool:
    if not value or len(value.replace(" ", "")) != 6:
        return False
    cleaned = value.replace(" ", "").upper()
    pattern = [str.isalpha, str.isdigit, str.isalpha, str.isdigit, str.isalpha, str.isdigit]
    return all(check(ch) for check, ch in zip(pattern, cleaned))


def _luhn_valid(value: str) -> bool:
    try:
        digits = [int(ch) for ch in value]
    except ValueError:
        return False
    checksum = 0
    double = False
    for digit in reversed(digits):
        if double:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
        double = not double
    return checksum % 10 == 0


def _validate_tax_year(year: int) -> bool:
    return year in {2024, 2025}


def _validate_identity_fields(identity: Identity) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not identity.sin or len(identity.sin) != 9 or not identity.sin.isdigit() or not _luhn_valid(identity.sin):
        issues.append(ValidationIssue("10001", "SIN must be 9 numeric digits and pass Luhn checksum", field="sin"))
    if not identity.first_name.strip() or not identity.last_name.strip():
        issues.append(ValidationIssue("10002", "First and last name are required", field="name"))
    try:
        datetime.strptime(identity.dob_yyyy_mm_dd, "%Y-%m-%d")
    except ValueError:
        issues.append(ValidationIssue("10003", "Date of birth must be YYYY-MM-DD", field="dob"))
    if not identity.address_line1.strip() or not identity.city.strip():
        issues.append(ValidationIssue("10004", "Mailing address must include street and city", field="address"))
    province = identity.province.upper()
    if province not in _ALLOWED_PROVINCES:
        issues.append(ValidationIssue("10005", "Province must be a valid two-letter Canadian code", field="province"))
    if not _validate_postal_code(identity.postal_code):
        issues.append(ValidationIssue("10006", f"Postal code must follow pattern {_POSTAL_TEMPLATE}", field="postal_code"))
    return issues


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _get_value(item: Any, field: str) -> Any:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def _field_path(collection: str, index: int, field: str | None = None) -> str:
    if field:
        return f"{collection}[{index}].{field}"
    return f"{collection}[{index}]"


def _collect_local(issues: list[str]):
    def _emit(template: IssueTemplate, field: str | None, *, message_override: str | None = None) -> None:
        issues.append(template.local)

    return _emit


def _collect_efile(issues: list[ValidationIssue]):
    def _emit(template: IssueTemplate, field: str | None, *, message_override: str | None = None) -> None:
        message = message_override or template.message
        issues.append(ValidationIssue(template.cra, message, field=field))

    return _emit


def _validate_slip_counts(
    slips: list[Any],
    reported_count: int | None,
    limit_issue: IssueTemplate,
    mismatch_issue: IssueTemplate,
    emit,
    collection_name: str,
) -> None:
    actual = len(slips)
    if reported_count is not None:
        if reported_count < 0 or reported_count != actual:
            emit(mismatch_issue, collection_name)
    if actual > _MAX_SLIPS_PER_TYPE or (
        reported_count is not None and reported_count > _MAX_SLIPS_PER_TYPE
    ):
        emit(limit_issue, collection_name)


def _validate_t4_slips(slips: list[Any], emit, *, collection: str = "slips_t4", reported_count: int | None = None) -> None:
    _validate_slip_counts(slips, reported_count, ISSUE_T4_COUNT_LIMIT, ISSUE_T4_COUNT_MISMATCH, emit, collection)
    for index, slip in enumerate(slips):
        income = _to_decimal(_get_value(slip, "employment_income"))
        field_name = _field_path(collection, index, "employment_income")
        if income is None:
            emit(ISSUE_T4_MISSING_BOX14, field_name)
        elif income < 0:
            emit(ISSUE_T4_NEGATIVE_AMOUNT, field_name)
        for optional in (
            "tax_deducted",
            "cpp_contrib",
            "ei_premiums",
            "pensionable_earnings",
            "insurable_earnings",
        ):
            value = _to_decimal(_get_value(slip, optional))
            if value is not None and value < 0:
                emit(ISSUE_T4_NEGATIVE_AMOUNT, _field_path(collection, index, optional))


def _validate_t4a_slips(slips: list[Any], emit, *, collection: str = "slips_t4a", reported_count: int | None = None) -> None:
    _validate_slip_counts(slips, reported_count, ISSUE_T4A_COUNT_LIMIT, ISSUE_T4A_COUNT_MISMATCH, emit, collection)
    for index, slip in enumerate(slips):
        has_income = False
        for field in (
            "pension_income",
            "other_income",
            "self_employment_commissions",
            "research_grants",
        ):
            value = _to_decimal(_get_value(slip, field))
            if value is not None:
                if value < 0:
                    emit(ISSUE_T4A_NEGATIVE_AMOUNT, _field_path(collection, index, field))
                if value > 0:
                    has_income = True
        tax_deducted = _to_decimal(_get_value(slip, "tax_deducted"))
        if tax_deducted is not None and tax_deducted < 0:
            emit(ISSUE_T4A_NEGATIVE_AMOUNT, _field_path(collection, index, "tax_deducted"))
        if not has_income:
            emit(ISSUE_T4A_MISSING_INCOME, _field_path(collection, index))


def _validate_t5_slips(slips: list[Any], emit, *, collection: str = "slips_t5", reported_count: int | None = None) -> None:
    _validate_slip_counts(slips, reported_count, ISSUE_T5_COUNT_LIMIT, ISSUE_T5_COUNT_MISMATCH, emit, collection)
    for index, slip in enumerate(slips):
        has_amount = False
        for field in (
            "interest_income",
            "eligible_dividends",
            "other_dividends",
            "capital_gains",
            "foreign_income",
        ):
            value = _to_decimal(_get_value(slip, field))
            if value is not None:
                if value < 0:
                    emit(ISSUE_T5_NEGATIVE_AMOUNT, _field_path(collection, index, field))
                if value > 0:
                    has_amount = True
        foreign_tax = _to_decimal(_get_value(slip, "foreign_tax_withheld"))
        if foreign_tax is not None:
            if foreign_tax < 0:
                emit(ISSUE_T5_NEGATIVE_AMOUNT, _field_path(collection, index, "foreign_tax_withheld"))
            foreign_income = _to_decimal(_get_value(slip, "foreign_income")) or Decimal("0")
            if foreign_tax > foreign_income:
                emit(ISSUE_T5_FOREIGN_TAX, _field_path(collection, index, "foreign_tax_withheld"))
        if not has_amount:
            emit(ISSUE_T5_MISSING_AMOUNT, _field_path(collection, index))


def _validate_tuition_slips(slips: list[Any], emit, *, collection: str = "tuition_slips") -> Decimal:
    total = Decimal("0")
    for index, slip in enumerate(slips):
        amount = _to_decimal(_get_value(slip, "eligible_tuition"))
        amount_field = _field_path(collection, index, "eligible_tuition")
        if amount is None:
            emit(ISSUE_TUITION_NEGATIVE, amount_field)
        elif amount < 0:
            emit(ISSUE_TUITION_NEGATIVE, amount_field)
        else:
            total += amount
        for field in ("months_full_time", "months_part_time"):
            raw_months = _get_value(slip, field)
            if raw_months in (None, ""):
                continue
            try:
                months = int(raw_months)
            except (TypeError, ValueError):
                emit(ISSUE_TUITION_MONTHS, _field_path(collection, index, field))
                continue
            if months < 0 or months > 12:
                emit(ISSUE_TUITION_MONTHS, _field_path(collection, index, field))
    return total


def _validate_tuition_claims(total: Decimal, claim_value: Any, transfer_value: Any, emit) -> None:
    claim = _to_decimal(claim_value)
    transfer = _to_decimal(transfer_value)
    if claim is not None and claim < 0:
        emit(ISSUE_TUITION_CLAIM_NEGATIVE, "tuition_claim")
    if transfer is not None and transfer < 0:
        emit(ISSUE_TUITION_TRANSFER_NEGATIVE, "tuition_transfer_to_spouse")
    claim_non_neg = claim if (claim is not None and claim > 0) else Decimal("0")
    transfer_non_neg = transfer if (transfer is not None and transfer > 0) else Decimal("0")
    if claim_non_neg > total:
        emit(ISSUE_TUITION_CLAIM_EXCEEDS, "tuition_claim")
    if claim_non_neg + transfer_non_neg > total:
        emit(ISSUE_TUITION_TRANSFER_EXCEEDS, "tuition_transfer_to_spouse")


def _validate_rrsp_amount(value: Any, emit) -> None:
    amount = _to_decimal(value)
    if amount is not None and amount < 0:
        emit(ISSUE_RRSP_NEGATIVE, "rrsp_contrib")


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


# Minimal checks per RC4018 ch.1 (identity section) and common reject families in ch.2.
def validate_before_efile(identity: Identity, return_payload: dict) -> list[ValidationIssue]:
    issues = _validate_identity_fields(identity)

    ti = Decimal(str(return_payload.get("taxable_income", "0")))
    if ti < 0:
        issues.append(ValidationIssue("30010", "Taxable income cannot be negative", field="taxable_income"))

    province = (return_payload.get("province") or identity.province or "").upper()
    if province not in _ALLOWED_PROVINCES:
        issues.append(ValidationIssue("10005", "Province must be a valid two-letter Canadian code", field="province"))

    tax_year = return_payload.get("tax_year")
    if tax_year is not None and not _validate_tax_year(int(tax_year)):
        issues.append(ValidationIssue("20001", "Unsupported or closed tax year for EFILE transmission", field="tax_year"))

    if not return_payload.get("t183_signed_ts"):
        issues.append(ValidationIssue("50010", "T183 signature timestamp is required before transmission", field="t183"))

    if not return_payload.get("t183_ip_hash") or not return_payload.get("t183_user_agent_hash"):
        issues.append(ValidationIssue("50011", "T183 IP/User-Agent hashes must be captured before transmission", field="t183"))

    emit = _collect_efile(issues)
    slips_t4 = _as_list(return_payload.get("slips_t4"))
    _validate_t4_slips(slips_t4, emit, reported_count=_to_int(return_payload.get("slips_t4_count")))
    slips_t4a = _as_list(return_payload.get("slips_t4a"))
    _validate_t4a_slips(slips_t4a, emit, reported_count=_to_int(return_payload.get("slips_t4a_count")))
    slips_t5 = _as_list(return_payload.get("slips_t5"))
    _validate_t5_slips(slips_t5, emit, reported_count=_to_int(return_payload.get("slips_t5_count")))
    tuition_slips = _as_list(return_payload.get("tuition_slips"))
    tuition_total = _validate_tuition_slips(tuition_slips, emit)
    _validate_tuition_claims(
        tuition_total,
        return_payload.get("tuition_claim"),
        return_payload.get("tuition_transfer_to_spouse"),
        emit,
    )
    _validate_rrsp_amount(return_payload.get("rrsp_contrib"), emit)

    return issues


def _valid_sin(sin: str) -> bool:
    return bool(sin and len(sin) == 9 and sin.isdigit())


def _validate_taxpayer_details(taxpayer: Taxpayer) -> list[str]:
    issues: list[str] = []
    if not _valid_sin(taxpayer.sin) or not _luhn_valid(taxpayer.sin):
        issues.append("invalid_sin")
    if not taxpayer.address_line1:
        issues.append("missing_address")
    if not _validate_postal_code(taxpayer.postal_code):
        issues.append("invalid_postal_code")
    if taxpayer.province.upper() not in _ALLOWED_PROVINCES:
        issues.append("invalid_province")
    return issues


def validate_return_input(in_: ReturnInput) -> list[str]:
    issues = _validate_taxpayer_details(in_.taxpayer)
    if in_.tax_year not in (2024, 2025):
        issues.append("unsupported_year")
    emit = _collect_local(issues)
    _validate_t4_slips(in_.slips_t4, emit)
    _validate_t4a_slips(in_.slips_t4a, emit)
    _validate_t5_slips(in_.slips_t5, emit)
    tuition_total = _validate_tuition_slips(in_.tuition_slips, emit)
    _validate_tuition_claims(tuition_total, in_.tuition_claim, in_.tuition_transfer_to_spouse, emit)
    _validate_rrsp_amount(in_.rrsp_contrib, emit)
    return issues
