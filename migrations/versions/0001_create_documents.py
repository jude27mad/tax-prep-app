"""Create documents table for the persistent document vault.

Revision ID: 0001_create_documents
Revises:
Create Date: 2026-04-23

Schema follows ``app.db.models.DocumentRow``. See :mod:`app.db.models` for
field-level design notes. This migration is hand-authored (not autogen)
so the schema stays reviewable as the vault evolves.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_documents"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_slug", sa.String(length=128), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("slip_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_filename", sa.String(length=512), nullable=True),
        sa.Column("stored_path", sa.String(length=1024), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_text", sa.String(), nullable=True),
        sa.Column("ocr_text", sa.String(), nullable=True),
        sa.Column("raw_fields", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_documents_profile_slug",
        "documents",
        ["profile_slug"],
    )
    op.create_index(
        "ix_documents_tax_year",
        "documents",
        ["tax_year"],
    )
    op.create_index(
        "ix_documents_source_type",
        "documents",
        ["source_type"],
    )
    op.create_index(
        "ix_documents_status",
        "documents",
        ["status"],
    )
    op.create_index(
        "ix_documents_profile_year_status",
        "documents",
        ["profile_slug", "tax_year", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_profile_year_status", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_source_type", table_name="documents")
    op.drop_index("ix_documents_tax_year", table_name="documents")
    op.drop_index("ix_documents_profile_slug", table_name="documents")
    op.drop_table("documents")
