"""Prior-state and limit contracts (Plan V3 execution roadmap PR 8).

``PriorTaxState`` records the opening balances and limits a return inherits
from prior years: tuition carryforwards (federal and Ontario, separately), the
RRSP deduction limit, unused RRSP/PRPP/SPP contributions, and required HBP/LLP
repayments.

The contract is deliberately **calculation-neutral**. Nothing in the 2024 or
2025 computation handlers reads it, so a return carrying non-zero prior state
must compute byte-for-byte identically to the same return without it. The
tests below pin that neutrality as hard as they pin the validation rules,
because the failure mode this PR must not introduce is a silent change to a
refund. Schedule 11 and Schedule 7 consume the state in later roadmap work.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.models import (
    PriorAmount,
    PriorAmountProvenance,
    PriorTaxState,
    ReturnInput,
    RRSPReceipt,
    T4Slip,
    Taxpayer,
    TuitionSlip,
)
from app.core.tax_years.y2024.calc import compute_return as compute_2024
from app.core.tax_years.y2025.calc import compute_return as compute_2025
from app.core.validate.pre_submit import validate_return_input
from tests.fixtures.min_client import make_min_input, make_provincial_examples

D = Decimal

SOURCE_KINDS = (
    "cra_afr",
    "prior_noa",
    "prior_reassessment",
    "prior_filed_return",
    "manual",
)
DOCUMENT_SOURCE_KINDS = tuple(kind for kind in SOURCE_KINDS if kind != "manual")

CAPTURED_AT = datetime(2026, 3, 1, 14, 30, tzinfo=timezone.utc)

PRIOR_AMOUNT_FIELDS = (
    "opening_federal_tuition_carryforward",
    "opening_ontario_tuition_carryforward",
    "rrsp_deduction_limit",
    "opening_unused_rrsp_contributions",
    "hbp_required_repayment",
    "llp_required_repayment",
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _provenance(source: str = "cra_afr", **overrides) -> PriorAmountProvenance:
    kwargs: dict[str, object] = {
        "source": source,
        "source_tax_year": 2024,
        "captured_at": CAPTURED_AT,
        "confirmed": True,
        "reference_id": None if source == "manual" else "AFR-2024-0001",
    }
    kwargs.update(overrides)
    return PriorAmountProvenance(**kwargs)  # type: ignore[arg-type]


def _amount(value: str, source: str = "cra_afr") -> PriorAmount:
    return PriorAmount(amount=D(value), provenance=_provenance(source))


def _populated_state(tax_year: int = 2025) -> PriorTaxState:
    """A prior state with every amount non-zero and independently sourced."""
    return PriorTaxState(
        applies_to_tax_year=tax_year,
        established_as_of=date(2026, 3, 1),
        opening_federal_tuition_carryforward=_amount("13953.81", "cra_afr"),
        opening_ontario_tuition_carryforward=_amount("7420.55", "prior_noa"),
        rrsp_deduction_limit=_amount("18500.00", "prior_noa"),
        opening_unused_rrsp_contributions=_amount("1200.00", "prior_filed_return"),
        hbp_required_repayment=_amount("1666.67", "cra_afr"),
        llp_required_repayment=_amount("500.00", "manual"),
    )


def _taxpayer() -> Taxpayer:
    return Taxpayer(
        sin="046454286",
        first_name="Prior",
        last_name="State",
        dob=date(1985, 5, 5),
        address_line1="1 Main St",
        city="Toronto",
        province="ON",
        postal_code="M1M1M1",
        residency_status="resident",
    )


def _return(*, tax_year: int = 2025, **overrides) -> ReturnInput:
    kwargs: dict[str, object] = {
        "taxpayer": _taxpayer(),
        "slips_t4": [T4Slip(employment_income=D("68000.00"), tax_deducted=D("12000.00"))],
        "province": "ON",
        "tax_year": tax_year,
    }
    kwargs.update(overrides)
    return ReturnInput(**kwargs)  # type: ignore[arg-type]


def _codes(exc: ValidationError) -> list[str]:
    """The stable issue slugs carried in a validation error's messages."""
    return [str(error["msg"]).split(":")[0].removeprefix("Value error, ") for error in exc.errors()]


def _locs(exc: ValidationError) -> list[tuple]:
    return [error["loc"] for error in exc.errors()]


