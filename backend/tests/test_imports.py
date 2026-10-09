from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.codec import base64_to_bytes, decode_uint16_layer


def _wait_for_detection(client: TestClient, job_id: str, timeout: float = 20.0) -> dict[str, Any]:
    """Type A detection (Lot 4) runs as a background task
    (`BackgroundTasks`) — neither `TestClient` nor the real server guarantee
    that it has finished when `POST /api/imports` returns, so we poll
    `GET /api/imports/{id}` until `detecting` drops back to false, exactly as
    the real client would."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"/api/imports/{job_id}").json()
        if not job["detecting"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"detection still running after {timeout}s for job {job_id}")


def _tiny_pdf_bytes() -> bytes:
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page(width=300, height=200)
    rect = pymupdf.Rect(20, 20, 280, 180)  # type: ignore[no-untyped-call]
    page.draw_rect(rect, color=(0, 0, 0), fill=(0.9, 0.85, 0.6))
    return bytes(doc.tobytes())  # type: ignore[no-untyped-call]


def _tiny_png_bytes() -> bytes:
    image = Image.new("RGB", (300, 200), (200, 220, 180))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_pdf(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/imports",
        files={"file": ("motif.pdf", _tiny_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def _upload_image(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/imports",
        files={"file": ("photo.png", _tiny_png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


_SAMPLE_PALETTE = [
    {"code": "310", "name": "Noir", "rgb_hex": "#000000", "symbol_key": "x"},
    {"code": "666", "name": "Rouge vif", "rgb_hex": "#cc0000", "symbol_key": "o"},
]


def test_create_import_accepts_pdf(client: TestClient) -> None:
    job = _upload_pdf(client)
    assert job["kind"] == "pdf"
    assert job["page_count"] == 1
    assert job["status"] == "ready"
    assert job["source_filename"] == "motif.pdf"
    assert job["config"] == {
        "crop_by_page": {},
        "columns": None,
        "rows": None,
        "palette": [],
        "fills": [],
        "detected_cells": None,
        "uncertain_cells": None,
        # Special stitches (Lot 9, type A): nothing at this step, before the
        # background detection has even had a chance to run.
        "detected_half": None,
        "detected_quarter": None,
        "detected_backstitch": None,
        "detected_french_knots": None,
        "detected_fabric_count": None,
    }
    assert job["preview"] is None


def test_create_import_of_trivial_pdf_finishes_detection_with_no_result(
    client: TestClient,
) -> None:
    job = _upload_pdf(client)
    assert job["detecting"] is True  # background task just scheduled
    job = _wait_for_detection(client, job["id"])
    assert job["detection"] is None


def test_manual_fills_override_detected_cells(client: TestClient) -> None:
    """A correction painted by hand must always win over the automatically
    detected grid (Lot 4) — without going through a real PDF detection, by
    setting `detected_cells` directly as the background task would once
    finished."""
    job = _upload_pdf(client)
    job_id = job["id"]
    _wait_for_detection(client, job_id)

    detected_cells = [1, 1, 1, 1]  # 2x2, entirely detected as DMC 310
    client.patch(
        f"/api/imports/{job_id}/config",
        json={
            "columns": 2,
            "rows": 2,
            "palette": _SAMPLE_PALETTE,
            "detected_cells": detected_cells,
        },
    )
    baseline = client.post(f"/api/imports/{job_id}/extract").json()
    assert baseline["preview"]["filled_count"] == 4

    # Correct one cell to the second colour — the rest must remain from the
    # detection, not fall back to empty.
    client.patch(
        f"/api/imports/{job_id}/config",
        json={"fills": [{"x0": 0, "y0": 0, "x1": 0, "y1": 0, "palette_index": 2}]},
    )
    corrected = client.post(f"/api/imports/{job_id}/extract").json()
    assert corrected["preview"]["filled_count"] == 4  # still 4 painted cells
    layer = decode_uint16_layer(base64_to_bytes(corrected["preview"]["layer_full"]))
    assert layer[0] == 2  # la correction a pris le dessus
    assert layer[1] == 1  # the other cells keep the original detection
    assert layer[2] == 1
    assert layer[3] == 1


def test_changing_dimensions_drops_a_now_mismatched_detected_base(client: TestClient) -> None:
    """Real bug found during manual testing (Lot 4): if `detected_cells` was
    set for one size (here 2x2, as the background task would for real
    detected dimensions) and the user then changes `columns`/`rows` without
    sending `detected_cells` back — exactly what the wizard sends when
    clicking Continue with its own dimensions typed by hand — `apply_fills`
    received a `base` of the wrong length and the API answered 500 instead of
    simply starting again from an empty grid for the new dimensions."""
    job = _upload_pdf(client)
    job_id = job["id"]
    _wait_for_detection(client, job_id)

    client.patch(
        f"/api/imports/{job_id}/config",
        json={"columns": 2, "rows": 2, "palette": _SAMPLE_PALETTE, "detected_cells": [1, 1, 1, 1]},
    )

    response = client.patch(
        f"/api/imports/{job_id}/config",
        json={"columns": 3, "rows": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["detected_cells"] is None  # meaningless for 3x3
    assert body["preview"]["cell_count"] == 9
    assert body["preview"]["filled_count"] == 0  # starts from an empty grid, not a crash


def test_create_import_accepts_image(client: TestClient) -> None:
    job = _upload_image(client)
    assert job["kind"] == "image"
    assert job["page_count"] == 1


def test_create_import_rejects_unsupported_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/imports",
        files={"file": ("motif.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_create_import_rejects_oversized_file(
    make_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CSH_IMPORT_MAX_UPLOAD_MB", "1")
    with make_client(None) as client:  # type: ignore[operator]
        big = b"0" * (2 * 1024 * 1024)
        response = client.post(
            "/api/imports", files={"file": ("big.png", big, "image/png")}
        )
        assert response.status_code == 400


def test_get_import_returns_current_state(client: TestClient) -> None:
    job = _upload_pdf(client)
    response = client.get(f"/api/imports/{job['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == job["id"]


def test_get_import_404_for_unknown_job(client: TestClient) -> None:
    assert client.get("/api/imports/does-not-exist").status_code == 404


def test_page_preview_returns_png_for_pdf(client: TestClient) -> None:
    job = _upload_pdf(client)
    response = client.get(f"/api/imports/{job['id']}/pages/1/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    image = Image.open(io.BytesIO(response.content))
    assert image.format == "PNG"
    # 300x200 scaled x3 (MAX_PREVIEW_DIMENSION bound / max zoom 3.0).
    assert image.size == (900, 600)


def test_page_preview_404_for_out_of_range_pdf_page(client: TestClient) -> None:
    job = _upload_pdf(client)
    assert client.get(f"/api/imports/{job['id']}/pages/2/preview").status_code == 404


def test_page_preview_image_only_has_page_one(client: TestClient) -> None:
    job = _upload_image(client)
    assert client.get(f"/api/imports/{job['id']}/pages/1/preview").status_code == 200
    assert client.get(f"/api/imports/{job['id']}/pages/2/preview").status_code == 404


def test_patch_config_merges_fields_and_computes_preview(client: TestClient) -> None:
    job = _upload_pdf(client)
    job_id = job["id"]

    response = client.patch(
        f"/api/imports/{job_id}/config",
        json={"columns": 5, "rows": 4, "palette": _SAMPLE_PALETTE},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["cell_count"] == 20
    assert body["preview"]["filled_count"] == 0

    response = client.patch(
        f"/api/imports/{job_id}/config",
        json={
            "fills": [
                {"x0": 0, "y0": 0, "x1": 4, "y1": 3, "palette_index": 1},
                {"x0": 1, "y0": 1, "x1": 2, "y1": 2, "palette_index": 2},
            ]
        },
    )
    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["filled_count"] == 20
    # The second fill covers the first — last area wins, like
    # `fillSelection` on the client.
    assert response.json()["config"]["columns"] == 5  # not overwritten by this partial PATCH


def test_extract_recomputes_preview_without_changing_config(client: TestClient) -> None:
    job = _upload_pdf(client)
    job_id = job["id"]
    client.patch(
        f"/api/imports/{job_id}/config",
        json={
            "columns": 3,
            "rows": 3,
            "palette": _SAMPLE_PALETTE,
            "fills": [{"x0": 0, "y0": 0, "x1": 0, "y1": 0, "palette_index": 1}],
        },
    )
    response = client.post(f"/api/imports/{job_id}/extract")
    assert response.status_code == 200
    assert response.json()["preview"]["filled_count"] == 1


def test_commit_requires_complete_config(client: TestClient) -> None:
    job = _upload_pdf(client)
    response = client.post(
        f"/api/imports/{job['id']}/commit", json={"name": "Sans configuration"}
    )
    assert response.status_code == 400


def test_commit_creates_a_real_usable_pattern(client: TestClient) -> None:
    job = _upload_pdf(client)
    job_id = job["id"]
    client.patch(
        f"/api/imports/{job_id}/config",
        json={
            "columns": 5,
            "rows": 4,
            "palette": _SAMPLE_PALETTE,
            "fills": [
                {"x0": 0, "y0": 0, "x1": 4, "y1": 3, "palette_index": 1},
                {"x0": 1, "y0": 1, "x1": 2, "y1": 2, "palette_index": 2},
            ],
        },
    )

    response = client.post(
        f"/api/imports/{job_id}/commit", json={"name": "Motif peint à la main", "fabric_count": 14}
    )
    assert response.status_code == 200
    pattern_id = response.json()["pattern_id"]

    detail = client.get(f"/api/patterns/{pattern_id}").json()
    assert detail["name"] == "Motif peint à la main"
    assert detail["width"] == 5
    assert detail["height"] == 4
    assert detail["fabric_count"] == 14
    assert len(detail["palette"]) == 2
    # 16 cells of index 1 (20 - the 4 covered) + 4 cells of index 2 (2x2 area).
    counts = {entry["code"]: entry["count_full"] for entry in detail["palette"]}
    assert counts["310"] == 16
    assert counts["666"] == 4

    grid = client.get(f"/api/patterns/{pattern_id}/grid").json()
    assert grid["width"] == 5
    assert grid["height"] == 4

    progress = client.get(f"/api/patterns/{pattern_id}/progress").json()
    assert progress["version"] == 1
    assert progress["stitched_count"] == 0
    assert progress["cell_count"] == 20

    # Checking a cell works exactly as for any other pattern (Lot 1): import
    # is just another way of populating `patterns`.
    sync = client.post(
        f"/api/patterns/{pattern_id}/progress",
        json={"base_version": 1, "ops": [{"index": 0, "stitched": True}]},
    ).json()
    assert sync["version"] == 2
    assert sync["stitched_count"] == 1


def test_commit_is_final(client: TestClient) -> None:
    job = _upload_pdf(client)
    job_id = job["id"]
    client.patch(
        f"/api/imports/{job_id}/config",
        json={"columns": 2, "rows": 2, "palette": _SAMPLE_PALETTE},
    )
    client.post(f"/api/imports/{job_id}/commit", json={"name": "Motif"})

    assert (
        client.patch(f"/api/imports/{job_id}/config", json={"columns": 3}).status_code == 400
    )
    assert client.post(f"/api/imports/{job_id}/extract").status_code == 400
    assert (
        client.post(f"/api/imports/{job_id}/commit", json={"name": "Encore"}).status_code == 400
    )


def test_commit_removes_the_staged_source_file(client: TestClient) -> None:
    from app.config import get_settings

    job = _upload_pdf(client)
    job_id = job["id"]
    settings = get_settings()
    job_dir = settings.imports_dir / job_id
    assert job_dir.is_dir()

    client.patch(
        f"/api/imports/{job_id}/config",
        json={"columns": 2, "rows": 2, "palette": _SAMPLE_PALETTE},
    )
    client.post(f"/api/imports/{job_id}/commit", json={"name": "Motif"})

    assert not job_dir.exists()


_TYPE_A_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "cafe-brasserie-charting-export"
    / "CaffeBrasseriecoloursymbols.pdf"
)


def _upload_real_type_a_pdf(client: TestClient) -> dict[str, Any]:
    if not _TYPE_A_FIXTURE.is_file():
        pytest.skip(f"fixture manquante : {_TYPE_A_FIXTURE}")
    with _TYPE_A_FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports",
            files={"file": ("CaffeBrasseriecoloursymbols.pdf", handle, "application/pdf")},
        )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def test_create_import_of_real_type_a_pdf_prefills_config_from_detection(
    client: TestClient,
) -> None:
    """End to end, real fixture (Lot 4): `POST /api/imports` of a real type A
    export must come out with the configuration already pre-filled by
    `app/type_a.py`, without any user action — this is the roadmap's "done
    when" criterion (`docs/roadmap.md`, Lot 4). Slower than the rest of this
    suite (real structural analysis, ~10s): that is expected, see
    `tests/test_type_a.py` for the exhaustive verification of the
    extraction's correctness itself — this test only checks the wiring into
    the import API."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)

    assert job["detecting"] is False
    assert job["detection"]["grid_type"] == "A"
    assert job["detection"]["confidence"] > 0.85

    config = job["config"]
    assert config["columns"] == 255
    assert config["rows"] == 180
    # 34 DMC colours from the "Full Stitches" legend — the same thread counts
    # once even if it is also used for 1/2, 1/4, backstitch or knot (Lot 9,
    # `app/type_a.py::_build_palette`). Since that lot, no "Unrecognised
    # symbol" entry remains on this file (see
    # `tests/test_type_a.py::test_no_symbol_is_left_unmapped`).
    dmc_entries = [entry for entry in config["palette"] if entry["code"]]
    assert len(dmc_entries) == 34
    assert len(config["palette"]) == 34
    assert config["detected_cells"] is not None
    assert len(config["detected_cells"]) == 255 * 180

    # The summary (wizard step 4) must already have a usable grid without any
    # area having been painted by hand.
    assert job["preview"] is not None
    assert job["preview"]["filled_count"] > 0


