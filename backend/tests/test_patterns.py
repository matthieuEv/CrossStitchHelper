from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.codec import base64_to_bytes, decode_uint16_layer, get_bit
from app.db import get_session_factory
from app.seed import DEMO_PATTERN_ID, HEIGHT, WIDTH, seed_demo_pattern


@pytest.fixture
def seeded_client(client: TestClient) -> Iterator[TestClient]:
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    yield client


def test_list_patterns_empty_by_default(client: TestClient) -> None:
    response = client.get("/api/patterns")
    assert response.status_code == 200
    assert response.json() == []


def test_list_patterns_includes_seeded_demo(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/patterns")
    assert response.status_code == 200
    [summary] = response.json()
    assert summary["id"] == DEMO_PATTERN_ID
    assert summary["width"] == WIDTH
    assert summary["height"] == HEIGHT
    assert summary["palette_count"] == 12
    # La bordure est pré-cochée par le seed : ni 0 % ni 100 %.
    assert 0 < summary["percent"] < 100
    assert summary["stitched_count"] > 0


def test_get_pattern_detail_exposes_palette(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == WIDTH
    assert len(body["palette"]) == 12
    assert body["palette"][0]["index_in_grid"] == 1


def test_get_pattern_detail_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/api/patterns/does-not-exist")
    assert response.status_code == 404


def test_get_grid_round_trips_cell_values(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/grid")
    assert response.status_code == 200
    body = response.json()
    assert body["encoding"] == "uint16le"

    layer = decode_uint16_layer(base64_to_bytes(body["layer_full"]))
    assert len(layer) == WIDTH * HEIGHT
    # La bordure (3 premières/dernières cases de chaque bord) est l'index 1.
    assert layer[0] == 1
    assert layer[WIDTH - 1] == 1


def test_get_progress_matches_seeded_bitmap(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["cell_count"] == WIDTH * HEIGHT

    bitmap = base64_to_bytes(body["bitmap"])
    # Coin haut-gauche : dans la bordure pré-brodée par le seed.
    assert get_bit(bitmap, 0) is True
    # Centre de la grille : jamais dans la bordure.
    center_index = (HEIGHT // 2) * WIDTH + WIDTH // 2
    assert get_bit(bitmap, center_index) is False


def test_sync_progress_applies_ops_and_bumps_version(seeded_client: TestClient) -> None:
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()

    # Index choisi loin de la bordure (déjà cochée par le seed) : row 90, col 130.
    interior_index = 90 * WIDTH + 130
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": before["version"],
            "ops": [{"index": interior_index, "stitched": True}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == before["version"] + 1
    assert body["stitched_count"] == before["stitched_count"] + 1
    assert body["conflict"] is False
    assert body["missing_ops"] == []

    after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    bitmap = base64_to_bytes(after["bitmap"])
    assert get_bit(bitmap, interior_index) is True


def test_sync_progress_is_idempotent(seeded_client: TestClient) -> None:
    op = {"index": 700, "stitched": True}
    first = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress", json={"base_version": 1, "ops": [op]}
    ).json()
    second = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": first["version"], "ops": [op]},
    ).json()
    # Cocher deux fois la même case ne doit pas doubler le compteur.
    assert second["stitched_count"] == first["stitched_count"]
    assert second["version"] == first["version"] + 1


def test_sync_progress_reports_missing_ops_for_stale_client(seeded_client: TestClient) -> None:
    base = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()

    # Un premier appareil coche une case.
    device_a = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": base["version"], "ops": [{"index": 10000, "stitched": True}]},
    ).json()
    assert device_a["version"] == base["version"] + 1

    # Un second appareil, resté sur l'ancienne version, coche une case différente.
    device_b = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": base["version"], "ops": [{"index": 10001, "stitched": True}]},
    ).json()
    assert device_b["conflict"] is True
    assert device_b["missing_ops"] == [{"index": 10000, "stitched": True}]
    assert device_b["version"] == device_a["version"] + 1

    final = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    bitmap = base64_to_bytes(final["bitmap"])
    assert get_bit(bitmap, 10000) is True
    assert get_bit(bitmap, 10001) is True


def test_sync_progress_pure_poll_does_not_bump_version(seeded_client: TestClient) -> None:
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": before["version"], "ops": []},
    )
    assert response.status_code == 200
    assert response.json()["version"] == before["version"]


def test_sync_progress_rejects_out_of_range_index(seeded_client: TestClient) -> None:
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": 1, "ops": [{"index": WIDTH * HEIGHT, "stitched": True}]},
    )
    assert response.status_code == 400


def test_sync_progress_404_for_unknown_pattern(client: TestClient) -> None:
    response = client.post(
        "/api/patterns/does-not-exist/progress",
        json={"base_version": 0, "ops": []},
    )
    assert response.status_code == 404


def test_export_produces_a_self_contained_cshp_archive(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(archive.namelist()) == {"pattern.json", "grid.bin", "progress.bin", "README.txt"}

    manifest = json.loads(archive.read("pattern.json"))
    assert manifest["format"] == "cshp"
    assert manifest["pattern"]["width"] == WIDTH
    assert manifest["pattern"]["height"] == HEIGHT
    assert len(manifest["palette"]) == 12
    assert manifest["grid"]["width"] == WIDTH
    assert manifest["progress"]["version"] == 1

    grid_bytes = archive.read("grid.bin")
    assert len(grid_bytes) == WIDTH * HEIGHT * 2  # uint16 little-endian, une valeur par case
    layer = decode_uint16_layer(grid_bytes)
    # Même contenu que ce que /grid renvoie en base64 — l'export ne doit pas
    # réencoder ou tronquer les octets stockés en base.
    grid_response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/grid").json()
    assert layer == decode_uint16_layer(base64_to_bytes(grid_response["layer_full"]))

    progress_bytes = archive.read("progress.bin")
    progress_response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert progress_bytes == base64_to_bytes(progress_response["bitmap"])


def test_export_404_for_unknown_pattern(client: TestClient) -> None:
    assert client.get("/api/patterns/does-not-exist/export").status_code == 404


def test_activity_is_empty_for_a_pattern_with_no_progress_events(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/activity")
    assert response.status_code == 200
    body = response.json()
    assert len(body["activity"]) == 7
    assert all(day["stitches"] == 0 for day in body["activity"])
    assert body["sessions"] == []


def test_activity_reflects_a_real_progress_sync(seeded_client: TestClient) -> None:
    base = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": base["version"],
            "ops": [
                {"index": 90 * WIDTH + 130, "stitched": True},
                {"index": 90 * WIDTH + 131, "stitched": True},
            ],
        },
    )

    body = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/activity").json()
    assert sum(day["stitches"] for day in body["activity"]) == 2
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["stitches"] == 2
    assert body["sessions"][0]["hours_ago"] < 0.01


def test_activity_404_for_unknown_pattern(client: TestClient) -> None:
    assert client.get("/api/patterns/does-not-exist/activity").status_code == 404
