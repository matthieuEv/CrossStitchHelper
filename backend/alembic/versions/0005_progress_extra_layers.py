"""Lot 8 : bitmaps de progression pour les points fractionnés et spéciaux

Revision ID: 0005_progress_extra_layers
Revises: 0004_recipes
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_progress_extra_layers"
down_revision: str | None = "0004_recipes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("progress") as batch_op:
        batch_op.add_column(sa.Column("bitmap_half", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("bitmap_quarter", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("bitmap_backstitch", sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column("bitmap_knots", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("progress") as batch_op:
        batch_op.drop_column("bitmap_knots")
        batch_op.drop_column("bitmap_backstitch")
        batch_op.drop_column("bitmap_quarter")
        batch_op.drop_column("bitmap_half")