def test_real_type_a_pdf_prefills_real_symbol_images_not_just_letters(
    client: TestClient,
) -> None:
    """The displayed symbol must be the PDF's, not a synthetic letter
    (`app.type_a.symbol_key`, only ever meant as an internal fallback) —
    end-to-end wiring of `app.imports_engine.render_symbol_svg`, whose
    correctness is verified exhaustively in `tests/test_type_a.py`."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)

    dmc_entries = [entry for entry in job["config"]["palette"] if entry["code"]]
    assert dmc_entries
    for entry in dmc_entries:
        assert entry["symbol_svg"] is not None
        assert entry["symbol_svg"].startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert "image/png;base64," in entry["symbol_svg"]


def test_symbol_images_survive_commit_into_a_real_pattern(client: TestClient) -> None:
    """The real symbol must remain available after validation — the source
    PDF no longer is (§3: never kept beyond extraction), so this is the only
    moment it can be captured."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)
    response = client.post(
        f"/api/imports/{job['id']}/commit", json={"name": "Café Brasserie e2e"}
    )
    assert response.status_code == 200
    pattern_id = response.json()["pattern_id"]

    detail = client.get(f"/api/patterns/{pattern_id}").json()
    dmc_entries = [entry for entry in detail["palette"] if entry["code"]]
    assert dmc_entries
    for entry in dmc_entries:
        assert entry["symbol_svg"] is not None
        assert "image/png;base64," in entry["symbol_svg"]


