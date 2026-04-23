"""Async engine + session factory for the persistent document vault.

Design notes:
  * We build a single :class:`AsyncEngine` per app instance and expose a
    :class:`async_sessionmaker` through :data:`FastAPI.state.db_session_factory`.
  * ``session_scope()`` is a request-scoped async context manager that yields
    a session, commits on success, rolls back on failure. FastAPI routes can
    depend on :func:`get_session` which does the same via the dependency
    injection system.
  * SQLite connections need ``check_same_thread=False`` when shared across
    asyncio tasks; aiosqlite handles this for us, but we also disable
    SQLAlchemy's connection pooling for SQLite (``NullPool``) because each
    aiosqlite connection already owns its own thread.
  * The engine is expected to be built at startup from
    :func:`app.config.get_settings` — tests can construct their own via
    :func:`create_engine` against an in-memory SQLite URL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from fastapi import Request

    from app.config import Settings


def build_database_url(settings: "Settings", *, base_dir: Path | None = None) -> str:
    """Resolve the async database URL from settings.

    ``DATABASE_URL`` (if set) wins — supports future Postgres/MySQL deploys.
    Otherwise build ``sqlite+aiosqlite:///{base_dir}/{db_path}`` so the
    default works zero-config on a fresh checkout.
    """
    if settings.database_url:
        return settings.database_url
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    db_file = Path(settings.db_path)
    if not db_file.is_absolute():
        db_file = base / db_file
    return f"sqlite+aiosqlite:///{db_file.as_posix()}"


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build an async engine. For SQLite we disable pooling (see module docs)."""
    connect_args: dict[str, object] = {}
    poolclass = None
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        poolclass = NullPool
    return create_async_engine(
        url,
        echo=echo,
        connect_args=connect_args,
        poolclass=poolclass,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``. ``expire_on_commit=False``
    so objects remain usable after ``await session.commit()``.
    """
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional scope: yields a session, commits on success, rolls back on failure."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session(request: "Request") -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session scoped to the current request.

    Relies on :data:`app.state.db_session_factory` being populated by the
    application lifespan (see :mod:`app.lifespan`).
    """
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "db_session_factory", None
    )
    if factory is None:
        raise RuntimeError(
            "DB session factory is not initialised — is the lifespan running?"
        )
    async with session_scope(factory) as session:
        yield session


async def dispose_engine(engine: AsyncEngine) -> None:
    """Close all pooled connections. Safe to call during shutdown."""
    await engine.dispose()
