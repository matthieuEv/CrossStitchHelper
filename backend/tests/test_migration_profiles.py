"""Migration 0007 on an instance that already has data (Lot 10).

Recreating `patterns` in batch mode (to add its foreign key to `users`) must
not cascade to its palette, grid or progress — `CLAUDE.md`: a change must
never be able to lose tracking work already done.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from app.config import get_settings
from app.db import reset_engine_cache
from app.migrations import build_alembic_config


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("CSH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine_cache()
    yield get_settings().database_path
    get_settings.cache_clear()
    reset_engine_cache()


def _insert_pattern_at_0006(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                "INSERT INTO patterns (id, owner_id, name, width, height, created_at, "
                "updated_at, labels_json) VALUES ('p1', NULL, 'Existing', 2, 1, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '[\"Mini\"]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO palette_entries (id, pattern_id, index_in_grid, brand, code, "
                "name, rgb_hex, symbol_key, count_full, count_half, count_quarter, "
                "count_french, count_beads) VALUES ('e1', 'p1', 1, 'DMC', '310', 'Black', "
                "'#000000', 'X', 2, 0, 0, 0, 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO grids (pattern_id, layer_full, backstitch_json, "
                "french_knots_json, encoding, version) VALUES ('p1', X'01000100', '[]', "
                "'[]', 'uint16le', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO progress (pattern_id, bitmap, version, stitched_count, "
                "updated_at) VALUES ('p1', X'01', 3, 1, '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO progress_events (pattern_id, ts, ops_json, version_after) "
                "VALUES ('p1', '2026-01-01 00:00:00', '[]', 3)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO import_jobs (id, status, kind, progress_pct, result_json, "
                "created_at) VALUES ('j1', 'ready', 'png', 100, '{}', '2026-01-01 00:00:00')"
            )
        )
    engine.dispose()


def test_upgrade_keeps_existing_patterns_progress_and_jobs(database: Path) -> None:
    config = build_alembic_config()
    url = get_settings().database_url
    command.upgrade(config, "0006_pattern_labels")
    _insert_pattern_at_0006(url)

    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT name, owner_id FROM patterns")).all()
        assert [tuple(row) for row in rows] == [("Existing", None)]
        # 0008 (Lot 11): an existing pattern is a personal one, never shared.
        shared_state = connection.execute(
            text("SELECT library, revision, origin_pattern_id FROM patterns")
        ).one()
        assert tuple(shared_state) == ("personal", 1, None)
        assert connection.execute(text("SELECT count(*) FROM palette_entries")).scalar() == 1
        assert connection.execute(text("SELECT layer_full FROM grids")).scalar() == bytes(
            [1, 0, 1, 0]
        )
        assert connection.execute(text("SELECT bitmap, version FROM progress")).one() == (
            b"\x01",
            3,
        )
        assert connection.execute(text("SELECT count(*) FROM progress_events")).scalar() == 1
        assert connection.execute(text("SELECT owner_id FROM import_jobs")).scalar() is None
        foreign_keys = connection.execute(text("PRAGMA foreign_key_list(patterns)")).all()
        assert any(row[2] == "users" and row[3] == "owner_id" for row in foreign_keys)
    engine.dispose()


def test_downgrade_to_0006_then_upgrade_again(database: Path) -> None:
    config = build_alembic_config()
    url = get_settings().database_url
    command.upgrade(config, "0006_pattern_labels")
    _insert_pattern_at_0006(url)
    command.upgrade(config, "head")

    command.downgrade(config, "0006_pattern_labels")
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM progress")).scalar() == 1
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 0
    engine.dispose()


def test_existing_shared_patterns_are_published_after_0009(database: Path) -> None:
    """A pattern shared before 0009 (Lot 11a) must get a place in the change
    sequence, or a paired instance would never hear of it."""
    config = build_alembic_config()
    url = get_settings().database_url
    command.upgrade(config, "0008_shared_library")
    engine = create_engine(url)
    with engine.begin() as connection:
        for pattern_id in ("s1", "s2"):
            connection.execute(
                text(
                    "INSERT INTO patterns (id, name, width, height, created_at, updated_at, "
                    "labels_json, library, revision) VALUES (:id, 'Shared', 2, 1, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '[]', 'shared', 1)"
                ),
                {"id": pattern_id},
            )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        seqs = connection.execute(
            text("SELECT shared_seq FROM patterns ORDER BY shared_seq")
        ).scalars()
        assert list(seqs) == [1, 2]
        counter = connection.execute(
            text("SELECT value FROM app_meta WHERE key = 'shared_seq'")
        ).scalar()
        assert counter == "2"
    engine.dispose()
