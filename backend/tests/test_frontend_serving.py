"""The same process serves the API and the built frontend.

These tests protect three behaviours the one-command installation depends
on: deep application routes must return the HTML shell, an unknown API route
must remain a JSON error, and the manifest must be sent with the right MIME
type — otherwise Safari refuses to add it to the home screen.
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
    # `/track` does not exist on disk: it is a client-side route.
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
    # An attempt to escape the build directory must fall back to the index,
    # never serve a system file.
    with make_client(frontend_dist) as client:  # type: ignore[operator]
        response: TestClient = client.get("/../../etc/passwd")

    assert response.status_code == 200
    assert "root:" not in response.text
