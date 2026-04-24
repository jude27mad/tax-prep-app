"""Persistent document vault — async SQLite via SQLModel/SQLAlchemy 2.0.

Phase 1 scope (D1.3):
  * Async engine + session factory built from :class:`app.config.Settings`.
  * A single ``documents`` table (see :mod:`app.db.models`) that will carry
    every slip/import/manual document in the system.
  * Alembic migrations live in the top-level ``migrations/`` directory.

Postgres is left as a future swap (set ``DATABASE_URL`` to a ``postgresql+asyncpg://``
URL and add the driver to requirements). The rest of the app should only
depend on the abstractions re-exported here.
"""

from __future__ import annotations

from app.db.auth import (
    LoginTokenRow,
    UserRow,
)
from app.db.engine import (
    build_database_url,
    create_engine,
    create_session_factory,
    dispose_engine,
    get_session,
    session_scope,
)
from app.db.models import (
    Base,
    DocumentRow,
    DocumentSource,
    DocumentStatus,
)

__all__ = [
    "Base",
    "DocumentRow",
    "DocumentSource",
    "DocumentStatus",
    "LoginTokenRow",
    "UserRow",
    "build_database_url",
    "create_engine",
    "create_session_factory",
    "dispose_engine",
    "get_session",
    "session_scope",
]
