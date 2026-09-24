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
    # The border is pre-checked by the seed: neither 0% nor 100%.
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
    # The border (first/last 3 cells of each edge) is index 1.
    assert layer[0] == 1
    assert layer[WIDTH - 1] == 1


def test_get_progress_matches_seeded_bitmap(seeded_client: TestClient) -> None:
    response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["cell_count"] == WIDTH * HEIGHT

    bitmap = base64_to_bytes(body["bitmap"])
    # Top-left corner: inside the border pre-stitched by the seed.
    assert get_bit(bitmap, 0) is True
    # Centre of the grid: never in the border.
    center_index = (HEIGHT // 2) * WIDTH + WIDTH // 2
    assert get_bit(bitmap, center_index) is False


def test_sync_progress_applies_ops_and_bumps_version(seeded_client: TestClient) -> None:
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()

    # Index chosen far from the border (already checked by the seed): row 90, col 130.
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
    # Checking the same cell twice must not double the counter.
    assert second["stitched_count"] == first["stitched_count"]
    assert second["version"] == first["version"] + 1


def test_sync_progress_reports_missing_ops_for_stale_client(seeded_client: TestClient) -> None:
    base = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()

    # A first device checks a cell.
    device_a = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": base["version"], "ops": [{"index": 10000, "stitched": True}]},
    ).json()
    assert device_a["version"] == base["version"] + 1

    # A second device, still on the old version, checks a different cell.
    device_b = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": base["version"], "ops": [{"index": 10001, "stitched": True}]},
    ).json()
    assert device_b["conflict"] is True
    assert device_b["missing_ops"] == [{"layer": "full", "index": 10000, "stitched": True}]
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


# (bitmap key, index not yet checked on the demo pattern) — `app/seed.py`
# already marks 5/10 half stitches and 6/12 quarter stitches as done, but in
# the space of the *whole grid's cells* (as for `full`, not in the narrower
# space of only the cells carrying a 1/2 or 1/4 stitch): cell (0, 9) is not
# one of them, so it is guaranteed unchecked. For `backstitch`/`knot`, the
# index space is indeed the narrower one of the elements of
# `Grid.backstitch_json`/`french_knots_json` themselves — only 0 and 1 (out
# of 4 segments), then 0, 2 and 4 (out of 6 knots), are checked at the start.
_UNCHECKED_INDEX_BY_LAYER = {
    "half": ("bitmap_half", 9),
    "quarter": ("bitmap_quarter", 9),
    "backstitch": ("bitmap_backstitch", 2),
    "knot": ("bitmap_knots", 1),
}


@pytest.mark.parametrize("layer", ["half", "quarter", "backstitch", "knot"])
def test_sync_progress_handles_each_special_layer_independently(
    seeded_client: TestClient, layer: str
) -> None:
    """Each category has its own bitmap and its own index space — see
    `app/models.py::Progress` and `app/api/patterns.py::_LAYER_ATTR`. The
    demo pattern has content in all five categories since Lot 8
    (`app/seed.py`), so each one can really be exercised here."""
    bitmap_key, target = _UNCHECKED_INDEX_BY_LAYER[layer]
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert get_bit(base64_to_bytes(before[bitmap_key]), target) is False

    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": before["version"],
            "ops": [{"layer": layer, "index": target, "stitched": True}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == before["version"] + 1
    # Checking a backstitch segment or a knot must never inflate
    # `stitched_count` (full stitches only, §7.1 unchanged) — except for
    # `layer == "full"`, not tested here (already covered by existing tests).
    assert body["stitched_count"] == before["stitched_count"]

    after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert get_bit(base64_to_bytes(after[bitmap_key]), target) is True
    # The other bitmaps must not have changed.
    other_keys = ["bitmap", "bitmap_half", "bitmap_quarter", "bitmap_backstitch", "bitmap_knots"]
    for other_key in other_keys:
        if other_key == bitmap_key:
            continue
        assert after[other_key] == before[other_key]


def test_sync_progress_rejects_index_out_of_range_for_its_own_layer(
    seeded_client: TestClient,
) -> None:
    """An `index` valid for `full` (large grid) but out of range for
    `backstitch` (4 segments on the demo pattern) must be rejected — index
    spaces are never shared between categories."""
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": 1, "ops": [{"layer": "backstitch", "index": 4, "stitched": True}]},
    )
    assert response.status_code == 400


