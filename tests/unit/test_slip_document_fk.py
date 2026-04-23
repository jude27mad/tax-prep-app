"""D1.3 PR C: slip models carry an optional document_id soft-FK.

Scope:
  * Each slip model (T4, T4A, T5, Tuition, RRSP) accepts and round-trips
    a ``document_id`` string through construction, ``model_dump``, and
    ``model_validate``.
  * ``document_id`` defaults to None so existing call sites that don't
    wire it continue to work.
  * ``ReturnInput`` preserves ``document_id`` on each contained slip
    when validated from a raw payload dict — proves the UI → model
    plumbing chains cleanly.
  * The persistent DocumentRow.id (UUID) format is compatible — i.e.
    a DocumentRow produced by SlipStagingStore can have its id copied
    onto T4Slip.document_id without further massaging.

We don't enforce referential integrity at the Pydantic layer — the FK
is soft (string). Cross-table consistency between slips and the
``documents`` table is the caller's responsibility, mirroring the
plan's decision to avoid coupling the tax-return domain model to the
persistence schema.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.models import (
    DeductionCreditInputs,
    Household,
    RRSPReceipt,
    ReturnInput,
    T4ASlip,
    T4Slip,
    T5Slip,
    Taxpayer,
    TuitionSlip,
)
from app.db import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
    create_session_factory,
    session_scope,
)


def _taxpayer() -> Taxpayer:
    return Taxpayer(
        sin="130 692 544",
        first_name="Jane",
        last_name="Doe",
        dob=date(1990, 1, 1),
        address_line1="1 Test St",
        city="Toronto",
        province="ON",
        postal_code="M5V 1A1",
        residency_status="resident",
    )


# ---------------------------------------------------------------------------
# Pure model tests: each slip carries document_id optionally.
# ---------------------------------------------------------------------------


def test_t4_slip_accepts_document_id() -> None:
    doc_id = str(uuid.uuid4())
    slip = T4Slip(employment_income=Decimal("10000.00"), document_id=doc_id)
    assert slip.document_id == doc_id
    dumped = slip.model_dump()
    assert dumped["document_id"] == doc_id
    round_trip = T4Slip.model_validate(dumped)
    assert round_trip.document_id == doc_id


def test_t4_slip_document_id_defaults_to_none() -> None:
    slip = T4Slip(employment_income=Decimal("1.00"))
    assert slip.document_id is None


@pytest.mark.parametrize(
    "cls, kwargs",
    [
        (T4ASlip, {"pension_income": Decimal("500.00")}),
        (T5Slip, {"interest_income": Decimal("100.00")}),
        (TuitionSlip, {"institution_name": "Uni", "eligible_tuition": Decimal("1000")}),
        (RRSPReceipt, {"contribution_amount": Decimal("250.00")}),
    ],
)
def test_other_slips_accept_document_id(cls, kwargs) -> None:
    doc_id = str(uuid.uuid4())
    instance = cls(**kwargs, document_id=doc_id)
    assert instance.document_id == doc_id
    assert cls.model_validate(instance.model_dump()).document_id == doc_id


def test_return_input_round_trips_document_id_on_slips() -> None:
    t4_doc = str(uuid.uuid4())
    t5_doc = str(uuid.uuid4())
    rrsp_doc = str(uuid.uuid4())

    payload = {
        "taxpayer": _taxpayer().model_dump(mode="json"),
        "household": Household(marital_status="single").model_dump(),
        "slips_t4": [
            {
                "employment_income": "55123.45",
                "cpp_contrib": "3000.99",
                "document_id": t4_doc,
            }
        ],
        "slips_t5": [{"interest_income": "100.00", "document_id": t5_doc}],
        "rrsp_receipts": [
            {"contribution_amount": "250.00", "document_id": rrsp_doc}
        ],
        "deductions": DeductionCreditInputs().model_dump(),
        "province": "ON",
        "tax_year": 2025,
    }

    req = ReturnInput.model_validate(payload)
    assert req.slips_t4[0].document_id == t4_doc
    assert req.slips_t5[0].document_id == t5_doc
    assert req.rrsp_receipts[0].document_id == rrsp_doc


def test_return_input_accepts_slips_without_document_id() -> None:
    """Regression guard: legacy payloads (no document_id) still validate."""
    payload = {
        "taxpayer": _taxpayer().model_dump(mode="json"),
        "household": Household(marital_status="single").model_dump(),
        "slips_t4": [{"employment_income": "42000.00"}],
        "deductions": DeductionCreditInputs().model_dump(),
        "province": "ON",
        "tax_year": 2025,
    }
    req = ReturnInput.model_validate(payload)
    assert req.slips_t4[0].document_id is None


# ---------------------------------------------------------------------------
# Provenance round-trip: a persisted DocumentRow.id can be stamped onto a
# slip and read back. Verifies the "soft FK" contract the plan describes.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_document_id_matches_persisted_row(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)

    # Persist a DocumentRow as the provenance anchor.
    async with session_scope(factory) as session:
        doc = DocumentRow(
            profile_slug="jane",
            tax_year=2025,
            source_type=DocumentSource.UPLOAD.value,
            slip_type="t4",
            status=DocumentStatus.APPLIED.value,
            original_filename="t4.pdf",
            raw_fields={"box14": "50000.00"},
            warnings=[],
        )
        session.add(doc)
        await session.flush()
        persisted_id = doc.id

    # Build a slip pointing at the persisted row.
    slip = T4Slip(employment_income=Decimal("50000.00"), document_id=persisted_id)
    assert slip.document_id == persisted_id
    assert len(slip.document_id) == 36  # UUID string length

    # Round-trip: reload the anchor using the slip's FK.
    async with session_scope(factory) as session:
        row = await session.get(DocumentRow, slip.document_id)
        assert row is not None
        assert row.slip_type == "t4"
        assert row.raw_fields["box14"] == "50000.00"
