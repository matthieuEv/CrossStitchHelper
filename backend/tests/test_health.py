"""The health endpoint must prove that the whole chain works.

Not just "the server responds": that the database was indeed created in the
configured data directory and that the Alembic migrations were really applied
to it at startup.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings


def test_health_reports_ok_and_applied_migration(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == get_settings().app_version
    assert body["database"] == "ok"
    assert body["schema_revision"] == "0005_progress_extra_layers"


def test_database_is_created_inside_the_configured_data_dir(
    client: TestClient, tmp_path: Path
) -> None:
    # A single directory to back up: if this test breaks, a user backing up
    # their volume would lose data without knowing it.
    assert (tmp_path / "data" / "crossstitchhelper.db").is_file()


def test_openapi_is_served_under_api(client: TestClient) -> None:
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
