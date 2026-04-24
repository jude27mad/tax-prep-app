"""Add documents.user_id for D1.6 user-scoped data.

Revision ID: 0003_documents_user_id
Revises: 0002_create_auth_tables
Create Date: 2026-04-24

Adds a nullable ``user_id`` FK column plus a supporting index on
``(user_id, profile_slug, tax_year)``. The column is nullable so that
pre-D1.6 rows (if any made it into a dev DB before this migration) don't
trip the upgrade. All newly-ingested documents stamp ``user_id`` from
the authenticated session.

We don't declare a hard FK to ``users(id)`` for the same reason D1.4
didn't FK ``login_tokens.user_id``: Phase 1 has no retention policy, and
a soft FK keeps sqlite batch ops simple. When we wire ON DELETE cascade
we'll add both in one migration.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_documents_user_id"
down_revision: str | Sequence[str] | None = "0002_create_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_documents_user_id", "documents", ["user_id"]
    )
    op.create_index(
        "ix_documents_user_profile_year",
        "documents",
        ["user_id", "profile_slug", "tax_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_profile_year", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("user_id")
