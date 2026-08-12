"""Phase 2 explanation-contract tests (Plan V3 execution roadmap §2).

Covers the roadmap's stated expectations: model validation, serialization,
stable field names, no dependency on AI providers, and proof the models can
describe deterministic engine output without changing tax math.
"""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.explain import (
    EvidenceRef,
    ExplanationItem,
    ReturnExplanation,
    VerificationStep,
)


def test_explanation_item_minimal_construction():
    item = ExplanationItem(
        id="income_total",
        title="Total income",
        summary="Sum of employment, T4A, and T5 income from your slips.",
    )
    assert item.id == "income_total"
    assert item.amount is None
    assert item.depends_on == []
    assert item.evidence == []
    assert item.verification == []


def test_explanation_item_rejects_unknown_fields():
    # extra="forbid" guards the contract: a mistyped field is an error,
    # not a silently dropped value.
    with pytest.raises(ValidationError):
        ExplanationItem(
            id="net_tax",
            title="Net tax",
            summary="Total payable.",
            ammount=Decimal("123.45"),  # typo for `amount`
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_required_text_fields_reject_blank(blank):
    with pytest.raises(ValidationError):
        ExplanationItem(id=blank.strip(), title="x", summary="y")


def test_stable_field_names_are_locked():
    # These names are the public contract every surface + the future ledger
    # serializes against. If this set changes, it is a breaking change and
    # this test should change deliberately, not by accident.
    assert set(ExplanationItem.model_fields) == {
        "id",
        "title",
        "summary",
        "amount",
        "depends_on",
        "evidence",
        "verification",
    }
    assert set(EvidenceRef.model_fields) == {"kind", "ref", "label", "detail"}
    assert set(VerificationStep.model_fields) == {"check", "surface", "expected"}
    assert set(ReturnExplanation.model_fields) == {"tax_year", "province", "items"}


def test_json_round_trip_is_stable():
    explanation = ReturnExplanation(
        tax_year=2025,
        province="ON",
        items=[
            ExplanationItem(
                id="taxable_income",
                title="Taxable income",
                summary="Total income minus RRSP deductions.",
                amount=Decimal("57000.00"),
                depends_on=["income_total"],
                evidence=[EvidenceRef(kind="calculation", ref="income_total")],
                verification=[
                    VerificationStep(
                        check="Confirm taxable income on the printout.",
                        surface="printout",
                        expected="$57,000.00",
                    )
                ],
            )
        ],
    )
    raw = explanation.model_dump_json()
    restored = ReturnExplanation.model_validate_json(raw)
    assert restored == explanation
    # Decimal serializes to a JSON number string deterministically.
    assert restored.items[0].amount == Decimal("57000.00")


def test_missing_dependencies_is_deterministic_integrity_check():
    explanation = ReturnExplanation(
        tax_year=2025,
        province="ON",
        items=[
            ExplanationItem(
                id="taxable_income",
                title="Taxable income",
                summary="Derives from total income.",
                depends_on=["income_total"],  # not present as an item
            )
        ],
    )
    assert explanation.missing_dependencies() == {"income_total"}
    assert explanation.get("taxable_income") is not None
    assert explanation.get("nope") is None
    assert explanation.item_ids() == ["taxable_income"]


def test_duplicate_item_ids_are_rejected():
    with pytest.raises(ValidationError):
        ReturnExplanation(
            tax_year=2025,
            province="ON",
            items=[
                ExplanationItem(id="income_total", title="A", summary="first"),
                ExplanationItem(id="income_total", title="B", summary="second"),
            ],
        )


def test_duplicate_item_id_is_named_in_the_error():
    # The error must identify which id collided, not just that a collision
    # happened -- and must not implicate ids that were actually unique.
    with pytest.raises(ValidationError) as exc_info:
        ReturnExplanation(
            tax_year=2025,
            province="ON",
            items=[
                ExplanationItem(id="dup", title="A", summary="first"),
                ExplanationItem(id="dup", title="B", summary="second"),
                ExplanationItem(id="only_once", title="C", summary="third"),
            ],
        )
    message = str(exc_info.value)
    assert "dup" in message
    assert "only_once" not in message


def test_unique_ids_construct_and_lookup_normally():
    explanation = ReturnExplanation(
        tax_year=2025,
        province="ON",
        items=[
            ExplanationItem(id="income_total", title="Total income", summary="s"),
            ExplanationItem(
                id="taxable_income",
                title="Taxable income",
                summary="s",
                depends_on=["income_total"],
            ),
        ],
    )
    # get() must not silently pick first/last -- with unique ids there is only
    # ever one candidate, and it must be the right one.
    assert explanation.get("income_total").title == "Total income"
    assert explanation.get("taxable_income").title == "Taxable income"
    assert explanation.item_ids() == ["income_total", "taxable_income"]


def test_dependency_resolution_still_works_with_unique_ids():
    explanation = ReturnExplanation(
        tax_year=2025,
        province="ON",
        items=[
            ExplanationItem(id="a", title="A", summary="s"),
            ExplanationItem(id="b", title="B", summary="s", depends_on=["a"]),
            ExplanationItem(id="c", title="C", summary="s", depends_on=["a", "b"]),
        ],
    )
    assert explanation.missing_dependencies() == set()
    assert explanation.get("c").depends_on == ["a", "b"]


def test_evidence_kind_is_constrained():
    with pytest.raises(ValidationError):
        EvidenceRef(kind="not-a-real-kind", ref="x")  # type: ignore[arg-type]


def test_models_have_no_ai_provider_dependency():
    # The whole explanation layer must work with TeeFoor disabled. Guard
    # against an accidental import of a network/provider client sneaking
    # into the contract module.
    import app.explain.models as explain_models

    forbidden = {"httpx", "requests", "openai", "anthropic", "aiohttp", "urllib3"}
    leaked = forbidden & set(sys.modules) & set(vars(explain_models))
    assert not leaked, f"explanation contracts pulled in: {sorted(leaked)}"


def test_can_describe_a_real_return_calc():
    # Proves the Phase 2 contracts can represent deterministic engine output
    # (the roadmap stop condition) — the mapping shown here is what the
    # Phase 3 engine will formalize. No tax math happens in app.explain.
    from app.core.models import ReturnInput, T4Slip, Taxpayer
    from app.core.tax_years.y2025.calc import compute_return

    calc = compute_return(
        ReturnInput(
            taxpayer=Taxpayer(
                sin="000000000",
                first_name="Test",
                last_name="Filer",
                dob="1990-01-01",
                address_line1="1 Main St",
                city="Toronto",
                province="ON",
                postal_code="M1M1M1",
                residency_status="resident",
            ),
            slips_t4=[T4Slip(employment_income=Decimal("57000.00"))],
            province="ON",
            tax_year=2025,
        )
    )

    items = [
        ExplanationItem(
            id=key,
            title=key.replace("_", " ").title(),
            summary=f"Deterministic engine value for {key}.",
            amount=amount,
            evidence=[EvidenceRef(kind="calculation", ref=key)],
        )
        for key, amount in {**calc.line_items, **calc.totals}.items()
    ]
    explanation = ReturnExplanation(
        tax_year=calc.tax_year, province=calc.province, items=items
    )

    assert explanation.tax_year == 2025
    assert explanation.get("income_total").amount == Decimal("57000.00")
    assert "net_tax" in explanation.item_ids()
    # Every explained amount equals the engine's own number, unchanged.
    for key, amount in {**calc.line_items, **calc.totals}.items():
        assert explanation.get(key).amount == amount
