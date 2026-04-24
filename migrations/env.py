"""Alembic environment for the persistent document vault.

Resolves the database URL from :class:`app.config.Settings` so production
and tests use the same resolution logic as the running app. Supports an
``alembic -x url=<override>`` escape hatch for one-off targets.
"""

from __future__ import annotations

import asyncio
import logging.config
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db import Base, build_database_url
from app.db import auth as _auth  # noqa: F401  # register users/login_tokens on Base.metadata
from app.db import models as _models  # noqa: F401  # register documents on Base.metadata

config = context.config

if config.config_file_name is not None:
    logging.config.fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """URL precedence: ``-x url=<value>`` > settings > alembic.ini default."""
    xargs = context.get_x_argument(as_dictionary=True)
    if "url" in xargs and xargs["url"]:
        return xargs["url"]
    settings = get_settings()
    base_dir = Path(__file__).resolve().parent.parent
    return build_database_url(settings, base_dir=base_dir)


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _resolve_url()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
