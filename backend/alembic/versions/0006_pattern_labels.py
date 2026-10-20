"""Issue #57: labels on patterns

Revision ID: 0006_pattern_labels
Revises: 0005_progress_extra_layers
Create Date: 2026-10-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_pattern_labels"
down_revision: str | None = "0005_progress_extra_layers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.add_column(
            sa.Column("labels_json", sa.Text(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.drop_column("labels_json")