def test_special_stitches_survive_commit_into_a_real_pattern(client: TestClient) -> None:
    """Lot 9 end to end: the 1/2, 1/4, backstitch and knot stitches detected
    by `app/type_a.py` (verified exhaustively in `tests/test_type_a.py`) must
    really reach the committed pattern, not just the import job — that is
    the whole point of the `commit()` wiring added in this lot. Reference
    values: page 11 of the PDF (see `fixtures/README.md`, "Special stitches"
    section)."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)

    # The detected fabric count ("Fabric: Aida 16") must be available so the
    # frontend can pre-fill the summary step — see `ImportScreen.tsx`. It is
    # reused here as is to commit, as a user who did not touch the pre-filled
    # value would.
    assert job["config"]["detected_fabric_count"] == 16

    response = client.post(
        f"/api/imports/{job['id']}/commit",
        json={
            "name": "Café Brasserie Lot 9",
            "fabric_count": job["config"]["detected_fabric_count"],
        },
    )
    assert response.status_code == 200
    pattern_id = response.json()["pattern_id"]

    grid = client.get(f"/api/patterns/{pattern_id}/grid").json()
    assert grid["layer_half"] is not None
    assert grid["layer_quarter"] is not None
    assert len(grid["backstitch"]) > 1000  # 1182 measured (see the Lot 9 report)
    assert len(grid["french_knots"]) == 3

    detail = client.get(f"/api/patterns/{pattern_id}").json()
    palette = {entry["code"]: entry for entry in detail["palette"]}
    # DMC 3031: 4 quarter stitches declared on page 11.
    assert palette["3031"]["count_quarter"] == 4
    # DMC 742: 3 knots declared on page 11.
    assert palette["742"]["count_french"] == 3
    # DMC 310: 114.2 (real unit: inches, see fixtures/README.md) — so
    # 114.2 * 2.54 cm, within 1% (same tolerance as `tests/test_type_a.py`).
    expected_cm = 114.2 * 2.54
    assert palette["310"]["backstitch_length_cm"] is not None
    assert abs(palette["310"]["backstitch_length_cm"] - expected_cm) < 0.01 * expected_cm


def test_backstitch_length_is_none_without_a_declared_fabric_count(client: TestClient) -> None:
    """Never a made-up centimetre (§3, `TypeAPaletteEntry.backstitch_length_cells`):
    if the user removes the pre-filled value without replacing it, the length
    stays `None` rather than a silent approximate conversion."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)
    response = client.post(
        f"/api/imports/{job['id']}/commit", json={"name": "Sans compte de toile"}
    )
    assert response.status_code == 200
    pattern_id = response.json()["pattern_id"]

    detail = client.get(f"/api/patterns/{pattern_id}").json()
    palette = {entry["code"]: entry for entry in detail["palette"]}
    assert palette["310"]["backstitch_length_cm"] is None
    # Counts that do not depend on the fabric count remain correct.
    assert palette["3031"]["count_quarter"] == 4


