"""Smoke tests for the persistent document vault (D1.3 PR A).

Scope:
  * Config + URL resolution from :func:`app.db.build_database_url`.
  * Engine/session factory against an in-memory SQLite database.
  * Round-trip CRUD on a :class:`DocumentRow` (insert, read, update, list,
    query by composite index, JSON round-trip).
  * End-to-end Alembic upgrade → downgrade against a scratch SQLite file
    so CI catches migration drift before it lands on a real DB.

These tests exercise the raw persistence layer only — ``SlipStagingStore``
rewiring lands in PR B and slip FKs land in PR C.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from app.config import Settings
from app.db import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
    build_database_url,
    create_engine,
    create_session_factory,
    dispose_engine,
    session_scope,
)

def _temp_sqlite_url(tmp_path: Path) -> str:
    # NullPool + in-memory SQLite don't share state across connections; use a
    # per-test file so create_all and the later session see the same DB.
    return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def test_build_database_url_prefers_explicit_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("DB_PATH", "ignored.db")
    settings = Settings()
    assert build_database_url(settings) == "postgresql+asyncpg://u:p@h/db"


def test_build_database_url_builds_sqlite_path_from_db_path(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", "data/custom.db")
    settings = Settings()
    url = build_database_url(settings, base_dir=tmp_path)
    expected = (tmp_path / "data" / "custom.db").as_posix()
    assert url == f"sqlite+aiosqlite:///{expected}"


def test_build_database_url_respects_absolute_db_path(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    abs_path = tmp_path / "abs.db"
    monkeypatch.setenv("DB_PATH", str(abs_path))
    settings = Settings()
    url = build_database_url(settings, base_dir=tmp_path / "unused")
    assert url.endswith(abs_path.as_posix())


# ---------------------------------------------------------------------------
# Engine + CRUD round-trip (in-memory SQLite, async)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncEngine:
    eng = create_engine(_temp_sqlite_url(tmp_path))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await dispose_engine(eng)


@pytest.mark.asyncio
async def test_insert_and_read_document(engine: AsyncEngine):
    factory = create_session_factory(engine)
    doc = DocumentRow(
        profile_slug="jane-doe",
        tax_year=2025,
        source_type=DocumentSource.UPLOAD.value,
        slip_type="T4",
        status=DocumentStatus.PROCESSING.value,
        original_filename="t4.pdf",
        raw_fields={"box14": "50000.00"},
        warnings=["low_confidence_box16"],
    )
    async with session_scope(factory) as session:
        session.add(doc)
        await session.flush()
        inserted_id = doc.id

    async with session_scope(factory) as session:
        fetched = await session.get(DocumentRow, inserted_id)
        assert fetched is not None
        assert fetched.profile_slug == "jane-doe"
        assert fetched.tax_year == 2025
        assert fetched.slip_type == "T4"
        assert fetched.status == DocumentStatus.PROCESSING.value
        assert fetched.raw_fields == {"box14": "50000.00"}
        assert fetched.warnings == ["low_confidence_box16"]
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_id_is_populated_without_explicit_value(engine: AsyncEngine):
    factory = create_session_factory(engine)
    a = DocumentRow(
        profile_slug="a",
        tax_year=2025,
        source_type=DocumentSource.MANUAL.value,
        slip_type="T5",
        status=DocumentStatus.COMPLETE.value,
        original_filename="a.pdf",
    )
    b = DocumentRow(
        profile_slug="b",
        tax_year=2025,
        source_type=DocumentSource.MANUAL.value,
        slip_type="T5",
        status=DocumentStatus.COMPLETE.value,
        original_filename="b.pdf",
    )
    async with session_scope(factory) as session:
        session.add_all([a, b])
        await session.flush()
    assert a.id and b.id
    assert a.id != b.id
    assert len(a.id) == 36  # UUID-4 string length


@pytest.mark.asyncio
async def test_status_transition_updates_row(engine: AsyncEngine):
    factory = create_session_factory(engine)
    doc = DocumentRow(
        profile_slug="p",
        tax_year=2025,
        source_type=DocumentSource.UPLOAD.value,
        slip_type="T4",
        status=DocumentStatus.PROCESSING.value,
        original_filename="slip.pdf",
    )
    async with session_scope(factory) as session:
        session.add(doc)
        await session.flush()
        doc_id = doc.id

    async with session_scope(factory) as session:
        row = await session.get(DocumentRow, doc_id)
        assert row is not None
        row.status = DocumentStatus.COMPLETE.value
        row.raw_fields = {"box14": "42000.00"}

    async with session_scope(factory) as session:
        row = await session.get(DocumentRow, doc_id)
        assert row is not None
        assert row.status == DocumentStatus.COMPLETE.value
        assert row.raw_fields == {"box14": "42000.00"}


@pytest.mark.asyncio
async def test_composite_query_by_profile_year_status(engine: AsyncEngine):
    factory = create_session_factory(engine)
    rows = [
        DocumentRow(
            profile_slug="jane",
            tax_year=2025,
            source_type=DocumentSource.UPLOAD.value,
            slip_type="T4",
            status=DocumentStatus.COMPLETE.value,
            original_filename="t4a.pdf",
        ),
        DocumentRow(
            profile_slug="jane",
            tax_year=2025,
            source_type=DocumentSource.UPLOAD.value,
            slip_type="T5",
            status=DocumentStatus.APPLIED.value,
            original_filename="t5a.pdf",
        ),
        DocumentRow(
            profile_slug="jane",
            tax_year=2024,
            source_type=DocumentSource.UPLOAD.value,
            slip_type="T4",
            status=DocumentStatus.COMPLETE.value,
            original_filename="t4b.pdf",
        ),
        DocumentRow(
            profile_slug="john",
            tax_year=2025,
            source_type=DocumentSource.UPLOAD.value,
            slip_type="T4",
            status=DocumentStatus.COMPLETE.value,
            original_filename="t4c.pdf",
        ),
    ]
    async with session_scope(factory) as session:
        session.add_all(rows)

    async with session_scope(factory) as session:
        stmt = (
            select(DocumentRow)
            .where(DocumentRow.profile_slug == "jane")
            .where(DocumentRow.tax_year == 2025)
            .where(DocumentRow.status == DocumentStatus.COMPLETE.value)
        )
        result = await session.execute(stmt)
        matching = result.scalars().all()
        assert len(matching) == 1
        assert matching[0].slip_type == "T4"
        assert matching[0].original_filename == "t4a.pdf"


@pytest.mark.asyncio
async def test_session_scope_rolls_back_on_error(engine: AsyncEngine):
    factory = create_session_factory(engine)
    with pytest.raises(ValueError):
        async with session_scope(factory) as session:
            session.add(
                DocumentRow(
                    profile_slug="rollback",
                    tax_year=2025,
                    source_type=DocumentSource.UPLOAD.value,
                    slip_type="T4",
                    status=DocumentStatus.PROCESSING.value,
                    original_filename="x.pdf",
                )
            )
            await session.flush()
            raise ValueError("boom")

    async with session_scope(factory) as session:
        stmt = select(DocumentRow).where(DocumentRow.profile_slug == "rollback")
        result = await session.execute(stmt)
        assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_document_indexes_exist(engine: AsyncEngine):
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='documents' "
                "ORDER BY name"
            )
        )
        names = {row[0] for row in result}
    expected = {
        "ix_documents_profile_slug",
        "ix_documents_tax_year",
        "ix_documents_source_type",
        "ix_documents_status",
        "ix_documents_profile_year_status",
    }
    assert expected.issubset(names), f"missing indexes: {expected - names}"


# ---------------------------------------------------------------------------
# Alembic migrations — upgrade → downgrade → upgrade against a scratch file.
# Guards against schema drift between the SQLModel models and the hand-
# authored migration script. Runs in a subprocess so the process-scope
# Alembic logging/context doesn't leak into other tests.
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(args: list[str], cwd: Path, db_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env={
            **_inherit_env(),
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_file.as_posix()}",
        },
    )


def _inherit_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if v is not None}


def test_alembic_upgrade_downgrade_roundtrip(tmp_path, monkeypatch):
    db_file = tmp_path / "roundtrip.db"
    up = _run_alembic(["upgrade", "head"], REPO_ROOT, db_file)
    assert up.returncode == 0, f"upgrade failed:\n{up.stderr}"
    assert db_file.exists()

    down = _run_alembic(["downgrade", "base"], REPO_ROOT, db_file)
    assert down.returncode == 0, f"downgrade failed:\n{down.stderr}"

    up_again = _run_alembic(["upgrade", "head"], REPO_ROOT, db_file)
    assert up_again.returncode == 0, f"re-upgrade failed:\n{up_again.stderr}"