# --- 1/2: default construction and backward compatibility -------------------


def test_return_input_constructs_without_prior_tax_state():
    req = _return()
    assert isinstance(req.prior_tax_state, PriorTaxState)
    # The pre-existing current-year fields keep their meaning and defaults.
    assert req.rrsp_contrib == D("0.00")
    assert req.tuition_claim == D("0.00")
    assert req.tuition_transfer_to_spouse == D("0.00")


def test_omitted_prior_state_defaults_to_empty_and_unidentified():
    state = _return().prior_tax_state
    assert state.applies_to_tax_year is None
    assert state.established_as_of is None
    assert not state.is_established()
    for field in PRIOR_AMOUNT_FIELDS:
        entry = getattr(state, field)
        assert entry.amount == D("0.00")
        assert entry.provenance is None


def test_default_prior_state_is_not_shared_between_returns():
    """The default is a factory, not one mutable instance shared by every
    return -- otherwise seeding one return's carryforward would seed them all."""
    first, second = _return(), _return()
    assert first.prior_tax_state is not second.prior_tax_state
    first.prior_tax_state.opening_federal_tuition_carryforward = _amount("100.00")
    assert second.prior_tax_state.opening_federal_tuition_carryforward.amount == D("0.00")


def test_prior_state_keeps_federal_and_ontario_tuition_separate():
    state = _populated_state()
    assert state.opening_federal_tuition_carryforward.amount == D("13953.81")
    assert state.opening_ontario_tuition_carryforward.amount == D("7420.55")
    assert (
        state.opening_federal_tuition_carryforward.amount
        != state.opening_ontario_tuition_carryforward.amount
    )


def test_prior_state_carries_no_current_year_outputs():
    """Tuition used/transferred/closing and RRSP claimed/closing are outputs of
    later deterministic calculations, not prior inputs. ``extra="forbid"``
    turns an attempt to smuggle one in here into a rejection."""
    forbidden = {
        "tuition_used": "1.00",
        "tuition_transferred": "1.00",
        "closing_tuition_carryforward": "1.00",
        "rrsp_deduction_claimed": "1.00",
        "closing_unused_rrsp_contributions": "1.00",
    }
    for field, value in forbidden.items():
        assert not hasattr(PriorTaxState(), field)
        with pytest.raises(ValidationError):
            PriorTaxState(**{field: value})  # type: ignore[arg-type]


# --- 3: cent quantization ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("13953.8", "13953.80"), ("18500", "18500.00"), ("1666.666", "1666.67")],
)
def test_prior_amount_quantizes_to_cents(raw, expected):
    assert _amount(raw).amount == D(expected)


def test_zero_prior_amount_quantizes_to_cents():
    assert PriorAmount().amount == D("0.00")
    assert PriorAmount(amount=D("0")).amount == D("0.00")


# --- 4/5/6: sign and provenance rules --------------------------------------


def test_negative_prior_amount_is_rejected():
    with pytest.raises(ValidationError) as exc:
        PriorAmount(amount=D("-0.01"), provenance=_provenance())
    assert "prior_amount_negative" in _codes(exc.value)


def test_positive_prior_amount_without_provenance_is_rejected():
    with pytest.raises(ValidationError) as exc:
        PriorAmount(amount=D("1.00"))
    assert "prior_amount_missing_provenance" in _codes(exc.value)


def test_zero_prior_amount_without_provenance_is_accepted():
    entry = PriorAmount(amount=D("0.00"))
    assert entry.amount == D("0.00")
    assert entry.provenance is None


def test_state_carrying_amounts_requires_identity():
    with pytest.raises(ValidationError) as exc:
        PriorTaxState(rrsp_deduction_limit=_amount("18500.00"))
    assert "prior_state_missing_identity" in _codes(exc.value)


# --- 7: supported source kinds ---------------------------------------------


@pytest.mark.parametrize("source", SOURCE_KINDS)
def test_every_supported_source_kind_is_accepted(source):
    entry = _amount("100.00", source)
    assert entry.provenance is not None
    assert entry.provenance.source == source


def test_unsupported_source_kind_is_rejected():
    with pytest.raises(ValidationError) as exc:
        _provenance("guessed_from_memory")
    assert _locs(exc.value) == [("source",)]


