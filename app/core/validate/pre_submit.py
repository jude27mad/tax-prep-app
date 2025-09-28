from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

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


_POSTAL_TEMPLATE = "A1A1A1"


def _validate_postal_code(value: str) -> bool:
    if not value or len(value.replace(" ", "")) != 6:
        return False
    cleaned = value.replace(" ", "").upper()
    pattern = [str.isalpha, str.isdigit, str.isalpha, str.isdigit, str.isalpha, str.isdigit]
    return all(check(ch) for check, ch in zip(pattern, cleaned))


def _validate_identity_fields(identity: Identity) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not identity.sin or len(identity.sin) != 9 or not identity.sin.isdigit():
        issues.append(ValidationIssue("10001", "SIN must be 9 numeric digits", field="sin"))
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


# Minimal checks per RC4018 ch.1 (identity section) and common reject families in ch.2.
def validate_before_efile(identity: Identity, return_payload: dict) -> list[ValidationIssue]:
    issues = _validate_identity_fields(identity)

    # Common business-rule guards (examples)
    ti = Decimal(str(return_payload.get("taxable_income", "0")))
    if ti < 0:
        issues.append(ValidationIssue("30010", "Taxable income cannot be negative", field="taxable_income"))

    if not return_payload.get("t183_signed_ts"):
        issues.append(ValidationIssue("50010", "T183 signature timestamp is required before transmission", field="t183"))

    return issues


def _valid_sin(sin: str) -> bool:
    return bool(sin and len(sin) == 9 and sin.isdigit())


def _validate_taxpayer_details(taxpayer: Taxpayer) -> list[str]:
    issues: list[str] = []
    if not _valid_sin(taxpayer.sin):
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
    return issues
