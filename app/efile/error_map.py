from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class RejectCodeInfo:
    """Structured description for an RC4018 reject code."""

    code: str
    category: str
    summary: str
    remediation: str

    @property
    def friendly_message(self) -> str:
        return self.summary


_SPECIFIC_CODES: Dict[str, RejectCodeInfo] = {
    # Identification & authentication rejects.
    "10021": RejectCodeInfo(
        code="10021",
        category="Identification",
        summary="CRA cannot match the SIN, name, or birthdate to their records.",
        remediation="Confirm the client’s SIN, legal name, and date of birth exactly match the CRA and update the return before retransmitting.",
    ),
    "10200": RejectCodeInfo(
        code="10200",
        category="Identification",
        summary="Mailing address failed CRA validation.",
        remediation="Check civic number, street, municipality, province, and postal code formatting against Canada Post and refile.",
    ),
    # Business-rule rejects.
    "30001": RejectCodeInfo(
        code="30001",
        category="Business rule",
        summary="Return totals do not balance with CRA business rules.",
        remediation="Recalculate income and deduction line totals; update slips or schedules causing the mismatch.",
    ),
    "30022": RejectCodeInfo(
        code="30022",
        category="Business rule",
        summary="Province or territory of residence conflicts with reported information.",
        remediation="Verify the province of residence on page 1 matches schedules, tax credits, and postal code, then correct and resend.",
    ),
    # Balancing & attachment rejects.
    "40013": RejectCodeInfo(
        code="40013",
        category="Balancing",
        summary="Return totals do not balance with attached slips or schedules.",
        remediation="Ensure every slip and schedule referenced in the return is attached and totals agree before resubmitting.",
    ),
    "50113": RejectCodeInfo(
        code="50113",
        category="Authorization",
        summary="Client signature missing on Form T183.",
        remediation="Obtain a signed T183 (electronic or wet signature) dated before transmission and update the authorization details prior to retransmitting.",
    ),
    # Transmission rejects.
    "80308": RejectCodeInfo(
        code="80308",
        category="Transmission",
        summary="Authentication failure during transmission.",
        remediation="Confirm the EFILE number, password, and CRA service availability before attempting again.",
    ),
}

_FAMILY_CODES: Dict[str, RejectCodeInfo] = {
    "1": RejectCodeInfo(
        code="1xx",
        category="Identification",
        summary="Identification or formatting issue detected.",
        remediation="Review SIN, names, dates of birth, and address formatting to ensure they follow CRA standards.",
    ),
    "3": RejectCodeInfo(
        code="3xx",
        category="Business rule",
        summary="Business-rule validation failed.",
        remediation="Recalculate line amounts, credits, and residency details to satisfy CRA consistency checks.",
    ),
    "4": RejectCodeInfo(
        code="4xx",
        category="Balancing",
        summary="Return balancing issue encountered.",
        remediation="Reconcile line items with the supporting schedules and slips before resubmitting.",
    ),
    "5": RejectCodeInfo(
        code="5xx",
        category="Attachments",
        summary="Slip or authorization attachment issue.",
        remediation="Confirm required slips, supporting documents, and authorizations (T183/T183CORP) are complete and attached.",
    ),
    "8": RejectCodeInfo(
        code="8xx",
        category="Transmission",
        summary="Transmission layer issue occurred.",
        remediation="Verify CRA service availability, transmitter credentials, and retry the submission.",
    ),
}

_UNKNOWN = RejectCodeInfo(
    code="unknown",
    category="Unknown",
    summary="Unknown EFILE reject code – review CRA RC4018 Chapter 2.",
    remediation="Check the latest CRA RC4018 Chapter 2 for details, then update the application’s reject-code map if necessary.",
)


def get_reject_details(code: str | None) -> RejectCodeInfo:
    """Return structured guidance for a CRA RC4018 reject code."""

    normalized = (code or "").strip()
    if not normalized:
        return _UNKNOWN

    if normalized in _SPECIFIC_CODES:
        return _SPECIFIC_CODES[normalized]

    for prefix, info in _FAMILY_CODES.items():
        if normalized.startswith(prefix):
            return info

    return _UNKNOWN


def explain_error(code: str) -> str:
    """Backward-compatible helper returning the friendly summary."""

    return get_reject_details(code).friendly_message
