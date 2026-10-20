"""Database schema, created straight from the models — no migrations.

While the project is in development, schema changes ship without migration
scripts (decision of 2026-10-20, specification §13): the models
(`app/models.py`) are the only description of the schema. At startup the
database is checked against a fingerprint of the models; when they differ —
a new column, a changed table — every table is dropped and recreated empty.
Data is lost on such an update: accepted for now, and the automatic backups
(`backups/` in the data directory, Lot 8) are files the reset never touches.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import Engine, inspect, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import get_settings
from app.db import Base, get_engine, get_session_factory

logger = logging.getLogger(__name__)

SCHEMA_FINGERPRINT_KEY = "schema_fingerprint"


def schema_fingerprint() -> str:
    """Hash of the SQL the models create, tables and indexes, in a stable
    order — any change to a model changes it."""
    # Imported for its side effect: registering every model on `Base`.
    import app.models  # noqa: F401

    dialect = sqlite.dialect()
    statements: list[str] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda table: table.name):
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        for index in sorted(table.indexes, key=lambda index: index.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip())
    return hashlib.sha256("\n".join(statements).encode()).hexdigest()


def _stored_fingerprint(engine: Engine) -> str | None:
    if "app_meta" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT value FROM app_meta WHERE key = :key"), {"key": SCHEMA_FINGERPRINT_KEY}
        ).first()
    return str(row[0]) if row is not None else None


def _drop_every_table(engine: Engine) -> None:
    # Every table SQLite holds, models or not (`alembic_version` from before
    # this decision, a table a model no longer has): the database starts again
    # from nothing. Foreign keys off, so the order does not matter — a PRAGMA
    # that SQLite ignores inside a transaction, hence AUTOCOMMIT.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for name in inspect(connection).get_table_names():
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}"')
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def ensure_schema() -> None:
    """Create the schema if the database is empty, recreate it (empty) if the
    models changed since it was created, leave it alone otherwise."""
    from app.models import AppMeta

    settings = get_settings()
    settings.ensure_directories()
    engine = get_engine()
    expected = schema_fingerprint()
    stored = _stored_fingerprint(engine)
    if stored == expected:
        return

    if inspect(engine).get_table_names():
        logger.warning(
            "The data model changed: recreating the database %s from scratch, "
            "its data is lost (automatic backups in %s are kept).",
            settings.database_path,
            settings.backups_dir,
        )
        _drop_every_table(engine)
    else:
        logger.info("Creating the database %s", settings.database_path)
    Base.metadata.create_all(engine)
    with get_session_factory()() as session:
        session.add(AppMeta(key=SCHEMA_FINGERPRINT_KEY, value=expected))
        session.commit()