# --- 8: serialization round trip -------------------------------------------


def test_json_round_trip_preserves_exact_decimals():
    original = _return(prior_tax_state=_populated_state())
    restored = ReturnInput.model_validate_json(original.model_dump_json())

    assert restored.prior_tax_state == original.prior_tax_state
    for field in PRIOR_AMOUNT_FIELDS:
        before = getattr(original.prior_tax_state, field)
        after = getattr(restored.prior_tax_state, field)
        assert after.amount == before.amount
        # Equality alone would pass for 13953.8 vs 13953.81 rounding drift; the
        # exact string is what a carryforward has to survive as.
        assert str(after.amount) == str(before.amount)
    assert restored.prior_tax_state.opening_federal_tuition_carryforward.amount == D("13953.81")


def test_json_round_trip_preserves_provenance_details():
    original = _populated_state()
    restored = PriorTaxState.model_validate_json(original.model_dump_json())
    provenance = restored.opening_federal_tuition_carryforward.provenance
    assert provenance is not None
    assert provenance.source == "cra_afr"
    assert provenance.source_tax_year == 2024
    assert provenance.captured_at == CAPTURED_AT
    assert provenance.confirmed is True
    assert provenance.reference_id == "AFR-2024-0001"
    assert restored.applies_to_tax_year == 2025
    assert restored.established_as_of == date(2026, 3, 1)


# --- 9/10: reference identifiers -------------------------------------------


