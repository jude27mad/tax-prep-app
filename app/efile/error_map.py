from __future__ import annotations

from typing import Dict

# Representative RC4018 mappings. Expand as CRA releases new codes.
_SPECIFIC_CODES: Dict[str, str] = {
    "10021": "SIN, name, or date of birth mismatch with CRA records.",
    "10200": "Mailing address invalid – verify civic, city, province, postal code.",
    "30001": "Line balance error – reconcile income and deduction totals.",
    "30008": "RRSP or deduction claim exceeds available room for this taxpayer.",
    "40013": "Return totals do not balance with attached slips or schedules.",
    "80308": "Authentication failure – confirm CRA transmitter number and password.",
}

_FAMILY_CODES: Dict[str, str] = {
    "1": "Identification / format reject – review SIN, name, birthdate, and address formatting.",
    "3": "Business-rule reject – check taxable income, credits, residency, and required schedules.",
    "4": "Balancing reject – re-add line items and slip summaries before resubmitting.",
    "5": "Slips / attachments reject – ensure all slips referenced in the return are transmitted.",
    "8": "Transmission layer issue – confirm CRA endpoint availability and credentials.",
}


def explain_error(code: str) -> str:
    normalized = (code or "").strip()
    if not normalized:
        return "Unknown EFILE reject code – review CRA RC4018 Chapter 2."

    if normalized in _SPECIFIC_CODES:
        return _SPECIFIC_CODES[normalized]

    for prefix, message in _FAMILY_CODES.items():
        if normalized.startswith(prefix):
            return message

    return "Unknown EFILE reject code – review CRA RC4018 Chapter 2."
