"""Le point de santé doit prouver que la chaîne complète fonctionne.

Pas seulement « le serveur répond » : que la base a bien été créée dans le
répertoire de données configuré et que les migrations Alembic s'y sont
réellement appliquées au démarrage.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import __version__


def test_health_reports_ok_and_applied_migration(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["database"] == "ok"
    assert body["schema_revision"] == "0004_recipes"


def test_database_is_created_inside_the_configured_data_dir(
    client: TestClient, tmp_path: Path
) -> None:
    # Un seul répertoire à sauvegarder : si ce test casse, l'utilisateur qui
    # sauvegarde son volume perdrait des données sans le savoir.
    assert (tmp_path / "data" / "crossstitchhelper.db").is_file()


def test_openapi_is_served_under_api(client: TestClient) -> None:
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
