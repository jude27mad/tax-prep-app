from __future__ import annotations

import time
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import (
    Base,
    DocumentRow,
    DocumentStatus,
    create_session_factory,
    session_scope,
)
from app.ui.slip_ingest import SlipStagingStore


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


@pytest.mark.asyncio
async def test_benchmark_apply_all(store: SlipStagingStore, engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    num_rows = 500

    # Seed 500 COMPLETE rows
    async with session_scope(factory) as session:
        for i in range(num_rows):
            session.add(
                DocumentRow(
                    id=str(uuid.uuid4()),
                    profile_slug="jane-doe",
                    tax_year=2025,
                    source_type="upload",
                    slip_type="t4",
                    status=DocumentStatus.COMPLETE.value,
                    original_filename=f"t4_{i}.txt",
                    raw_fields={"employment_income": "50000.00"},
                    warnings=[],
                )
            )

    start_time = time.perf_counter()
    applied = await store.apply("jane-doe", 2025)
    elapsed = time.perf_counter() - start_time

    assert len(applied) == num_rows
    print(f"\n[BENCHMARK] apply_all with {num_rows} rows: {elapsed * 1000:.2f} ms")


@pytest.mark.asyncio
async def test_benchmark_apply_subset(store: SlipStagingStore, engine: AsyncEngine) -> None:
    factory = create_session_factory(engine)
    num_rows = 1000
    subset_size = 10
    row_ids: list[str] = []

    # Seed 1000 COMPLETE rows
    async with session_scope(factory) as session:
        for i in range(num_rows):
            row_id = str(uuid.uuid4())
            if i < subset_size:
                row_ids.append(row_id)
            session.add(
                DocumentRow(
                    id=row_id,
                    profile_slug="jane-doe",
                    tax_year=2025,
                    source_type="upload",
                    slip_type="t4",
                    status=DocumentStatus.COMPLETE.value,
                    original_filename=f"t4_{i}.txt",
                    raw_fields={"employment_income": "50000.00"},
                    warnings=[],
                )
            )

    start_time = time.perf_counter()
    applied = await store.apply("jane-doe", 2025, row_ids)
    elapsed = time.perf_counter() - start_time

    assert len(applied) == subset_size
    print(f"\n[BENCHMARK] apply_subset ({subset_size}/{num_rows} rows): {elapsed * 1000:.2f} ms")
