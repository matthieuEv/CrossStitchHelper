"""Tests de la sauvegarde automatique quotidienne (Lot 8, cahier des charges §7.5).

`app/auto_backup.py` est décomposé exprès en fonctions synchrones
directement testables (`is_auto_backup_enabled`, `write_auto_backup`) plutôt
que de tout vérifier à travers la boucle asyncio réelle, qui attendrait 24h
entre deux écritures — seul le dernier test ci-dessous exerce vraiment la
boucle, avec un intervalle raccourci, pour couvrir la création de tâche et
l'annulation propre (`app/main.py`, arrêt de l'application)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auto_backup
from app.db import get_session_factory
from app.seed import seed_demo_pattern


@pytest.fixture
def seeded_client(client: TestClient) -> Iterator[TestClient]:
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    yield client


def test_is_auto_backup_enabled_defaults_true_and_is_toggleable(client: TestClient) -> None:
    with get_session_factory()() as session:
        assert auto_backup.is_auto_backup_enabled(session) is True
        auto_backup.set_auto_backup_enabled(session, False)
        assert auto_backup.is_auto_backup_enabled(session) is False
        auto_backup.set_auto_backup_enabled(session, True)
        assert auto_backup.is_auto_backup_enabled(session) is True


def test_write_auto_backup_creates_a_file_matching_the_current_data(
    seeded_client: TestClient, tmp_path: Path
) -> None:
    backups_dir = tmp_path / "backups"
    with get_session_factory()() as session:
        path = auto_backup.write_auto_backup(session, backups_dir)

    assert path.parent == backups_dir
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["format"] == "csh-backup"
    [pattern] = document["patterns"]

    exported = seeded_client.get("/api/backup").json()
    assert pattern["id"] == exported["patterns"][0]["id"]
    assert pattern["grid"]["layer_full"] == exported["patterns"][0]["grid"]["layer_full"]


def test_write_auto_backup_prunes_beyond_retention(client: TestClient, tmp_path: Path) -> None:
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    # Fichiers déjà présents, plus vieux que ce que la rétention doit garder
    # (tri lexicographique = tri chronologique, même convention que le nom
    # réel écrit par `write_auto_backup`).
    existing_count = auto_backup.RETENTION + 3
    for day in range(1, existing_count + 1):
        (backups_dir / f"backup-2020-01-{day:02d}T00-00-00.json").write_text("{}")

    with get_session_factory()() as session:
        auto_backup.write_auto_backup(session, backups_dir)

    remaining = sorted(backups_dir.glob("backup-*.json"))
    assert len(remaining) == auto_backup.RETENTION
    # Les plus anciens (2020-01-01, -02, -03) ont été purgés en premier.
    assert remaining[0].name > "backup-2020-01-03T00-00-00.json"


def test_write_auto_backup_is_a_no_op_regarding_existing_files_when_disabled_upstream(
    client: TestClient, tmp_path: Path
) -> None:
    """`write_auto_backup` elle-même est inconditionnelle (voir sa
    docstring) : c'est `run_auto_backup_loop` qui vérifie le réglage avant de
    l'appeler — ce test le confirme directement sur la boucle."""
    backups_dir = tmp_path / "backups"
    with get_session_factory()() as session:
        auto_backup.set_auto_backup_enabled(session, False)

    async def scenario() -> None:
        task = asyncio.create_task(
            auto_backup.run_auto_backup_loop(get_session_factory(), backups_dir)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    asyncio.run(scenario())
    assert not backups_dir.exists() or list(backups_dir.glob("backup-*.json")) == []


def test_run_auto_backup_loop_writes_repeatedly_and_cancels_cleanly(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auto_backup, "INTERVAL_SECONDS", 0.05)
    backups_dir = tmp_path / "backups"

    async def scenario() -> None:
        task = asyncio.create_task(
            auto_backup.run_auto_backup_loop(get_session_factory(), backups_dir)
        )
        await asyncio.sleep(0.3)
        task.cancel()
        await task  # ne doit lever ni CancelledError ni rien d'autre

    asyncio.run(scenario())

    written = list(backups_dir.glob("backup-*.json"))
    assert len(written) >= 2  # au moins l'écriture immédiate + une itération
