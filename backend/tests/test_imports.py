from __future__ import annotations

import io
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image


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
        "crop": None,
        "columns": None,
        "rows": None,
        "palette": [],
        "fills": [],
    }
    assert job["preview"] is None


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
    # 300x200 à l'échelle x3 (borne MAX_PREVIEW_DIMENSION / zoom max 3.0).
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
    # Le second remplissage recouvre le premier — dernière zone gagne, comme
    # `fillSelection` côté client.
    assert response.json()["config"]["columns"] == 5  # non écrasé par ce PATCH partiel


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
    # 16 cases d'index 1 (20 - les 4 recouvertes) + 4 cases d'index 2 (zone 2x2).
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

    # Cocher une case fonctionne exactement comme pour tout autre motif
    # (Lot 1) : l'import n'est qu'une autre façon de peupler `patterns`.
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
