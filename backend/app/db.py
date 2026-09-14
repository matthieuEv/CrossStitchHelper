"""Accès à la base SQLite.

SQLite est un choix assumé du cahier des charges (§3) : une instance
auto-hébergée sert une poignée d'utilisateurs, et une base fichier supprime
toute installation supplémentaire. Les réglages ci-dessous sont ce qui sépare
une base SQLite jouet d'une base utilisable par plusieurs appareils qui
synchronisent leur progression en même temps.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles."""


def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    # WAL : les lectures ne bloquent plus pendant une écriture. Indispensable
    # dès que deux appareils poussent des deltas de progression en parallèle.
    cursor.execute("PRAGMA journal_mode=WAL")
    # SQLite n'applique pas les clés étrangères par défaut.
    cursor.execute("PRAGMA foreign_keys=ON")
    # NORMAL en mode WAL : durable face à un crash applicatif, sans payer un
    # fsync par transaction.
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Laisse SQLite attendre plutôt que de renvoyer immédiatement "database is
    # locked" quand deux requêtes écrivent en même temps.
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    settings.ensure_directories()
    engine = create_engine(
        settings.database_url,
        # FastAPI sert les routes synchrones depuis un pool de threads : la
        # connexion peut donc changer de thread entre deux requêtes.
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dépendance FastAPI fournissant une session par requête."""
    with get_session_factory()() as session:
        yield session


def reset_engine_cache() -> None:
    """Oublie le moteur et la fabrique de sessions (utilisé par les tests)."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
