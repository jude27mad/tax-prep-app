"""DB-backed SlipStagingStore coverage (D1.3 PR B).

Exercises the write-through-to-``documents`` rewire of
:class:`app.ui.slip_ingest.SlipStagingStore`:

  * ``process_upload`` inserts a PROCESSING row, flips to COMPLETE on
    success with detection fields/warnings persisted as JSON blobs.
  * Upload errors (empty, oversize, unsupported) flip the row to ERROR
    with ``error_message`` set and raise :class:`SlipUploadError`.
  * ``job_status`` returns the persisted row; unknown/cross-profile IDs
    raise :class:`SlipJobNotFoundError`.
  * ``apply`` transitions COMPLETE rows to APPLIED and returns
    detections; ``apply(specific_ids)`` works; missing IDs raise.
  * ``clear`` deletes COMPLETE rows but preserves APPLIED rows (audit).
  * Scoping: profile+year form a bucket — rows from other buckets are
    invisible to ``apply``/``clear``/``job_status``.

The fixture spins up an in-memory SQLite with ``StaticPool`` so the
single shared connection makes ``create_all`` visible to the store's
sessions (see engine.py design notes).
"""

from __future__ import annotations

import io

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.config import Settings
from app.db import (
    Base,
    DocumentRow,
    DocumentStatus,
    create_session_factory,
    session_scope,
)
from app.ui.slip_ingest import (
    SlipApplyError,
    SlipJobNotFoundError,
    SlipStagingStore,
    SlipUploadError,
)

T4_TEXT = (
    b"T4 Statement of Remuneration Paid\n"
    b"Box 14 Employment income: $55,123.45\n"
    b"Box 22 Income tax deducted 8,765.43\n"
    b"CPP contributions (Box 16) 3,000.99\n"
    b"EI premiums Box 18 890.12\n"
)

T5_TEXT = (
    b"T5 Statement of Investment Income\n"
    b"Box 13 Interest income: 100.00\n"
    b"Box 25 Eligible dividends: 250.00\n"
)


def _upload(filename: str, data: bytes, content_type: str | None = None) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(data),
        headers={"content-type": content_type} if content_type else None,
    )


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


@pytest_asyncio.fixture
async def store(engine: AsyncEngine) -> SlipStagingStore:
    return SlipStagingStore(create_session_factory(engine))


@pytest.fixture
def settings(tmp_path) -> Settings:
    # Re-use app Settings but point artifact_root to tmp_path so
    # _persist_upload drops its files under the test directory.
    return Settings(artifact_root=str(tmp_path / "artifacts"))


@pytest.mark.asyncio
async def test_process_upload_persists_complete_row(
    store: SlipStagingStore,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    status = await store.process_upload(
        "jane-doe", 2025, _upload("t4.txt", T4_TEXT), settings=settings
    )
    assert status.status == "complete"
    assert status.detection is not None
    assert status.detection.slip_type == "t4"
    assert status.detection.fields["employment_income"] == "55123.45"

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        row = await session.get(DocumentRow, status.job_id)
        assert row is not None
        assert row.profile_slug == "jane-doe"
        assert row.tax_year == 2025
        assert row.status == DocumentStatus.COMPLETE.value
        assert row.slip_type == "t4"
        assert row.size_bytes == len(T4_TEXT)
        assert row.raw_fields["employment_income"] == "55123.45"
        assert row.warnings == []


@pytest.mark.asyncio
async def test_process_upload_empty_marks_error(
    store: SlipStagingStore,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    with pytest.raises(SlipUploadError):
        await store.process_upload(
            "jane", 2025, _upload("empty.txt", b""), settings=settings
        )

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "jane")
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].status == DocumentStatus.ERROR.value
    assert rows[0].error_message == "Uploaded file was empty"


@pytest.mark.asyncio
async def test_process_upload_oversize_marks_error(
    store: SlipStagingStore,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    oversize = b"T4 " + (b"0" * (9 * 1024 * 1024))
    with pytest.raises(SlipUploadError):
        await store.process_upload(
            "jane", 2025, _upload("big.txt", oversize), settings=settings
        )

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "jane")
        result = await session.execute(stmt)
        row = result.scalars().first()
    assert row is not None
    assert row.status == DocumentStatus.ERROR.value
    assert "maximum allowed size" in (row.error_message or "")


@pytest.mark.asyncio
async def test_job_status_returns_complete(
    store: SlipStagingStore,
    settings: Settings,
) -> None:
    uploaded = await store.process_upload(
        "jane", 2025, _upload("t4.txt", T4_TEXT), settings=settings
    )
    status = await store.job_status("jane", 2025, uploaded.job_id)
    assert status.status == "complete"
    assert status.detection is not None
    assert status.detection.id == uploaded.job_id


