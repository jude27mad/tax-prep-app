"""Deterministic regression coverage for bulk staged-document deletion."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.db import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
    create_session_factory,
    session_scope,
)
from app.ui.slip_ingest import SlipStagingStore


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clear_uses_one_scoped_delete(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    target_ids = [f"target-{index}" for index in range(25)]
    preserved_ids = {"already-applied", "other-profile", "other-user", "other-year"}

    def row(
        row_id: str,
        *,
        user_id: str = "user-bench",
        profile_slug: str = "bench-profile",
        tax_year: int = 2025,
        status: str = DocumentStatus.COMPLETE.value,
    ) -> DocumentRow:
        return DocumentRow(
            id=row_id,
            user_id=user_id,
            profile_slug=profile_slug,
            tax_year=tax_year,
            source_type=DocumentSource.UPLOAD.value,
            status=status,
            slip_type="t4",
            original_filename=f"{row_id}.pdf",
        )

    async with session_scope(factory) as session:
        session.add_all([row(row_id) for row_id in target_ids])
        session.add_all(
            [
                row("already-applied", status=DocumentStatus.APPLIED.value),
                row("other-profile", profile_slug="someone-else"),
                row("other-user", user_id="different-user"),
                row("other-year", tax_year=2024),
            ]
        )

    delete_statements: list[str] = []

    def record_delete(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("DELETE FROM DOCUMENTS"):
            delete_statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record_delete)
    try:
        store = SlipStagingStore(factory)
        await store.clear("bench-profile", 2025, user_id="user-bench")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_delete)

    async with session_scope(factory) as session:
        remaining_ids = set(
            (await session.execute(select(DocumentRow.id))).scalars()
        )

    assert remaining_ids == preserved_ids
    assert len(delete_statements) == 1
    assert "documents.profile_slug" in delete_statements[0]
    assert "documents.status" in delete_statements[0]
