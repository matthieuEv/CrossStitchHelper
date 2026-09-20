"""Tests de la sauvegarde/restauration complète (Lot 8, cahier des charges §7.5).

Distinct de `test_patterns.py::test_export_produces_a_self_contained_cshp_archive`
(un seul motif) : ici, l'instance entière — motifs, progression, journal
d'activité, recettes — en un document JSON (`app/backup.py`)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.codec import base64_to_bytes, get_bit
from app.db import get_session_factory
from app.models import Recipe
from app.seed import DEMO_PATTERN_ID, HEIGHT, WIDTH, seed_demo_pattern


@pytest.fixture
def seeded_client(client: TestClient) -> Iterator[TestClient]:
    with get_session_factory()() as session:
        seed_demo_pattern(session)
    yield client


def _add_recipe(recipe_id: str = "recette-test") -> None:
    with get_session_factory()() as session:
        session.add(
            Recipe(
                id=recipe_id,
                fingerprint="a" * 16,
                label="DMC officiel",
                grid_type="C",
                config_json='{"crop_by_page": {}}',
            )
        )
        session.commit()


def test_export_backup_empty_by_default(client: TestClient) -> None:
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert ".json" in response.headers["content-disposition"]
    body = response.json()
    assert body["format"] == "csh-backup"
    assert body["format_version"] == 1
    assert body["patterns"] == []
    assert body["recipes"] == []


def test_export_backup_includes_seeded_pattern_with_all_layers(seeded_client: TestClient) -> None:
    response = seeded_client.get("/api/backup")
    assert response.status_code == 200
    [pattern] = response.json()["patterns"]
    assert pattern["id"] == DEMO_PATTERN_ID
    assert pattern["width"] == WIDTH
    assert pattern["height"] == HEIGHT
    assert len(pattern["palette"]) == 12

    grid = pattern["grid"]
    assert grid is not None
    assert len(base64_to_bytes(grid["layer_full"])) == WIDTH * HEIGHT * 2
    assert grid["layer_half"] is not None
    assert grid["layer_quarter"] is not None
    assert len(grid["backstitch_json"]) > 2  # pas juste "[]"
    assert len(grid["french_knots_json"]) > 2

    progress = pattern["progress"]
    assert progress is not None
    assert get_bit(base64_to_bytes(progress["bitmap"]), 0) is True
    assert progress["bitmap_backstitch"] is not None
    assert progress["bitmap_knots"] is not None


def test_export_backup_includes_progress_events_and_recipes(seeded_client: TestClient) -> None:
    _add_recipe()
    interior_index = 90 * WIDTH + 130
    sync = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": 1,
            "ops": [{"layer": "full", "index": interior_index, "stitched": True}],
        },
    )
    assert sync.status_code == 200

    body = seeded_client.get("/api/backup").json()
    [pattern] = body["patterns"]
    [event] = pattern["progress_events"]
    assert event["version_after"] == 2
    assert str(interior_index) in event["ops_json"]

    [recipe] = body["recipes"]
    assert recipe["id"] == "recette-test"
    assert recipe["label"] == "DMC officiel"


def test_restore_replaces_rather_than_merges(seeded_client: TestClient) -> None:
    _add_recipe("recette-avant-sauvegarde")
    snapshot = seeded_client.get("/api/backup").json()

    # Mutation après la sauvegarde : un second motif, une progression modifiée.
    interior_index = 90 * WIDTH + 130
    seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": 1,
            "ops": [{"layer": "full", "index": interior_index, "stitched": True}],
        },
    )
    _add_recipe("recette-apres-sauvegarde")

    restore = seeded_client.post("/api/backup/restore", json=snapshot)
    assert restore.status_code == 200
    summary = restore.json()
    assert summary["patterns_count"] == 1
    assert summary["recipes_count"] == 1
    assert summary["progress_events_count"] == 0

    patterns_after = seeded_client.get("/api/patterns").json()
    assert [p["id"] for p in patterns_after] == [DEMO_PATTERN_ID]

    progress_after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert progress_after["version"] == 1  # remis à l'état de la sauvegarde, pas 2
    assert get_bit(base64_to_bytes(progress_after["bitmap"]), interior_index) is False

    recipes_after = seeded_client.get("/api/recipes").json()
    assert [r["id"] for r in recipes_after] == ["recette-avant-sauvegarde"]


def test_restore_round_trips_special_stitch_layers(seeded_client: TestClient) -> None:
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    snapshot = seeded_client.get("/api/backup").json()

    restore = seeded_client.post("/api/backup/restore", json=snapshot)
    assert restore.status_code == 200

    after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert after["bitmap_half"] == before["bitmap_half"]
    assert after["bitmap_quarter"] == before["bitmap_quarter"]
    assert after["bitmap_backstitch"] == before["bitmap_backstitch"]
    assert after["bitmap_knots"] == before["bitmap_knots"]
    assert after["stitched_count_backstitch"] == before["stitched_count_backstitch"] > 0
    assert after["stitched_count_knots"] == before["stitched_count_knots"] > 0


def test_restore_rejects_wrong_format_string(client: TestClient) -> None:
    payload = {
        "format": "quelque-chose-d-autre",
        "format_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "patterns": [],
        "recipes": [],
    }
    response = client.post("/api/backup/restore", json=payload)
    assert response.status_code == 422


def test_restore_rejects_unsupported_format_version(seeded_client: TestClient) -> None:
    snapshot = seeded_client.get("/api/backup").json()
    snapshot["format_version"] = 99
    response = seeded_client.post("/api/backup/restore", json=snapshot)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "backup_unsupported_version"
    assert detail["params"] == {"got": 99, "expected": 1}


def test_auto_backup_setting_defaults_enabled_and_is_toggleable(client: TestClient) -> None:
    assert client.get("/api/backup/auto").json() == {"enabled": True}

    response = client.put("/api/backup/auto", json={"enabled": False})
    assert response.status_code == 200
    assert response.json() == {"enabled": False}
    assert client.get("/api/backup/auto").json() == {"enabled": False}
