"""Lot 6: recipes table

Revision ID: 0004_recipes
Revises: 0003_import_jobs
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_recipes"
down_revision: str | None = "0003_import_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("grid_type", sa.String(length=8), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recipes_fingerprint", "recipes", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_recipes_fingerprint", table_name="recipes")
    op.drop_table("recipes")
