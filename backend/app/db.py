"""SQLite database access.

SQLite is a deliberate choice of the specification (§3): a self-hosted
instance serves a handful of users, and a file database removes any extra
installation. The settings below are what separate a toy SQLite database
from one usable by several devices synchronising their progress at the same
time.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all models."""


def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    # WAL: reads no longer block during a write. Essential as soon as two
    # devices push progress deltas in parallel.
    cursor.execute("PRAGMA journal_mode=WAL")
    # SQLite does not enforce foreign keys by default.
    cursor.execute("PRAGMA foreign_keys=ON")
    # NORMAL in WAL mode: durable against an application crash, without
    # paying one fsync per transaction.
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Let SQLite wait rather than immediately return "database is locked"
    # when two requests write at the same time.
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    settings.ensure_directories()
    engine = create_engine(
        settings.database_url,
        # FastAPI serves synchronous routes from a thread pool: the
        # connection can therefore change threads between two requests.
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency providing one session per request."""
    with get_session_factory()() as session:
        yield session


def reset_engine_cache() -> None:
    """Forget the engine and the session factory (used by tests)."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
