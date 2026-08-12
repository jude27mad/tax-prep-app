"""Legacy JSON EFILE envelope serialization (app.efile.records).

ReturnCalc.provincial_additions is a field separate from line_items (see
app/core/models.py and app/core/lines.py) so the printout doesn't misclassify
new T1 lines as provincial additions. build_records must serialize both, or the
legacy JSON payload silently drops Ontario surtax and health premium while
totals["net_tax"] still reflects them -- a payload where the components don't
sum to the total it claims to justify.
"""

from __future__ import annotations

from decimal import Decimal

from app.efile.records import EfileEnvelope, build_records
from tests.fixtures.min_client import make_min_input
from app.core.tax_years._2025_alias import compute_return
from app.core.tax_years.y2025.calc import compute_full_2025

D = Decimal


def _envelope() -> EfileEnvelope:
    return EfileEnvelope(
        software_id="TAXAPP",
        software_ver="1.0",
        transmitter_id="T0000001",
        environment="CERT",
    )


def test_provincial_additions_survive_legacy_serialization():
    request = make_min_input(include_examples=True, province="ON")
    calc = compute_return(request)
    assert calc.provincial_additions, "fixture must actually exercise ON additions"

    record = build_records(_envelope(), request, calc)

    assert record["return"]["provincial_additions"] == calc.provincial_additions
    assert "ontario_health_premium" in record["return"]["provincial_additions"]
    # And it must not have been folded back into line_items either.
    assert "ontario_health_premium" not in record["return"]["line_items"]


def test_provincial_additions_reconcile_with_net_tax():
    """net_tax minus the record's additions equals tax payable before additions.

    line_items["federal_tax"] / ["prov_tax"] are pre-credit gross amounts (see
    app/core/tax_years/y2025/calc.py), so they cannot be summed directly against
    net_tax -- credits aren't exposed on ReturnCalc at all. The independently
    computed breakdown is the ground truth for pre-addition payable; this proves
    the record's additions are exactly the gap between that and net_tax, i.e.
    they weren't dropped and weren't double-counted.
    """
    request = make_min_input(include_examples=True, province="ON")
    calc = compute_return(request)
    record = build_records(_envelope(), request, calc)

    additions_total = sum(record["return"]["provincial_additions"].values(), D("0.00"))
    net_tax = record["return"]["totals"]["net_tax"]

    breakdown = compute_full_2025(
        calc.line_items["taxable_income"], calc.line_items["net_income"], province="ON"
    )
    tax_before_additions = max(
        D("0.00"), breakdown.federal_tax - breakdown.federal_credits
    ) + max(D("0.00"), breakdown.provincial_tax - breakdown.provincial_credits)

    assert tax_before_additions + additions_total == net_tax
