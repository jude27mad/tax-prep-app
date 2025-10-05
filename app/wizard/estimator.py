from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.tax.ca2025 import (
    FEDERAL_2025,
    FED_CREDIT_RATE,
    federal_bpa_2025,
    tax_from_brackets as fed_tax,
)
from app.tax.dispatch import UnknownProvinceError, get_provincial_adapter

CPP_BASE_EXEMPTION = 3_500.0
CPP_YMPE_2025 = 71_300.0
CPP_YAMPE_2025 = 81_200.0
CPP_RATE_2025 = 0.0595
CPP2_RATE_2025 = 0.04
EI_MIE_2025 = 65_700.0
EI_RATE_2025 = 0.0164
_TOLERANCE = 0.05  # forgive minor payroll rounding
_CENT = Decimal("0.01")


class T4EstimateRequest(BaseModel):
    box14: float = Field(
        ...,
        ge=0,
        description="Employment income (T4 box 14)",
        validation_alias=AliasChoices("box14", "box14_employment_income"),
    )
    box22: float = Field(
        ...,
        ge=0,
        description="Income tax deducted (T4 box 22)",
        validation_alias=AliasChoices("box22", "box22_tax_withheld"),
    )
    box16: float = Field(
        ...,
        ge=0,
        description="CPP contributions (T4 box 16)",
        validation_alias=AliasChoices("box16", "box16_cpp"),
    )
    box16a: float = Field(
        0.0,
        ge=0,
        description="Second CPP contributions (T4 box 16A)",
        validation_alias=AliasChoices("box16a", "box16A", "box16A_cpp2", "box16_cpp2", "box16a_cpp2"),
    )
    box18: float = Field(
        ...,
        ge=0,
        description="EI premiums (T4 box 18)",
        validation_alias=AliasChoices("box18", "box18_ei"),
    )
    rrsp: float = Field(
        0.0,
        ge=0,
        description="RRSP deductions claimed",
        validation_alias=AliasChoices("rrsp", "rrsp_deduction"),
    )
    province: str = Field("ON", description="Province code, defaults to ON")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def to_decimal(value: float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def round_cents(value: float | Decimal) -> float:
    return float(to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


def compute_tax_summary(income: float, rrsp: float, province: str) -> dict[str, Any]:
    taxable = max(0.0, income - max(rrsp, 0.0))

    federal_before = fed_tax(taxable, FEDERAL_2025)
    fed_bpa = federal_bpa_2025(taxable)
    federal_after = max(0.0, round_cents(federal_before - FED_CREDIT_RATE * fed_bpa))

    province_code = (province or "ON").upper()
    try:
        adapter = get_provincial_adapter(2025, province_code)
    except UnknownProvinceError as exc:
        raise ValueError(str(exc)) from exc

    provincial = adapter.compute(taxable)
    total_net_tax = round_cents(to_decimal(federal_after) + to_decimal(provincial.net_tax))

    return {
        "income": income,
        "rrsp": rrsp,
        "taxable_income": taxable,
        "province": provincial.province_code,
        "federal": {
            "before_credits": federal_before,
            "bpa_used": fed_bpa,
            "after_credits": federal_after,
        },
        "provincial": {
            "province_code": provincial.province_code,
            "province_name": provincial.province_name,
            "before_credits": provincial.before_credits,
            "bpa_used": provincial.bpa_used,
            "credit_rate": provincial.credit_rate,
            "after_credits": provincial.after_credits,
            "additions": provincial.additions,
            "net_provincial": provincial.net_tax,
        },
        "total_net_tax": total_net_tax,
    }


def expected_cpp_contributions(income: float) -> tuple[float, float]:
    income_dec = to_decimal(income)
    ympe = to_decimal(CPP_YMPE_2025)
    base = to_decimal(CPP_BASE_EXEMPTION)
    pensionable = max(Decimal("0"), min(income_dec, ympe) - base)
    cpp_regular = round_cents(pensionable * to_decimal(CPP_RATE_2025))

    yamp = to_decimal(CPP_YAMPE_2025)
    additional_earnings = max(Decimal("0"), min(income_dec, yamp) - ympe)
    cpp_additional = round_cents(additional_earnings * to_decimal(CPP2_RATE_2025))

    return cpp_regular, cpp_additional


def expected_ei_contribution(income: float) -> float:
    income_dec = to_decimal(income)
    mie = to_decimal(EI_MIE_2025)
    rate = to_decimal(EI_RATE_2025)
    return round_cents(min(income_dec, mie) * rate)


def within_limit(actual: float, maximum: float) -> bool:
    return actual <= maximum + _TOLERANCE


def contribution_status(actual: float, maximum: float) -> str:
    if actual > maximum + _TOLERANCE:
        return "over"
    if actual < max(0.0, maximum - _TOLERANCE):
        return "under"
    return "ok"


def estimate_from_t4(payload: T4EstimateRequest) -> dict[str, Any]:
    tax_summary = compute_tax_summary(payload.box14, payload.rrsp, payload.province)
    total_tax = tax_summary["total_net_tax"]
    total_tax_dec = to_decimal(total_tax)
    withheld = round_cents(payload.box22)
    balance = round_cents(total_tax_dec - to_decimal(withheld))

    cpp_max, cpp2_max = expected_cpp_contributions(payload.box14)
    ei_max = expected_ei_contribution(payload.box14)

    cpp_actual = round_cents(payload.box16)
    cpp2_actual = round_cents(payload.box16a)
    ei_actual = round_cents(payload.box18)

    return {
        "inputs": {
            "box14": payload.box14,
            "box22": payload.box22,
            "box16": payload.box16,
            "box16A": payload.box16a,
            "box18": payload.box18,
            "rrsp": payload.rrsp,
            "province": payload.province,
        },
        "tax": tax_summary,
        "total_tax": total_tax,
        "withholding": withheld,
        "balance": balance,
        "balance_positive_is_amount_owing": balance > 0,
        "is_refund": balance < 0,
        "cpp": {
            "reported": cpp_actual,
            "maximum_allowed": cpp_max,
            "within_limit": within_limit(cpp_actual, cpp_max),
            "status": contribution_status(cpp_actual, cpp_max),
        },
        "cpp2": {
            "reported": cpp2_actual,
            "maximum_allowed": cpp2_max,
            "within_limit": within_limit(cpp2_actual, cpp2_max),
            "status": contribution_status(cpp2_actual, cpp2_max),
        },
        "ei": {
            "reported": ei_actual,
            "maximum_allowed": ei_max,
            "within_limit": within_limit(ei_actual, ei_max),
            "status": contribution_status(ei_actual, ei_max),
        },
    }


__all__ = [
    "T4EstimateRequest",
    "compute_tax_summary",
    "contribution_status",
    "estimate_from_t4",
    "expected_cpp_contributions",
    "expected_ei_contribution",
    "round_cents",
    "to_decimal",
    "within_limit",
]
