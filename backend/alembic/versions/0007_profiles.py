"""Lot 10 (issue #77): profiles, sessions, pattern and import ownership

Revision ID: 0007_profiles
Revises: 0006_pattern_labels
Create Date: 2026-10-14

Existing patterns and import jobs keep a NULL ``owner_id``: they are handed
to the first admin when the instance is set up
(`app/accounts.py::create_first_admin`), never to an arbitrary account picked
by this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_profiles"
down_revision: str | None = "0006_pattern_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # Alembic's own connection runs without `PRAGMA foreign_keys=ON` (see
    # `alembic/env.py`): recreating `patterns` in batch mode therefore never
    # cascades to its palette, grid or progress.
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.create_foreign_key(
            "fk_patterns_owner_id_users", "users", ["owner_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_patterns_owner_id", ["owner_id"])

    with op.batch_alter_table("import_jobs") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(32), nullable=True))
        batch_op.create_foreign_key(
            "fk_import_jobs_owner_id_users", "users", ["owner_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_import_jobs_owner_id", ["owner_id"])


def downgrade() -> None:
    with op.batch_alter_table("import_jobs") as batch_op:
        batch_op.drop_index("ix_import_jobs_owner_id")
        batch_op.drop_constraint("fk_import_jobs_owner_id_users", type_="foreignkey")
        batch_op.drop_column("owner_id")
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.drop_index("ix_patterns_owner_id")
        batch_op.drop_constraint("fk_patterns_owner_id_users", type_="foreignkey")
    op.execute("UPDATE patterns SET owner_id = NULL")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
