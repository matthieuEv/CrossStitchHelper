"""Tests for the full backup/restore (Lot 8, specification §7.5).

Distinct from `test_patterns.py::test_export_produces_a_self_contained_cshp_archive`
(a single pattern): here, the whole instance — patterns, progress, activity
log, recipes — as one JSON document (`app/backup.py`)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.codec import (
    base64_to_bytes,
    bitmap_from_indices,
    bytes_to_base64,
    encode_uint16_layer,
    get_bit,
)
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
    assert body["format_version"] == 4
    # Lot 10: the profiles travel with the backup — here only the admin
    # created by the `client` fixture.
    [admin] = body["users"]
    assert admin["email"] == "admin@example.com"
    assert admin["role"] == "admin"
    assert admin["password_hash"].startswith("$argon2id$")
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
    assert grid["layer_quarter"] is None  # format version 3 and older only
    assert len(json.loads(grid["quarter_json"])) == 16
    assert len(json.loads(grid["three_quarter_json"])) == 4
    assert len(grid["backstitch_json"]) > 2  # not just "[]"
    assert len(grid["french_knots_json"]) > 2

    progress = pattern["progress"]
    assert progress is not None
    assert get_bit(base64_to_bytes(progress["bitmap"]), 0) is True
    assert progress["bitmap_backstitch"] is not None
    assert progress["bitmap_knots"] is not None
    assert progress["bitmap_three_quarter"] is not None


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

    # Mutation after the backup: a second recipe, modified progress.
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
    assert progress_after["version"] == 1  # back to the backup's state, not 2
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
    assert after["bitmap_three_quarter"] == before["bitmap_three_quarter"]
    assert after["bitmap_backstitch"] == before["bitmap_backstitch"]
    assert after["bitmap_knots"] == before["bitmap_knots"]
    assert after["stitched_count_backstitch"] == before["stitched_count_backstitch"] > 0
    assert after["stitched_count_knots"] == before["stitched_count_knots"] > 0


def test_restore_reads_an_older_backup_quarter_layer_as_top_left_items(
    seeded_client: TestClient,
) -> None:
    """Issue #83: before format version 4, 1/4 stitches were a cell layer
    without a corner. Restoring such a backup turns them into top-left items
    (where they were always drawn), moving their progress and their logged
    operations from the cell's index to the item's."""
    snapshot = seeded_client.get("/api/backup").json()
    snapshot["format_version"] = 3
    [pattern] = snapshot["patterns"]
    cells = [0] * (WIDTH * HEIGHT)
    cells[WIDTH + 2] = 3  # (2, 1)
    cells[5 * WIDTH + 7] = 4  # (7, 5)
    grid = pattern["grid"]
    grid["layer_quarter"] = bytes_to_base64(encode_uint16_layer(cells))
    del grid["quarter_json"], grid["three_quarter_json"]
    progress = pattern["progress"]
    progress["bitmap_quarter"] = bytes_to_base64(
        bitmap_from_indices([5 * WIDTH + 7], WIDTH * HEIGHT)
    )
    del progress["bitmap_three_quarter"]
    pattern["progress_events"].append(
        {
            "id": 9001,
            "ts": "2026-10-01T10:00:00Z",
            "ops_json": json.dumps(
                [
                    {"layer": "quarter", "index": 5 * WIDTH + 7, "stitched": True},
                    {"layer": "full", "index": 3, "stitched": True},
                ]
            ),
            "version_after": 1,
        }
    )

    assert seeded_client.post("/api/backup/restore", json=snapshot).status_code == 200

    grid_after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/grid").json()
    assert grid_after["quarter_stitches"] == [
        {"x": 2, "y": 1, "corner": "tl", "palette_index": 3},
        {"x": 7, "y": 5, "corner": "tl", "palette_index": 4},
    ]
    assert grid_after["three_quarter_stitches"] == []
    progress_after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    quarter_bits = base64_to_bytes(progress_after["bitmap_quarter"])
    assert [get_bit(quarter_bits, index) for index in range(2)] == [False, True]
    events = seeded_client.get("/api/backup").json()["patterns"][0]["progress_events"]
    assert json.loads(events[-1]["ops_json"]) == [
        {"layer": "quarter", "index": 1, "stitched": True},
        {"layer": "full", "index": 3, "stitched": True},
    ]


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
    assert detail["params"] == {"got": 99, "expected": 4}


def test_auto_backup_setting_defaults_enabled_and_is_toggleable(client: TestClient) -> None:
    assert client.get("/api/backup/auto").json() == {"enabled": True}

    response = client.put("/api/backup/auto", json={"enabled": False})
    assert response.status_code == 200
    assert response.json() == {"enabled": False}
    assert client.get("/api/backup/auto").json() == {"enabled": False}


def test_restore_round_trips_labels_and_accepts_backups_without_them(
    seeded_client: TestClient,
) -> None:
    """Issue #57: labels are part of a backup; a backup made before them
    (no `labels` key) still restores, with no labels."""
    seeded_client.patch(f"/api/patterns/{DEMO_PATTERN_ID}", json={"labels": ["Mini", "Mer"]})
    snapshot = seeded_client.get("/api/backup").json()
    assert snapshot["patterns"][0]["labels"] == ["Mini", "Mer"]

    seeded_client.patch(f"/api/patterns/{DEMO_PATTERN_ID}", json={"labels": []})
    assert seeded_client.post("/api/backup/restore", json=snapshot).status_code == 200
    assert seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}").json()["labels"] == [
        "Mini",
        "Mer",
    ]

    del snapshot["patterns"][0]["labels"]
    assert seeded_client.post("/api/backup/restore", json=snapshot).status_code == 200
    assert seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}").json()["labels"] == []
