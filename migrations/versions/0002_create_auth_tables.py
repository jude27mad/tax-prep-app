"""Create users and login_tokens tables for D1.4 magic-link auth.

Revision ID: 0002_create_auth_tables
Revises: 0001_create_documents
Create Date: 2026-04-23

Schema follows ``app.db.auth`` (UserRow, LoginTokenRow). Hand-authored
rather than autogen so we own the indexes and constraints explicitly.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_auth_tables"
down_revision: str | Sequence[str] | None = "0001_create_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "login_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_tokens_user_id", "login_tokens", ["user_id"])
    op.create_index(
        "ix_login_tokens_token_hash", "login_tokens", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_login_tokens_user_id_consumed",
        "login_tokens",
        ["user_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_tokens_user_id_consumed", table_name="login_tokens")
    op.drop_index("ix_login_tokens_token_hash", table_name="login_tokens")
    op.drop_index("ix_login_tokens_user_id", table_name="login_tokens")
    op.drop_table("login_tokens")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
