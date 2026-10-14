"""Lot 11a (issue #78): shared library on one instance

Revision ID: 0008_shared_library
Revises: 0007_profiles
Create Date: 2026-10-14

Every existing pattern is a personal one (``library = 'personal'``, the
server default): nothing becomes shared without someone sharing it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_shared_library"
down_revision: str | None = "0007_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Same caveat as 0007: Alembic's own connection runs without
    # `PRAGMA foreign_keys=ON`, so recreating `patterns` never cascades.
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.add_column(
            sa.Column("library", sa.String(16), nullable=False, server_default="personal")
        )
        batch_op.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("contributed_by", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("origin_pattern_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("origin_revision", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_patterns_contributed_by_users",
            "users",
            ["contributed_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_patterns_origin_pattern_id_patterns",
            "patterns",
            ["origin_pattern_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_patterns_library", ["library"])
        batch_op.create_index("ix_patterns_origin_pattern_id", ["origin_pattern_id"])

    op.create_table(
        "shared_requests",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "shared_pattern_id",
            sa.String(32),
            sa.ForeignKey("patterns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pattern_name", sa.String(200), nullable=False),
        sa.Column(
            "requested_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "proposal_pattern_id",
            sa.String(32),
            sa.ForeignKey("patterns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_shared_requests_shared_pattern_id", "shared_requests", ["shared_pattern_id"]
    )
    op.create_index("ix_shared_requests_requested_by", "shared_requests", ["requested_by"])


def downgrade() -> None:
    op.drop_index("ix_shared_requests_requested_by", table_name="shared_requests")
    op.drop_index("ix_shared_requests_shared_pattern_id", table_name="shared_requests")
    op.drop_table("shared_requests")
    # Shared and proposal patterns have no meaning without this revision.
    # Foreign keys are not enforced on this connection: their rows in the
    # child tables are deleted explicitly, never left orphaned.
    others = "SELECT id FROM patterns WHERE library != 'personal'"
    for table in ("palette_entries", "grids", "progress", "progress_events"):
        op.execute(f"DELETE FROM {table} WHERE pattern_id IN ({others})")
    op.execute("UPDATE patterns SET origin_pattern_id = NULL")
    op.execute("DELETE FROM patterns WHERE library != 'personal'")
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.drop_index("ix_patterns_origin_pattern_id")
        batch_op.drop_index("ix_patterns_library")
        batch_op.drop_constraint("fk_patterns_origin_pattern_id_patterns", type_="foreignkey")
        batch_op.drop_constraint("fk_patterns_contributed_by_users", type_="foreignkey")
        batch_op.drop_column("origin_revision")
        batch_op.drop_column("origin_pattern_id")
        batch_op.drop_column("contributed_by")
        batch_op.drop_column("revision")
        batch_op.drop_column("library")
