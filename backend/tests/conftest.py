from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import reset_engine_cache


def _reset_caches() -> None:
    get_settings.cache_clear()
    reset_engine_cache()


@pytest.fixture
def frontend_dist(tmp_path: Path) -> Path:
    """Fake build directory mimicking Vite's output."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>CrossStitchHelper</title>")
    (dist / "assets" / "index-abc123.js").write_text("console.log('app')")
    (dist / "manifest.webmanifest").write_text('{"name":"CrossStitchHelper"}')
    (dist / "sw.js").write_text("// service worker")
    return dist


@pytest.fixture
def make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[object]:
    """Build a test client, with or without a built frontend."""

    def factory(dist: Path | None = None) -> TestClient:
        monkeypatch.setenv("CSH_DATA_DIR", str(tmp_path / "data"))
        # Automatic backup loop (Lot 8, `app/auto_backup.py`): disabled by
        # default in tests, same principle as migrations — no background task
        # writing to disk in every test that instantiates a client.
        # `test_auto_backup.py` re-enables it explicitly for what it needs
        # to check.
        monkeypatch.setenv("CSH_RUN_AUTO_BACKUP_LOOP", "false")
        if dist is not None:
            monkeypatch.setenv("CSH_FRONTEND_DIST", str(dist))
        else:
            monkeypatch.delenv("CSH_FRONTEND_DIST", raising=False)
        _reset_caches()

        from app.main import create_app

        application: FastAPI = create_app()
        return TestClient(application)

    _reset_caches()
    yield factory
    _reset_caches()


@pytest.fixture
def client(make_client: object) -> Iterator[TestClient]:
    with make_client(None) as test_client:  # type: ignore[operator]
        yield test_client
