from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.core.provinces import (
    UnknownProvinceError,
    get_provincial_calculator,
)
from app.core.tax_years.y2025.calc import compute_from_amounts

# Estimator constants. CPP/EI thresholds are local to the wizard because the
# estimator's job is to validate T4 box totals against statutory maxima — these
# numbers do not flow into the Decimal compute path. If/when a 2026 estimator
# lands these will need their own module.
CPP_BASE_EXEMPTION = Decimal("3500")
CPP_YMPE_2025 = Decimal("71300")
CPP_YAMPE_2025 = Decimal("81200")
CPP_RATE_2025 = Decimal("0.0595")
CPP2_RATE_2025 = Decimal("0.04")
EI_MIE_2025 = Decimal("65700")
EI_RATE_2025 = Decimal("0.0164")
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


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def compute_tax_summary(income: float, rrsp: float, province: str) -> dict[str, Any]:
    """Present the core tax computation as the estimator's JSON summary dict.

    This is a **presenter, not a calculator**. Every amount comes from
    :func:`app.core.tax_years.y2025.calc.compute_from_amounts`; this function only
    reshapes and floats them for JSON. Output shape is unchanged, so existing
    callers (CLI wizard preview, ``/tax/estimate``, the T4 endpoints) keep working.

    Previously this re-assembled federal tax, credits, provincial tax, and
    additions itself. That second implementation drifted from the filing path:
    it passed *taxable* income to the Basic Personal Amount phase-out while
    ``compute_return`` passed *total* income, so the two disagreed on the BPA for
    anyone with deductions. ``docs/plan_v3.md`` §3 forbids a second calculator;
    routing through the core is what makes that enforceable rather than aspirational.
    """
    # UnknownProvinceError subclasses KeyError, not ValueError, so it is
    # converted here to preserve this function's long-standing contract: callers
    # catch ValueError for an unsupported province.
    try:
        computation = compute_from_amounts(
            to_decimal(income),
            max(Decimal("0"), to_decimal(rrsp)),
            province=province,
        )
        # The provincial calculator is consulted only for display metadata
        # (name, credit rate); every amount comes from the computation above.
        calculator = get_provincial_calculator(2025, computation.province)
    except UnknownProvinceError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "income": income,
        "rrsp": rrsp,
        "taxable_income": float(computation.lines.taxable_income),
        "province": computation.province,
        "federal": {
            "before_credits": float(computation.federal_tax),
            "bpa_used": float(computation.federal_bpa),
            "after_credits": float(computation.net_federal_tax),
        },
        "provincial": {
            "province_code": computation.province,
            "province_name": calculator.name,
            "before_credits": float(computation.provincial_tax),
            "bpa_used": float(_quantize(computation.provincial_bpa)),
            "credit_rate": float(calculator.nrtc_rate),
            "after_credits": float(
                _quantize(
                    max(
                        Decimal("0"),
                        computation.provincial_tax - computation.provincial_credits,
                    )
                )
            ),
            "additions": {
                key: float(_quantize(value))
                for key, value in computation.provincial_additions.items()
            },
            "net_provincial": float(computation.net_provincial_tax),
        },
        "total_net_tax": float(computation.net_tax),
    }


def expected_cpp_contributions(income: float) -> tuple[float, float]:
    income_dec = to_decimal(income)
    pensionable = max(Decimal("0"), min(income_dec, CPP_YMPE_2025) - CPP_BASE_EXEMPTION)
    cpp_regular = round_cents(pensionable * CPP_RATE_2025)

    additional_earnings = max(Decimal("0"), min(income_dec, CPP_YAMPE_2025) - CPP_YMPE_2025)
    cpp_additional = round_cents(additional_earnings * CPP2_RATE_2025)

    return cpp_regular, cpp_additional


def expected_ei_contribution(income: float) -> float:
    income_dec = to_decimal(income)
    return round_cents(min(income_dec, EI_MIE_2025) * EI_RATE_2025)


def within_limit(actual: float, maximum: float) -> bool:
    return actual <= maximum + _TOLERANCE


def contribution_status(actual: float, maximum: float) -> str:
    if actual > maximum + _TOLERANCE:
        return "over"
    if actual < max(0.0, maximum - _TOLERANCE):
        return "under"
    return "ok"


def estimate_from_t4(payload: T4EstimateRequest) -> dict[str, Any]:
    # Withholding and balance come from the core computation rather than being
    # recomputed here, so the estimate and the filed return can never disagree
    # about a refund. Sign convention is the core's: positive is balance owing,
    # negative is a refund.
    try:
        computation = compute_from_amounts(
            to_decimal(payload.box14),
            max(Decimal("0"), to_decimal(payload.rrsp)),
            province=payload.province,
            withholding=to_decimal(payload.box22),
        )
    except UnknownProvinceError as exc:
        raise ValueError(str(exc)) from exc
    tax_summary = compute_tax_summary(payload.box14, payload.rrsp, payload.province)
    total_tax = tax_summary["total_net_tax"]
    withheld = round_cents(computation.withholding)
    balance = round_cents(computation.balance)

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
