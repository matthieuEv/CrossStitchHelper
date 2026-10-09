"""Tests for the recipe library (Lot 6, specification §8.7, §9).

The end-to-end case (`test_recipe_prefills_crop_on_a_second_file_of_the_same_dmc_template`)
uses `botanical-citrus-dmc` then `cucurbit-dmc`: two real files, same
official DMC export template but different patterns (see
`fixtures/README.md` and `tests/test_fingerprint.py`) — exactly the lot's
use case, without having to fabricate a fake pair of files."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
BOTANICAL_CITRUS = FIXTURES_ROOT / "botanical-citrus-dmc" / "agrumes_-_planche_botanique.pdf"
CUCURBIT = FIXTURES_ROOT / "cucurbit-dmc" / "Cucurbitaces.pdf"


def _wait_for_detection(client: TestClient, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"/api/imports/{job_id}").json()
        if not job["detecting"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"detection still running after {timeout}s for job {job_id}")


def _upload(client: TestClient, path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.skip(f"missing fixture: {path}")
    with path.open("rb") as handle:
        response = client.post(
            "/api/imports", files={"file": (path.name, handle, "application/pdf")}
        )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


_SOME_CROP = {"1": {"left": 6.0, "top": 5.0, "right": 4.0, "bottom": 7.0}}


def _tiny_pdf_bytes() -> bytes:
    """A trivial PDF, unrelated to any DMC recipe — its own fingerprint never
    matches that of `BOTANICAL_CITRUS`/`CUCURBIT`, useful for building a
    settled job before substituting a real file into it (same technique as
    `test_imports.py::test_manual_config_started_before_detection_finishes_is_not_overwritten`)."""
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page(width=300, height=200)
    return bytes(doc.tobytes())  # type: ignore[no-untyped-call]


def _upload_tiny_pdf(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/imports", files={"file": ("vide.pdf", _tiny_pdf_bytes(), "application/pdf")}
    )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def test_create_recipe_from_a_validated_job(client: TestClient) -> None:
    job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    assert job["detection"]["grid_type"] == "C"

    client.patch(f"/api/imports/{job['id']}/config", json={"crop_by_page": _SOME_CROP})

    response = client.post("/api/recipes", json={"job_id": job["id"], "label": "DMC officiel"})
    assert response.status_code == 200
    recipe = response.json()
    assert recipe["label"] == "DMC officiel"
    assert recipe["grid_type"] == "C"
    assert recipe["config"]["crop_by_page"] == _SOME_CROP
    assert recipe["usage_count"] == 0


def test_recipe_config_never_carries_dimensions_or_palette(client: TestClient) -> None:
    """Direct guard from `CLAUDE.md`: a recipe must never be able to carry a
    pattern's creative content (dimensions, colours)."""
    job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    response = client.post("/api/recipes", json={"job_id": job["id"], "label": "Test"})
    recipe = response.json()
    assert set(recipe["config"].keys()) == {"crop_by_page"}


def test_create_recipe_rejects_unknown_job(client: TestClient) -> None:
    response = client.post("/api/recipes", json={"job_id": "inconnu", "label": "X"})
    assert response.status_code == 404


def test_list_and_delete_recipe(client: TestClient) -> None:
    job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    recipe_id = client.post(
        "/api/recipes", json={"job_id": job["id"], "label": "DMC officiel"}
    ).json()["id"]

    listed = client.get("/api/recipes").json()
    assert any(r["id"] == recipe_id for r in listed)

    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 404

    listed_after = client.get("/api/recipes").json()
    assert not any(r["id"] == recipe_id for r in listed_after)


def test_recipe_prefills_crop_on_a_second_file_of_the_same_dmc_template(
    client: TestClient,
) -> None:
    first_job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    client.patch(f"/api/imports/{first_job['id']}/config", json={"crop_by_page": _SOME_CROP})
    recipe = client.post(
        "/api/recipes", json={"job_id": first_job["id"], "label": "DMC officiel"}
    ).json()
    assert recipe["usage_count"] == 0

    second_job = _wait_for_detection(client, _upload(client, CUCURBIT)["id"])

    # The cropping comes from the recipe...
    assert second_job["config"]["crop_by_page"] == _SOME_CROP
    assert second_job["applied_recipe"] == {"id": recipe["id"], "label": "DMC officiel"}
    # ...but dimensions and palette remain this file's own — never copied
    # from the recipe (creative content, specification §8.7: "never from the
    # creative content").
    assert second_job["config"]["columns"] is not None
    assert second_job["config"]["rows"] is not None
    assert len(second_job["config"]["palette"]) > 0
    assert second_job["detection"]["grid_type"] == "C"

    used_recipe = next(r for r in client.get("/api/recipes").json() if r["id"] == recipe["id"])
    assert used_recipe["usage_count"] == 1

    commit = client.post(f"/api/imports/{second_job['id']}/commit", json={"name": "Cucurbit"})
    assert commit.status_code == 200
    pattern_id = commit.json()["pattern_id"]

    from app.db import get_session_factory
    from app.models import Pattern

    with get_session_factory()() as session:
        pattern = session.get(Pattern, pattern_id)
        assert pattern is not None
        assert pattern.recipe_id == recipe["id"]


def test_recipe_never_overwrites_an_already_started_manual_crop(client: TestClient) -> None:
    """Same test principle as
    `test_manual_config_started_before_detection_finishes_is_not_overwritten`
    in `test_imports.py`: the background task's real timing is guaranteed
    neither by the server nor by `TestClient`, so rather than guessing a race
    window, this test builds an already settled job then invokes
    `_run_auto_detection` directly after the manual cropping, reproducing the
    exact order without depending on any timing."""
    from app.api.imports import _run_auto_detection
    from app.config import get_settings

    first_job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    client.patch(f"/api/imports/{first_job['id']}/config", json={"crop_by_page": _SOME_CROP})
    client.post("/api/recipes", json={"job_id": first_job["id"], "label": "DMC officiel"})

    if not CUCURBIT.is_file():
        pytest.skip(f"missing fixture: {CUCURBIT}")
    job_id = _upload_tiny_pdf(client)["id"]
    _wait_for_detection(client, job_id)  # trivial PDF, no known fingerprint: nothing to apply

    source_path = get_settings().imports_dir / job_id / "source.pdf"
    source_path.write_bytes(CUCURBIT.read_bytes())

    manual_crop = {"1": {"left": 1.0, "top": 1.0, "right": 1.0, "bottom": 1.0}}
    client.patch(f"/api/imports/{job_id}/config", json={"crop_by_page": manual_crop})

    _run_auto_detection(job_id, source_path)

    second_job = client.get(f"/api/imports/{job_id}").json()
    assert second_job["config"]["crop_by_page"] == manual_crop
    assert second_job["applied_recipe"] is None
