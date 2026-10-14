"""Lot 11b (issue #78): sharing between two paired instances

Revision ID: 0009_federation
Revises: 0008_shared_library
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_federation"
down_revision: str | None = "0008_shared_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "peers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("instance_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("outbound_token", sa.String(100), nullable=True),
        sa.Column("inbound_token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("trust_admins", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "peer_invitations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("trust_admins", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "shared_tombstones",
        sa.Column("pattern_id", sa.String(32), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shared_tombstones_seq", "shared_tombstones", ["seq"])

    # Same caveat as 0007/0008: no `PRAGMA foreign_keys` on this connection,
    # recreating the tables never cascades.
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.add_column(sa.Column("source_peer_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("remote_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("contributed_by_name", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("shared_seq", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_patterns_source_peer_id_peers",
            "peers",
            ["source_peer_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_patterns_source_peer_id", ["source_peer_id"])
        batch_op.create_index("ix_patterns_shared_seq", ["shared_seq"])

    # Shared patterns that already exist (Lot 11a) get their place in the
    # change sequence, or a paired instance would never be told about them.
    op.execute(
        "UPDATE patterns SET shared_seq = (SELECT COUNT(*) FROM patterns AS earlier "
        "WHERE earlier.library = 'shared' AND earlier.rowid <= patterns.rowid) "
        "WHERE library = 'shared'"
    )
    op.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) "
        "SELECT 'shared_seq', CAST(COALESCE(MAX(shared_seq), 0) AS TEXT), CURRENT_TIMESTAMP "
        "FROM patterns"
    )

    with op.batch_alter_table("shared_requests") as batch_op:
        batch_op.add_column(sa.Column("requested_by_name", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("requester_peer_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("requester_ref", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("source_peer_id", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("remote_id", sa.String(32), nullable=True))
        batch_op.create_foreign_key(
            "fk_shared_requests_requester_peer_id_peers",
            "peers",
            ["requester_peer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_shared_requests_source_peer_id_peers",
            "peers",
            ["source_peer_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_shared_requests_source_peer_id", ["source_peer_id"])


def downgrade() -> None:
    op.execute("DELETE FROM app_meta WHERE key = 'shared_seq'")
    # Mirrors only exist through a pairing: they go with it. Foreign keys are
    # not enforced here, so their child rows are deleted explicitly.
    mirrors = "SELECT id FROM patterns WHERE source_peer_id IS NOT NULL"
    for table in ("palette_entries", "grids", "progress", "progress_events"):
        op.execute(f"DELETE FROM {table} WHERE pattern_id IN ({mirrors})")
    op.execute(
        f"UPDATE patterns SET origin_pattern_id = NULL WHERE origin_pattern_id IN ({mirrors})"
    )
    op.execute("DELETE FROM patterns WHERE source_peer_id IS NOT NULL")
    op.execute("DELETE FROM shared_requests WHERE source_peer_id IS NOT NULL")
    with op.batch_alter_table("shared_requests") as batch_op:
        batch_op.drop_index("ix_shared_requests_source_peer_id")
        batch_op.drop_constraint("fk_shared_requests_source_peer_id_peers", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_shared_requests_requester_peer_id_peers", type_="foreignkey"
        )
        batch_op.drop_column("remote_id")
        batch_op.drop_column("source_peer_id")
        batch_op.drop_column("requester_ref")
        batch_op.drop_column("requester_peer_id")
        batch_op.drop_column("requested_by_name")
    with op.batch_alter_table("patterns") as batch_op:
        batch_op.drop_index("ix_patterns_shared_seq")
        batch_op.drop_index("ix_patterns_source_peer_id")
        batch_op.drop_constraint("fk_patterns_source_peer_id_peers", type_="foreignkey")
        batch_op.drop_column("shared_seq")
        batch_op.drop_column("contributed_by_name")
        batch_op.drop_column("remote_id")
        batch_op.drop_column("source_peer_id")
    op.drop_index("ix_shared_tombstones_seq", table_name="shared_tombstones")
    op.drop_table("shared_tombstones")
    op.drop_table("peer_invitations")
    op.drop_table("peers")