@pytest.mark.asyncio
async def test_job_status_unknown_id_raises(store: SlipStagingStore) -> None:
    with pytest.raises(SlipJobNotFoundError):
        await store.job_status("jane", 2025, "not-a-real-id")


@pytest.mark.asyncio
async def test_job_status_rejects_cross_profile(
    store: SlipStagingStore, settings: Settings
) -> None:
    uploaded = await store.process_upload(
        "jane", 2025, _upload("t4.txt", T4_TEXT), settings=settings
    )
    with pytest.raises(SlipJobNotFoundError):
        await store.job_status("other-user", 2025, uploaded.job_id)
    with pytest.raises(SlipJobNotFoundError):
        await store.job_status("jane", 2024, uploaded.job_id)


@pytest.mark.asyncio
async def test_apply_all_flips_complete_to_applied(
    store: SlipStagingStore,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    a = await store.process_upload(
        "jane", 2025, _upload("a.txt", T4_TEXT), settings=settings
    )
    b = await store.process_upload(
        "jane", 2025, _upload("b.txt", T5_TEXT), settings=settings
    )
    assert a.status == "complete" and b.status == "complete"

    applied = await store.apply("jane", 2025)
    assert {d.id for d in applied} == {a.job_id, b.job_id}

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "jane")
        rows = list((await session.execute(stmt)).scalars().all())
    statuses = {row.id: row.status for row in rows}
    assert statuses[a.job_id] == DocumentStatus.APPLIED.value
    assert statuses[b.job_id] == DocumentStatus.APPLIED.value


@pytest.mark.asyncio
async def test_apply_specific_ids(
    store: SlipStagingStore, engine: AsyncEngine, settings: Settings
) -> None:
    a = await store.process_upload(
        "jane", 2025, _upload("a.txt", T4_TEXT), settings=settings
    )
    b = await store.process_upload(
        "jane", 2025, _upload("b.txt", T5_TEXT), settings=settings
    )
    applied = await store.apply("jane", 2025, [a.job_id])
    assert len(applied) == 1 and applied[0].id == a.job_id

    # b still COMPLETE, a flipped to APPLIED
    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "jane")
        rows = list((await session.execute(stmt)).scalars().all())
    statuses = {row.id: row.status for row in rows}
    assert statuses[a.job_id] == DocumentStatus.APPLIED.value
    assert statuses[b.job_id] == DocumentStatus.COMPLETE.value


@pytest.mark.asyncio
async def test_apply_missing_id_raises(
    store: SlipStagingStore, settings: Settings
) -> None:
    await store.process_upload(
        "jane", 2025, _upload("a.txt", T4_TEXT), settings=settings
    )
    with pytest.raises(SlipApplyError):
        await store.apply("jane", 2025, ["bogus-id"])


@pytest.mark.asyncio
async def test_clear_drops_complete_preserves_applied(
    store: SlipStagingStore, engine: AsyncEngine, settings: Settings
) -> None:
    a = await store.process_upload(
        "jane", 2025, _upload("a.txt", T4_TEXT), settings=settings
    )
    b = await store.process_upload(
        "jane", 2025, _upload("b.txt", T5_TEXT), settings=settings
    )
    # Apply a (now APPLIED), leave b as COMPLETE
    await store.apply("jane", 2025, [a.job_id])
    await store.clear("jane", 2025)

    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "jane")
        rows = list((await session.execute(stmt)).scalars().all())
    statuses = {row.id: row.status for row in rows}
    assert a.job_id in statuses and statuses[a.job_id] == DocumentStatus.APPLIED.value
    assert b.job_id not in statuses


@pytest.mark.asyncio
async def test_apply_and_clear_respect_bucket_scope(
    store: SlipStagingStore, settings: Settings
) -> None:
    mine = await store.process_upload(
        "jane", 2025, _upload("mine.txt", T4_TEXT), settings=settings
    )
    theirs = await store.process_upload(
        "john", 2025, _upload("theirs.txt", T4_TEXT), settings=settings
    )
    other_year = await store.process_upload(
        "jane", 2024, _upload("oy.txt", T4_TEXT), settings=settings
    )

    applied = await store.apply("jane", 2025)
    assert {d.id for d in applied} == {mine.job_id}

    # theirs and other_year still COMPLETE; job_status proves it
    s1 = await store.job_status("john", 2025, theirs.job_id)
    s2 = await store.job_status("jane", 2024, other_year.job_id)
    assert s1.status == "complete"
    assert s2.status == "complete"
