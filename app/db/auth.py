"""SQLModel table definitions for D1.4 magic-link auth.

Two tables:

* ``users`` — one row per verified email. ``email`` is stored lowercased and
  uniquely indexed. ``last_login_at`` is refreshed on successful verification.
* ``login_tokens`` — one row per outstanding magic link. We store the
  sha-256 hash of the raw token (never the raw value), keyed by the hash so
  verify is O(1). ``consumed_at`` is stamped on first use, so a reused link
  fails immediately. ``expires_at`` is checked against UTC at verify time.

Design notes:

* The raw token only ever lives in the email we send; the DB row holds the
  hash. A DB leak therefore does not hand out working login links.
* Tokens bind to a user by FK (string UUID). No ON DELETE CASCADE — we never
  expect to delete users in Phase 1 and the orphan risk is low, but we can
  add one when retention policy lands.
* ``users.email`` is unique and case-insensitive at the application layer
  (we lowercase before writing/querying). Sqlite doesn't support a partial
  functional index cleanly, so we don't try to enforce it at the DB level.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, func
from sqlmodel import Field

from app.db.models import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRow(Base, table=True):
    """A verified user. One row per email address."""

    __tablename__ = "users"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        max_length=36,
    )
    email: str = Field(
        index=True,
        unique=True,
        max_length=320,  # RFC 5321 max
        description="Lowercased email address. Unique per user.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class LoginTokenRow(Base, table=True):
    """One outstanding magic-link token.

    ``token_hash`` is the sha-256 hex digest of the raw token that went out
    over email. Callers look up by hash (unique index) rather than scanning.
    """

    __tablename__ = "login_tokens"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        max_length=36,
    )
    user_id: str = Field(
        index=True,
        max_length=36,
        description="FK to users.id (soft — no DB-level ON DELETE).",
    )
    token_hash: str = Field(
        unique=True,
        index=True,
        max_length=64,  # sha-256 hex = 64 chars
        description="sha-256 hex digest of the raw token emailed to the user.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    __table_args__ = (
        Index("ix_login_tokens_user_id_consumed", "user_id", "consumed_at"),
    )
