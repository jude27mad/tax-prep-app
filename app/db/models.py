"""SQLModel table definitions for the persistent document vault.

Scope for D1.3 PR A (this file): the ``documents`` table only. Slip FKs that
reference these rows land in PR C; the live migration from the in-memory
``SlipStagingStore`` to write-through persistence lands in PR B.

Design notes:
  * UUIDs (string form) are used as primary keys. They're stable across
    environments, don't require round-tripping through ``INSERT ... RETURNING``,
    and make it easy to reference a document from a slip model before the
    row is actually persisted.
  * ``source_type`` and ``status`` are stored as plain strings (we validate
    values through :class:`DocumentSource` / :class:`DocumentStatus` str
    enums rather than the SQL ENUM type, which SQLite handles awkwardly and
    which would force Alembic schema churn each time we add a value).
  * ``raw_fields`` and ``warnings`` are JSON-encoded blobs. SQLAlchemy's
    generic :class:`~sqlalchemy.types.JSON` type maps to TEXT on SQLite and
    JSONB on Postgres when we eventually swap backends.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String, func
from sqlmodel import Field, SQLModel


class DocumentSource(StrEnum):
    """Where this document originated."""

    UPLOAD = "upload"         # User uploaded a file through the UI
    CRA_IMPORT = "cra_import" # Fetched from CRA Auto-fill (D3.2)
    MANUAL = "manual"         # Entered by the user without an attachment


class DocumentStatus(StrEnum):
    """Lifecycle of an ingested document."""

    PROCESSING = "processing" # Upload received; OCR/classification in flight
    COMPLETE = "complete"     # Detection produced; awaiting user confirmation
    APPLIED = "applied"       # User applied detection onto a return
    ERROR = "error"           # Processing failed; see ``error_message``


def _new_document_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(SQLModel):
    """Marker base so downstream modules can target ``Base.metadata``."""


class DocumentRow(Base, table=True):
    """A single ingested document — slip upload, CRA pull, or manual entry.

    Rows of this table are the source of truth for document provenance:
    every slip on a return must eventually link back to one of these via a
    ``document_id`` FK (landing in PR C).
    """

    __tablename__ = "documents"

    id: str = Field(
        default_factory=_new_document_id,
        primary_key=True,
        max_length=36,
        description="Stable UUID used downstream as a slip FK.",
    )

    user_id: str | None = Field(
        default=None,
        index=True,
        max_length=36,
        description=(
            "FK to users.id (soft — no DB-level ON DELETE). Nullable for rows "
            "pre-D1.6; newly-ingested documents always stamp this from the "
            "authenticated session."
        ),
    )
    profile_slug: str = Field(
        index=True,
        max_length=128,
        description="Slug of the owning profile; matches app/wizard/profiles.py keys.",
    )
    tax_year: int = Field(
        index=True,
        description="Tax year the document pertains to (e.g. 2025).",
    )

    source_type: str = Field(
        index=True,
        max_length=32,
        description="One of DocumentSource values.",
    )
    slip_type: str = Field(
        max_length=32,
        description="T4 / T4A / T5 / T2202 / RRSP / unknown.",
    )
    status: str = Field(
        index=True,
        max_length=32,
        description="One of DocumentStatus values.",
    )

    original_filename: str = Field(max_length=512)
    stored_filename: str | None = Field(default=None, max_length=512)
    stored_path: str | None = Field(default=None, max_length=1024)
    size_bytes: int = Field(default=0)

    preview_text: str | None = Field(default=None)
    ocr_text: str | None = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )
    raw_fields: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
        description="Key/value fields extracted from the document (OCR or structured).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
        description="Non-fatal OCR/classification warnings surfaced to the UI.",
    )
    error_message: str | None = Field(default=None, max_length=2048)

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=_utcnow,
        ),
    )

    __table_args__ = (
        Index("ix_documents_profile_year_status", "profile_slug", "tax_year", "status"),
        Index("ix_documents_user_profile_year", "user_id", "profile_slug", "tax_year"),
    )