def test_sync_progress_defaults_to_full_layer_when_omitted(seeded_client: TestClient) -> None:
    """Compatibility: a client that ignores `layer` (as before Lot 8) keeps
    checking a full stitch, with no change to its observable behaviour."""
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={"base_version": before["version"], "ops": [{"index": 30000, "stitched": True}]},
    )
    assert response.status_code == 200
    after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert get_bit(base64_to_bytes(after["bitmap"]), 30000) is True


def test_sync_progress_mixed_layer_batch_applies_all_of_them(seeded_client: TestClient) -> None:
    before = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    response = seeded_client.post(
        f"/api/patterns/{DEMO_PATTERN_ID}/progress",
        json={
            "base_version": before["version"],
            "ops": [
                {"layer": "full", "index": 20000, "stitched": True},
                {"layer": "backstitch", "index": 2, "stitched": True},
                {"layer": "knot", "index": 5, "stitched": True},
            ],
        },
    )
    assert response.status_code == 200
    after = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()
    assert get_bit(base64_to_bytes(after["bitmap"]), 20000) is True
    assert get_bit(base64_to_bytes(after["bitmap_backstitch"]), 2) is True
    assert get_bit(base64_to_bytes(after["bitmap_knots"]), 5) is True


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
    # The demo pattern has content in all five stitch categories since Lot 8
    # (see `app/seed.py`): the four optional files must therefore all be
    # present here.
    assert set(archive.namelist()) == {
        "pattern.json",
        "grid.bin",
        "grid_half.bin",
        "grid_quarter.bin",
        "progress.bin",
        "progress_half.bin",
        "progress_quarter.bin",
        "progress_backstitch.bin",
        "progress_knots.bin",
        "README.txt",
    }

    manifest = json.loads(archive.read("pattern.json"))
    assert manifest["format"] == "cshp"
    assert manifest["format_version"] == 2
    assert manifest["pattern"]["width"] == WIDTH
    assert manifest["pattern"]["height"] == HEIGHT
    assert len(manifest["palette"]) == 12
    assert manifest["grid"]["width"] == WIDTH
    assert manifest["grid"]["half_file"] == "grid_half.bin"
    assert manifest["grid"]["quarter_file"] == "grid_quarter.bin"
    assert manifest["progress"]["version"] == 1
    assert manifest["progress"]["backstitch_file"] == "progress_backstitch.bin"
    assert manifest["progress"]["knots_file"] == "progress_knots.bin"
    assert len(manifest["segments"]["backstitch"]) == 4
    assert len(manifest["segments"]["french_knots"]) == 6

    grid_response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/grid").json()
    progress_response = seeded_client.get(f"/api/patterns/{DEMO_PATTERN_ID}/progress").json()

    # Same content as what /grid and /progress return in base64 — for each
    # file, never a re-encoding or truncation of the bytes stored in the
    # database.
    for filename, api_b64 in [
        ("grid.bin", grid_response["layer_full"]),
        ("grid_half.bin", grid_response["layer_half"]),
        ("grid_quarter.bin", grid_response["layer_quarter"]),
        ("progress.bin", progress_response["bitmap"]),
        ("progress_half.bin", progress_response["bitmap_half"]),
        ("progress_quarter.bin", progress_response["bitmap_quarter"]),
        ("progress_backstitch.bin", progress_response["bitmap_backstitch"]),
        ("progress_knots.bin", progress_response["bitmap_knots"]),
    ]:
        assert archive.read(filename) == base64_to_bytes(api_b64)

    grid_bytes = archive.read("grid.bin")
    assert len(grid_bytes) == WIDTH * HEIGHT * 2  # uint16 little-endian, one value per cell
    assert decode_uint16_layer(grid_bytes) == decode_uint16_layer(
        base64_to_bytes(grid_response["layer_full"])
    )


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