@pytest.mark.parametrize("source", DOCUMENT_SOURCE_KINDS)
def test_document_sources_require_a_reference_id(source):
    with pytest.raises(ValidationError) as exc:
        _provenance(source, reference_id=None)
    assert "prior_provenance_missing_reference" in _codes(exc.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_document_sources_reject_a_blank_reference_id(blank):
    with pytest.raises(ValidationError) as exc:
        _provenance("prior_noa", reference_id=blank)
    assert "prior_provenance_missing_reference" in _codes(exc.value)


def test_manual_source_is_permitted_without_a_reference_id():
    provenance = _provenance("manual", reference_id=None)
    assert provenance.source == "manual"
    assert provenance.reference_id is None


def test_manual_source_may_still_carry_a_review_reference():
    provenance = _provenance("manual", review_ref="REVIEW-77")
    assert provenance.review_ref == "REVIEW-77"


# --- 11: capture timestamps -------------------------------------------------


def test_timezone_naive_captured_at_is_rejected():
    with pytest.raises(ValidationError) as exc:
        _provenance(captured_at=datetime(2026, 3, 1, 14, 30))
    assert "prior_provenance_naive_timestamp" in _codes(exc.value)


@pytest.mark.parametrize(
    "tz", [timezone.utc, timezone(timedelta(hours=-5)), timezone(timedelta(hours=5, minutes=30))]
)
def test_timezone_aware_captured_at_is_accepted(tz):
    provenance = _provenance(captured_at=datetime(2026, 3, 1, 14, 30, tzinfo=tz))
    assert provenance.captured_at.utcoffset() is not None


# --- 12: the state's year must be the return's year ------------------------


@pytest.mark.parametrize("tax_year", [2024, 2025])
def test_matching_prior_state_tax_year_is_accepted(tax_year):
    req = _return(tax_year=tax_year, prior_tax_state=_populated_state(tax_year))
    assert req.prior_tax_state.applies_to_tax_year == tax_year


@pytest.mark.parametrize(("return_year", "state_year"), [(2025, 2024), (2024, 2025)])
def test_mismatched_prior_state_tax_year_is_rejected(return_year, state_year):
    with pytest.raises(ValidationError) as exc:
        _return(tax_year=return_year, prior_tax_state=_populated_state(state_year))
    assert "prior_state_tax_year_mismatch" in _codes(exc.value)


def test_source_tax_year_may_differ_from_the_state_year():
    """A 2022 reassessment can restate a balance that opens 2025 -- the source
    document's year is not the year the state applies to."""
    state = PriorTaxState(
        applies_to_tax_year=2025,
        established_as_of=date(2026, 3, 1),
        opening_federal_tuition_carryforward=PriorAmount(
            amount=D("100.00"),
            provenance=_provenance("prior_reassessment", source_tax_year=2022),
        ),
    )
    req = _return(prior_tax_state=state)
    provenance = req.prior_tax_state.opening_federal_tuition_carryforward.provenance
    assert provenance is not None
    assert provenance.source_tax_year == 2022


# --- 13: field paths and issue codes ---------------------------------------
#
# Paths are asserted against whole-payload validation (the shape the UI and API
# actually submit), because that is where a caller needs to be told *which*
# amount is wrong. Building a nested model directly reports a path relative to
# that model, which is correct but says nothing about the full contract.


def _payload(**state_fields) -> dict:
    payload = _return().model_dump(mode="json")
    payload["prior_tax_state"].update(
        {"applies_to_tax_year": 2025, "established_as_of": "2026-03-01", **state_fields}
    )
    return payload


def _provenance_payload(**overrides) -> dict:
    return {
        "source": "cra_afr",
        "source_tax_year": 2024,
        "captured_at": "2026-03-01T14:30:00+00:00",
        "confirmed": True,
        "reference_id": "AFR-2024-0001",
        **overrides,
    }


def test_negative_amount_reports_its_precise_field_path():
    payload = _payload(
        rrsp_deduction_limit={"amount": "-1.00", "provenance": _provenance_payload()}
    )
    with pytest.raises(ValidationError) as exc:
        ReturnInput.model_validate(payload)
    assert _locs(exc.value) == [("prior_tax_state", "rrsp_deduction_limit")]
    assert _codes(exc.value) == ["prior_amount_negative"]


def test_missing_provenance_reports_the_offending_amount_not_the_whole_state():
    payload = _payload(opening_unused_rrsp_contributions={"amount": "1200.00"})
    with pytest.raises(ValidationError) as exc:
        ReturnInput.model_validate(payload)
    assert _locs(exc.value) == [("prior_tax_state", "opening_unused_rrsp_contributions")]
    assert _codes(exc.value) == ["prior_amount_missing_provenance"]


def test_naive_timestamp_reports_its_precise_field_path():
    payload = _payload(
        hbp_required_repayment={
            "amount": "500.00",
            "provenance": _provenance_payload(
                source="manual", reference_id=None, captured_at="2026-03-01T14:30:00"
            ),
        }
    )
    with pytest.raises(ValidationError) as exc:
        ReturnInput.model_validate(payload)
    assert _locs(exc.value) == [
        ("prior_tax_state", "hbp_required_repayment", "provenance", "captured_at")
    ]
    assert _codes(exc.value) == ["prior_provenance_naive_timestamp"]


def test_missing_reference_reports_the_offending_provenance():
    payload = _payload(
        opening_ontario_tuition_carryforward={
            "amount": "7420.55",
            "provenance": _provenance_payload(source="prior_noa", reference_id=None),
        }
    )
    with pytest.raises(ValidationError) as exc:
        ReturnInput.model_validate(payload)
    assert _locs(exc.value) == [
        ("prior_tax_state", "opening_ontario_tuition_carryforward", "provenance")
    ]
    assert _codes(exc.value) == ["prior_provenance_missing_reference"]


def test_tax_year_mismatch_reports_the_return_level_path():
    with pytest.raises(ValidationError) as exc:
        _return(tax_year=2024, prior_tax_state=_populated_state(2025))
    assert _locs(exc.value) == [()]
    assert _codes(exc.value) == ["prior_state_tax_year_mismatch"]


# --- 14/15: current-year slips never seed prior state ----------------------


def test_t2202_tuition_slips_do_not_seed_opening_tuition_carryforwards():
    req = _return(
        tuition_slips=[
            TuitionSlip(
                institution_name="Uni",
                eligible_tuition=D("6000.00"),
                months_full_time=8,
            )
        ],
        tuition_claim=D("6000.00"),
    )
    state = req.prior_tax_state
    assert state.opening_federal_tuition_carryforward.amount == D("0.00")
    assert state.opening_ontario_tuition_carryforward.amount == D("0.00")
    assert not state.is_established()
    # Current-year tuition stays exactly where it was.
    assert req.tuition_claim == D("6000.00")
    assert req.tuition_slips[0].eligible_tuition == D("6000.00")


def test_rrsp_receipts_do_not_seed_the_limit_or_opening_contributions():
    req = _return(
        rrsp_receipts=[RRSPReceipt(contribution_amount=D("5000.00"), issuer="Bank")],
        rrsp_contrib=D("5000.00"),
    )
    state = req.prior_tax_state
    assert state.rrsp_deduction_limit.amount == D("0.00")
    assert state.opening_unused_rrsp_contributions.amount == D("0.00")
    assert not state.is_established()
    assert req.rrsp_contrib == D("5000.00")


# --- 16-19: calculation neutrality -----------------------------------------


@pytest.mark.parametrize(("compute", "tax_year"), [(compute_2025, 2025), (compute_2024, 2024)])
class TestCalculationNeutrality:
    def test_compute_return_does_not_mutate_prior_state(self, compute, tax_year):
        req = _return(tax_year=tax_year, prior_tax_state=_populated_state(tax_year))
        before = req.prior_tax_state.model_dump_json()
        compute(req)
        assert req.prior_tax_state.model_dump_json() == before

    def test_prior_state_does_not_change_any_computed_amount(self, compute, tax_year):
        without = compute(_return(tax_year=tax_year))
        with_state = compute(
            _return(tax_year=tax_year, prior_tax_state=_populated_state(tax_year))
        )
        assert with_state.line_items == without.line_items
        assert with_state.totals == without.totals
        assert with_state.provincial_additions == without.provincial_additions
        assert with_state.cpp == without.cpp
        assert with_state.ei == without.ei

    def test_prior_rrsp_state_does_not_reach_the_rrsp_deduction(self, compute, tax_year):
        """The limit and unused contributions are Schedule 7 inputs for later
        work. Consuming them now would silently enlarge the deduction."""
        without = compute(_return(tax_year=tax_year, rrsp_contrib=D("5000.00")))
        with_state = compute(
            _return(
                tax_year=tax_year,
                rrsp_contrib=D("5000.00"),
                prior_tax_state=_populated_state(tax_year),
            )
        )
        assert with_state.line_items["net_income"] == without.line_items["net_income"]
        assert with_state.totals["balance"] == without.totals["balance"]

    def test_prior_tuition_state_does_not_reach_federal_credits(self, compute, tax_year):
        without = compute(_return(tax_year=tax_year))
        with_state = compute(
            _return(tax_year=tax_year, prior_tax_state=_populated_state(tax_year))
        )
        assert with_state.line_items["federal_credits"] == without.line_items["federal_credits"]
        assert with_state.line_items["prov_credits"] == without.line_items["prov_credits"]


@pytest.mark.parametrize(("compute", "tax_year"), [(compute_2025, 2025), (compute_2024, 2024)])
def test_known_balance_is_unchanged_with_and_without_prior_state(compute, tax_year):
    """Pin the actual numbers, not just their equality to each other: a change
    that broke both branches identically would still pass the comparison."""
    without = compute(_return(tax_year=tax_year))
    with_state = compute(_return(tax_year=tax_year, prior_tax_state=_populated_state(tax_year)))
    assert without.totals["withholding"] == D("12000.00")
    assert with_state.totals["balance"] == without.totals["balance"]
    assert with_state.line_items["income_total"] == D("68000.00")


# --- 20: existing fixtures and payloads keep validating --------------------


@pytest.mark.parametrize("tax_year", [2024, 2025])
def test_existing_min_client_fixture_still_validates(tax_year):
    req = make_min_input(tax_year=tax_year, include_examples=True)
    assert validate_return_input(req) == []
    assert not req.prior_tax_state.is_established()


def test_existing_provincial_example_fixtures_still_validate():
    for province, req in make_provincial_examples().items():
        assert validate_return_input(req) == [], province
        assert req.prior_tax_state.applies_to_tax_year is None


def test_existing_input_json_without_prior_state_still_validates():
    """Payloads serialized before this field existed must keep loading."""
    payload = make_min_input().model_dump(mode="json")
    payload.pop("prior_tax_state")
    restored = ReturnInput.model_validate(payload)
    assert restored.prior_tax_state == PriorTaxState()


# --- 21: the sample CLI refund is unchanged --------------------------------


def test_sample_cli_refund_is_unchanged():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.main",
            "--data",
            "tests/fixtures/user_data.toml",
            "--profile",
            "sample",
            "--quick",
            "--color",
            "never",
            "--no-save",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert "Expected refund: $1,313.76" in result.stdout
