"""One authoritative calculation path (docs/plan_v3.md section 3).

Every surface -- the core engine, the estimator dict, the /tax/estimate and
/t4/estimate endpoints, and the CLI wizard preview -- must agree on the same
numbers for the same inputs, because they now all adapt the output of a single
computation rather than each assembling their own.

This is the regression that makes the "no second calculator" rule enforceable.
The two implementations had genuinely drifted before app.core.computation existed:
compute_return passed *total* income to the Basic Personal Amount phase-out while
the estimator passed *taxable* income, so they disagreed on the BPA -- and
therefore on tax owing -- for anyone with deductions.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.models import ReturnInput, T4Slip, Taxpayer
from app.core.provinces import list_provincial_calculators
from app.core.tax_years.y2024.calc import compute_from_amounts as amounts_2024
from app.core.tax_years.y2025.calc import (
    compute_from_amounts as amounts_2025,
    compute_return as compute_2025,
)
from app.main import app as estimator_app
from app.wizard.estimator import (
    T4EstimateRequest,
    compute_tax_summary,
    estimate_from_t4,
)

D = Decimal

# (employment income, RRSP deduction, tax withheld, province)
SCENARIOS = [
    ("50000.00", "0.00", "8000.00", "ON"),
    ("68000.00", "5000.00", "12000.00", "ON"),
    ("20000.00", "0.00", "3000.00", "ON"),
    ("200000.00", "30000.00", "60000.00", "ON"),
    ("90000.00", "2500.00", "20000.00", "BC"),
    ("45000.00", "0.00", "0.00", "AB"),
]


def _return_input(income: str, rrsp: str, withheld: str, province: str) -> ReturnInput:
    return ReturnInput(
        taxpayer=Taxpayer(
            sin="000000000",
            first_name="Single",
            last_name="Path",
            dob="1980-01-01",
            address_line1="1 Main St",
            city="Toronto",
            province=province,
            postal_code="M1M1M1",
            residency_status="resident",
        ),
        slips_t4=[
            T4Slip(employment_income=D(income), tax_deducted=D(withheld))
        ],
        rrsp_contrib=D(rrsp),
        province=province,
        tax_year=2025,
    )


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(estimator_app)


@pytest.mark.parametrize(("income", "rrsp", "withheld", "province"), SCENARIOS)
class TestAllSurfacesAgree:
    def test_core_engine_and_estimator_dict_agree(self, income, rrsp, withheld, province):
        calc = compute_2025(_return_input(income, rrsp, withheld, province))
        summary = compute_tax_summary(float(D(income)), float(D(rrsp)), province)

        assert calc.totals["net_tax"] == D(str(summary["total_net_tax"]))
        assert calc.line_items["taxable_income"] == D(str(summary["taxable_income"]))
        assert calc.line_items["federal_tax"] == D(str(summary["federal"]["before_credits"]))
        assert calc.line_items["net_federal_tax"] == D(
            str(summary["federal"]["after_credits"])
        )
        assert calc.line_items["prov_tax"] == D(str(summary["provincial"]["before_credits"]))
        assert calc.line_items["net_prov_tax"] == D(
            str(summary["provincial"]["net_provincial"])
        )

    def test_core_engine_and_t4_estimate_agree_on_refund(
        self, income, rrsp, withheld, province
    ):
        calc = compute_2025(_return_input(income, rrsp, withheld, province))
        estimate = estimate_from_t4(
            T4EstimateRequest(
                box14=float(D(income)),
                box22=float(D(withheld)),
                box16=0.0,
                box16a=0.0,
                box18=0.0,
                rrsp=float(D(rrsp)),
                province=province,
            )
        )
        assert calc.totals["net_tax"] == D(str(estimate["total_tax"]))
        assert calc.totals["withholding"] == D(str(estimate["withholding"]))
        assert calc.totals["balance"] == D(str(estimate["balance"]))
        # And the refund/owing flags must follow the same sign convention.
        assert (calc.totals["balance"] < 0) is bool(estimate["is_refund"])
        assert (calc.totals["balance"] > 0) is bool(
            estimate["balance_positive_is_amount_owing"]
        )

    def test_http_endpoints_agree_with_the_core_engine(
        self, client, income, rrsp, withheld, province
    ):
        calc = compute_2025(_return_input(income, rrsp, withheld, province))

        estimate_response = client.get(
            "/tax/estimate",
            params={"income": float(D(income)), "rrsp": float(D(rrsp)), "province": province},
        )
        assert estimate_response.status_code == 200
        assert calc.totals["net_tax"] == D(str(estimate_response.json()["total_net_tax"]))

        t4_response = client.post(
            "/t4/estimate",
            json={
                "box14": float(D(income)),
                "box22": float(D(withheld)),
                "box16": 0.0,
                "box16a": 0.0,
                "box18": 0.0,
                "rrsp": float(D(rrsp)),
                "province": province,
            },
        )
        assert t4_response.status_code == 200
        body = t4_response.json()
        assert calc.totals["net_tax"] == D(str(body["total_tax"]))
        assert calc.totals["balance"] == D(str(body["balance"]))


@pytest.mark.parametrize(("income", "rrsp", "withheld", "province"), SCENARIOS)
def test_bpa_is_derived_from_net_income_on_every_surface(income, rrsp, withheld, province):
    """The specific drift this refactor eliminates.

    The estimator used to phase the BPA on taxable income while the engine used
    total income. Both must now key off net income, which means the estimator's
    reported bpa_used has to match the engine's federal_bpa line exactly --
    including when a deduction moves net income into a different phase-out band.
    """
    calc = compute_2025(_return_input(income, rrsp, withheld, province))
    summary = compute_tax_summary(float(D(income)), float(D(rrsp)), province)
    assert calc.line_items["federal_bpa"] == D(str(summary["federal"]["bpa_used"]))


@pytest.mark.parametrize(("income", "rrsp", "withheld", "province"), SCENARIOS)
@pytest.mark.parametrize(
    ("compute_amounts", "tax_year"), [(amounts_2025, 2025), (amounts_2024, 2024)]
)
def test_computation_reconciles_on_both_years(
    compute_amounts, tax_year, income, rrsp, withheld, province
):
    # net federal + net provincial (additions included) must equal net tax, or a
    # future component could be added without reaching the total.
    supported = {calc.code for calc in list_provincial_calculators(tax_year)}
    if province not in supported:
        pytest.skip(f"{province} has no {tax_year} provincial calculator")

    computation = compute_amounts(
        D(income), D(rrsp), province=province, withholding=D(withheld)
    )
    assert computation.reconciles(), (
        f"{tax_year}: {computation.net_federal_tax} + "
        f"{computation.net_provincial_tax} != {computation.net_tax}"
    )
    assert computation.balance == computation.net_tax - computation.withholding


def test_estimator_no_longer_implements_tax_arithmetic():
    """Guard against the duplicate path creeping back.

    The estimator may format, reshape, and validate payroll box limits. It must
    not import the federal rate/bracket helpers again -- doing so is how the
    second calculator was built the first time.
    """
    import app.wizard.estimator as estimator

    module_names = set(vars(estimator))
    forbidden = {
        "federal_tax_2025",
        "federal_bpa_2025",
        "federal_nrtcs_2025",
        "FED_CREDIT_RATE_2025",
        "NRTC_RATE_2025",
    }
    leaked = forbidden & module_names
    assert not leaked, f"estimator re-imported tax rate helpers: {sorted(leaked)}"
