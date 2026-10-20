"""No migrations while in development (decision of 2026-10-20): the schema
is created from the models, and recreated empty when they change."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import get_engine, reset_engine_cache
from app.schema import SCHEMA_FINGERPRINT_KEY, ensure_schema, schema_fingerprint


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("CSH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine_cache()
    yield tmp_path
    get_settings.cache_clear()
    reset_engine_cache()


def _stored_fingerprint() -> str | None:
    with get_engine().connect() as connection:
        row = connection.execute(
            text("SELECT value FROM app_meta WHERE key = :key"), {"key": SCHEMA_FINGERPRINT_KEY}
        ).first()
    return None if row is None else str(row[0])


def _count(table: str) -> int:
    with get_engine().connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _add_instance_name() -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO app_meta (key, value, updated_at) "
                "VALUES ('instance_name', 'Site A', CURRENT_TIMESTAMP)"
            )
        )


def test_an_empty_database_gets_the_schema_and_its_fingerprint() -> None:
    ensure_schema()
    tables = set(inspect(get_engine()).get_table_names())
    assert {"patterns", "grids", "progress", "app_meta"} <= tables
    assert _stored_fingerprint() == schema_fingerprint()


def test_an_unchanged_schema_keeps_its_data() -> None:
    ensure_schema()
    _add_instance_name()
    ensure_schema()
    assert _count("app_meta") == 2


def test_changed_models_recreate_the_database_empty() -> None:
    ensure_schema()
    _add_instance_name()
    with get_engine().begin() as connection:
        # A database created from older models, still carrying the table
        # Alembic kept before this decision.
        connection.execute(
            text("UPDATE app_meta SET value = 'older' WHERE key = :key"),
            {"key": SCHEMA_FINGERPRINT_KEY},
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))

    ensure_schema()

    assert "alembic_version" not in inspect(get_engine()).get_table_names()
    assert _stored_fingerprint() == schema_fingerprint()
    assert _count("app_meta") == 1  # the instance name went with the rest


def test_a_database_from_the_migration_era_is_recreated() -> None:
    """A database made by the former Alembic chain has no fingerprint at all."""
    with get_engine().begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("CREATE TABLE patterns (id VARCHAR(32) PRIMARY KEY)"))

    ensure_schema()

    assert "alembic_version" not in inspect(get_engine()).get_table_names()
    assert _stored_fingerprint() == schema_fingerprint()