def test_manual_config_started_before_detection_finishes_is_not_overwritten(
    client: TestClient,
) -> None:
    """Real bug found during manual testing (Lot 4): the message shown during
    analysis explicitly invites the user to crop or enter the dimensions by
    hand while waiting (`import.detection.running`). If the background task
    finishes afterwards, it must not silently overwrite that input —
    otherwise the client, which stopped applying the server's responses as
    soon as it detected a manual change (`manualEditRef` on the frontend),
    then sends its own dimensions on top of a now inconsistent
    `detected_cells`, crashing the API (see
    `test_changing_dimensions_drops_a_now_mismatched_detected_base`).

    The real timing of the background task scheduled by `POST /api/imports`
    is not guaranteed (neither by the real server nor by `TestClient`):
    rather than guessing a race window, this test builds an already fully
    settled job (upload of a trivial PDF, whose detection finishes almost
    instantly and changes nothing), substitutes the real reference file into
    it, corrects the configuration by hand, then invokes
    `_run_auto_detection` directly — reproducing the bug's exact order of
    operations without depending on any timing."""
    from app.api.imports import _run_auto_detection
    from app.config import get_settings

    if not _TYPE_A_FIXTURE.is_file():
        pytest.skip(f"fixture manquante : {_TYPE_A_FIXTURE}")

    job = _upload_pdf(client)
    job_id = job["id"]
    _wait_for_detection(client, job_id)  # trivial PDF: nothing to detect, config stays blank

    source_path = get_settings().imports_dir / job_id / "source.pdf"
    source_path.write_bytes(_TYPE_A_FIXTURE.read_bytes())

    # The user corrects by hand — the equivalent of what they would have
    # typed while waiting, had they been faster than the analysis on a real
    # server.
    client.patch(f"/api/imports/{job_id}/config", json={"columns": 92, "rows": 74})

    _run_auto_detection(job_id, source_path)

    job = client.get(f"/api/imports/{job_id}").json()
    # Warning as code + parameters (translation audit, Lot 8): the final text
    # is composed on the client.
    assert "detection.manual_config_kept" in [w["code"] for w in job["detection"]["warnings"]]
    config = job["config"]
    assert config["columns"] == 92  # never overwritten by detection
    assert config["rows"] == 74
    assert config["detected_cells"] is None  # never set on top of input already in progress


