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


ADMIN_PASSWORD = "admin-password"
USER_PASSWORD = "user-password"


def as_app_client(test_client: TestClient) -> TestClient:
    """What the real frontend sends with every request (`app/auth.py::
    require_client_header`, Lot 10)."""
    test_client.headers["X-CSH-Client"] = "web"
    return test_client


@pytest.fixture
def anonymous_client(make_client: object) -> Iterator[TestClient]:
    """A client with no profile logged in, on an instance not set up yet."""
    with make_client(None) as test_client:  # type: ignore[operator]
        yield as_app_client(test_client)


@pytest.fixture
def client(anonymous_client: TestClient) -> TestClient:
    """A client logged in as the instance's first admin (Lot 10): every API
    route except health and login requires a profile."""
    response = anonymous_client.post(
        "/api/auth/setup",
        json={
            "email": "admin@example.com",
            "first_name": "Ada",
            "last_name": "Admin",
            "password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return anonymous_client


@pytest.fixture
def make_user(client: TestClient, make_client: object) -> object:
    """Create a profile through the admin API and return a second client
    logged in as it (same instance, separate cookie jar)."""

    def factory(email: str = "user@example.com", role: str = "user") -> TestClient:
        created = client.post(
            "/api/users",
            json={
                "email": email,
                "first_name": email.split("@")[0].capitalize(),
                "last_name": "Tester",
                "role": role,
                "password": USER_PASSWORD,
            },
        )
        assert created.status_code == 201, created.text
        other = as_app_client(TestClient(client.app))
        logged = other.post(
            "/api/auth/login", json={"user_id": created.json()["id"], "password": USER_PASSWORD}
        )
        assert logged.status_code == 200, logged.text
        return other

    return factory
