"""Lot 1 : modèle de données complet (patterns, palette_entries, grids, progress, progress_events)

Revision ID: 0002_pattern_model
Revises: 0001_initial
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_pattern_model"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patterns",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fabric_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_config_json", sa.Text(), nullable=True),
        sa.Column("recipe_id", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "palette_entries",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("pattern_id", sa.String(length=32), nullable=False),
        sa.Column("index_in_grid", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("rgb_hex", sa.String(length=7), nullable=False),
        sa.Column("symbol_key", sa.String(length=8), nullable=False),
        sa.Column("symbol_svg", sa.Text(), nullable=True),
        sa.Column("strands_full", sa.Integer(), nullable=True),
        sa.Column("strands_back", sa.Integer(), nullable=True),
        sa.Column("count_full", sa.Integer(), nullable=False),
        sa.Column("count_half", sa.Integer(), nullable=False),
        sa.Column("count_quarter", sa.Integer(), nullable=False),
        sa.Column("count_french", sa.Integer(), nullable=False),
        sa.Column("count_beads", sa.Integer(), nullable=False),
        sa.Column("backstitch_length_cm", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern_id", "index_in_grid"),
    )
    op.create_index(
        "ix_palette_entries_pattern_id", "palette_entries", ["pattern_id"], unique=False
    )

    op.create_table(
        "grids",
        sa.Column("pattern_id", sa.String(length=32), nullable=False),
        sa.Column("layer_full", sa.LargeBinary(), nullable=False),
        sa.Column("layer_half", sa.LargeBinary(), nullable=True),
        sa.Column("layer_quarter", sa.LargeBinary(), nullable=True),
        sa.Column("backstitch_json", sa.Text(), nullable=False),
        sa.Column("french_knots_json", sa.Text(), nullable=False),
        sa.Column("encoding", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pattern_id"),
    )

    op.create_table(
        "progress",
        sa.Column("pattern_id", sa.String(length=32), nullable=False),
        sa.Column("bitmap", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stitched_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pattern_id"),
    )

    op.create_table(
        "progress_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.String(length=32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ops_json", sa.Text(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_progress_events_pattern_id", "progress_events", ["pattern_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_progress_events_pattern_id", table_name="progress_events")
    op.drop_table("progress_events")
    op.drop_table("progress")
    op.drop_table("grids")
    op.drop_index("ix_palette_entries_pattern_id", table_name="palette_entries")
    op.drop_table("palette_entries")
    op.drop_table("patterns")
