"""Benchmark document deletion in SlipStagingStore.clear.

Measures the performance difference between N+1 row-by-row deletion and
single SQL DELETE statement bulk deletion.
"""

from __future__ import annotations

import time
import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import select

from app.db import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
    create_session_factory,
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


@pytest.mark.asyncio
async def test_benchmark_bulk_delete_speedup(engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    num_rows = 300

    # Populate rows for old method benchmark
    async with factory() as session:
        for i in range(num_rows):
            session.add(
                DocumentRow(
                    id=f"old_doc_{i}",
                    user_id="user_bench",
                    profile_slug="bench_profile",
                    tax_year=2025,
                    source_type=DocumentSource.UPLOAD.value,
                    status=DocumentStatus.COMPLETE.value,
                    slip_type="t4",
                    original_filename=f"file_{i}.pdf",
                )
            )
        await session.commit()

    # Time old method (N+1 select + session.delete loop)
    t0 = time.perf_counter()
    async with factory() as session:
        stmt = (
            select(DocumentRow)
            .where(DocumentRow.user_id == "user_bench")
            .where(DocumentRow.profile_slug == "bench_profile")
            .where(DocumentRow.tax_year == 2025)
            .where(DocumentRow.status == DocumentStatus.COMPLETE.value)
        )
        result = await session.execute(stmt)
        for row in result.scalars().all():
            await session.delete(row)
        await session.commit()
    t1 = time.perf_counter()
    old_duration = t1 - t0

    # Populate rows for new method benchmark
    async with factory() as session:
        for i in range(num_rows):
            session.add(
                DocumentRow(
                    id=f"new_doc_{i}",
                    user_id="user_bench",
                    profile_slug="bench_profile",
                    tax_year=2025,
                    source_type=DocumentSource.UPLOAD.value,
                    status=DocumentStatus.COMPLETE.value,
                    slip_type="t4",
                    original_filename=f"file_{i}.pdf",
                )
            )
        await session.commit()

    # Time bulk delete query
    t0 = time.perf_counter()
    async with factory() as session:
        stmt = (
            delete(DocumentRow)
            .where(DocumentRow.user_id == "user_bench")
            .where(DocumentRow.profile_slug == "bench_profile")
            .where(DocumentRow.tax_year == 2025)
            .where(DocumentRow.status == DocumentStatus.COMPLETE.value)
        )
        await session.execute(stmt)
        await session.commit()
    t1 = time.perf_counter()
    new_duration = t1 - t0

    speedup = old_duration / new_duration if new_duration > 0 else 0
    print(f"\n[Benchmark] Old approach ({num_rows} rows): {old_duration * 1000:.2f} ms")
    print(f"[Benchmark] Bulk delete ({num_rows} rows): {new_duration * 1000:.2f} ms")
    print(f"[Benchmark] Speedup: {speedup:.2f}x")

    assert new_duration < old_duration, "Bulk delete should be faster than N+1 deletion"