_BOTANICAL_CITRUS_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "botanical-citrus-dmc"
    / "agrumes_-_planche_botanique.pdf"
)


def _upload_real_type_bc_pdf(client: TestClient) -> dict[str, Any]:
    if not _BOTANICAL_CITRUS_FIXTURE.is_file():
        pytest.skip(f"fixture manquante : {_BOTANICAL_CITRUS_FIXTURE}")
    with _BOTANICAL_CITRUS_FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports",
            files={"file": ("agrumes_-_planche_botanique.pdf", handle, "application/pdf")},
        )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def test_create_import_of_real_type_bc_pdf_prefills_config_from_detection(
    client: TestClient,
) -> None:
    """End to end, real fixture (Lot 5): `POST /api/imports` of a DMC vector
    PDF without a symbol font must come out with `detect_type_a` having
    handed over to `detect_type_bc` (see `_run_auto_detection`), the
    configuration already pre-filled — this is the roadmap's "done when"
    criterion (`docs/roadmap.md`, Lot 5). The extraction's correctness itself
    is verified exhaustively in `tests/test_type_bc.py`; this test only
    checks the wiring into the import API."""
    job = _wait_for_detection(client, _upload_real_type_bc_pdf(client)["id"], timeout=30.0)

    assert job["detecting"] is False
    assert job["detection"]["grid_type"] == "C"

    config = job["config"]
    assert config["columns"] is not None
    assert config["rows"] is not None
    assert config["detected_cells"] is not None
    assert len(config["detected_cells"]) == config["columns"] * config["rows"]
    # `botanical-citrus-dmc` overlays a real symbol page (Lot 5,
    # `tests/test_type_bc.py`) — at least one entry must therefore carry a
    # real symbol cut out of the PDF, exactly like type A (Lot 4).
    assert any(entry["symbol_svg"] is not None for entry in config["palette"])

    # Explicit flagging of uncertain cells (roadmap Lot 5, "done when"): never
    # a wrong cell left without any indication in the API.
    assert config["uncertain_cells"]
    assert all(0 <= idx < len(config["detected_cells"]) for idx in config["uncertain_cells"])

    assert job["preview"] is not None
    assert job["preview"]["filled_count"] > 0


def test_real_type_bc_pattern_survives_commit_with_its_uncertain_cells_config(
    client: TestClient,
) -> None:
    """The validated configuration (never the detection result itself, which
    is only a proposal) must be the one actually archived in
    `patterns.import_config_json` — including `uncertain_cells`, so that a
    future recipe or a future diagnostic tool (out of Lot 5's scope) can find
    what had been flagged as doubtful at import time."""
    job = _wait_for_detection(client, _upload_real_type_bc_pdf(client)["id"], timeout=30.0)
    response = client.post(f"/api/imports/{job['id']}/commit", json={"name": "Botanical e2e"})
    assert response.status_code == 200
    pattern_id = response.json()["pattern_id"]

    detail = client.get(f"/api/patterns/{pattern_id}").json()
    assert detail["width"] * detail["height"] == len(job["config"]["detected_cells"])
    dmc_entries = [entry for entry in detail["palette"] if entry["code"]]
    assert any(entry["symbol_svg"] is not None for entry in dmc_entries)
