"""Le même processus sert l'API et le frontend construit.

Ces tests protègent trois comportements dont dépend l'installation en une
commande : les routes applicatives profondes doivent renvoyer la coquille HTML,
une route d'API inconnue doit rester une erreur JSON, et le manifeste doit
partir avec le bon type MIME — sans quoi Safari refuse l'ajout à l'écran
d'accueil.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_root_serves_the_built_index(make_client: object, frontend_dist: Path) -> None:
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response = client.get("/")

    assert response.status_code == 200
    assert "CrossStitchHelper" in response.text


def test_deep_application_route_falls_back_to_index(
    make_client: object, frontend_dist: Path
) -> None:
    # `/track` n'existe pas sur le disque : c'est une route gérée côté client.
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response = client.get("/track")

    assert response.status_code == 200
    assert "CrossStitchHelper" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_unknown_api_route_stays_a_json_error(
    make_client: object, frontend_dist: Path
) -> None:
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_hashed_assets_are_cached_forever(make_client: object, frontend_dist: Path) -> None:
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_service_worker_and_manifest_are_never_cached(
    make_client: object, frontend_dist: Path
) -> None:
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        service_worker = client.get("/sw.js")
        manifest = client.get("/manifest.webmanifest")

    assert service_worker.headers["cache-control"] == "no-cache"
    assert manifest.headers["cache-control"] == "no-cache"
    assert manifest.headers["content-type"].startswith("application/manifest+json")


def test_path_traversal_is_refused(make_client: object, frontend_dist: Path) -> None:
    # Une tentative de sortir du répertoire de build doit retomber sur l'index,
    # jamais servir un fichier du système.
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response: TestClient = client.get("/../../etc/passwd")

    assert response.status_code == 200
    assert "root:" not in response.text
