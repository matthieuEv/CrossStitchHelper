"""Tests de la bibliothèque de recettes (Lot 6, cahier des charges §8.7, §9).

Le cas de bout en bout (`test_recipe_prefills_crop_on_a_second_file_of_the_same_dmc_template`)
utilise `botanical-citrus-dmc` puis `cucurbit-dmc` : deux fichiers réels,
même gabarit d'export DMC officiel mais motifs différents (voir
`fixtures/README.md` et `tests/test_fingerprint.py`) — exactement le cas
d'usage du lot, sans avoir à fabriquer une fausse paire de fichiers."""

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
    raise AssertionError(f"détection toujours en cours après {timeout}s pour le job {job_id}")


def _upload(client: TestClient, path: Path) -> dict[str, Any]:
    if not path.is_file():
        pytest.skip(f"fixture manquante : {path}")
    with path.open("rb") as handle:
        response = client.post(
            "/api/imports", files={"file": (path.name, handle, "application/pdf")}
        )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


_SOME_CROP = {"1": {"left": 6.0, "top": 5.0, "right": 4.0, "bottom": 7.0}}


def _tiny_pdf_bytes() -> bytes:
    """Un PDF trivial, sans rapport avec aucune recette DMC — sa propre
    empreinte ne correspond jamais à celle de `BOTANICAL_CITRUS`/`CUCURBIT`,
    utile pour construire un job stabilisé avant d'y substituer un vrai
    fichier (même technique que
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
    """Garde-fou direct de `CLAUDE.md` : une recette ne doit jamais pouvoir
    transporter le contenu créatif d'un motif (dimensions, couleurs)."""
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

    # Le cadrage vient de la recette...
    assert second_job["config"]["crop_by_page"] == _SOME_CROP
    assert second_job["applied_recipe"] == {"id": recipe["id"], "label": "DMC officiel"}
    # ...mais dimensions et palette restent celles, propres, de ce fichier —
    # jamais copiées depuis la recette (contenu créatif, cahier des charges
    # §8.7 : « jamais à partir du contenu créatif »).
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
    """Même principe de test que
    `test_manual_config_started_before_detection_finishes_is_not_overwritten`
    de `test_imports.py` : le minutage réel de la tâche de fond n'est
    garanti ni par le serveur ni par `TestClient`, donc plutôt que de
    deviner une fenêtre de course, ce test construit un job déjà stabilisé
    puis invoque `_run_auto_detection` directement après le cadrage manuel,
    reproduisant l'ordre exact sans dépendre d'aucun minutage."""
    from app.api.imports import _run_auto_detection
    from app.config import get_settings

    first_job = _wait_for_detection(client, _upload(client, BOTANICAL_CITRUS)["id"])
    client.patch(f"/api/imports/{first_job['id']}/config", json={"crop_by_page": _SOME_CROP})
    client.post("/api/recipes", json={"job_id": first_job["id"], "label": "DMC officiel"})

    if not CUCURBIT.is_file():
        pytest.skip(f"fixture manquante : {CUCURBIT}")
    job_id = _upload_tiny_pdf(client)["id"]
    _wait_for_detection(client, job_id)  # PDF trivial, sans empreinte connue : rien à appliquer

    source_path = get_settings().imports_dir / job_id / "source.pdf"
    source_path.write_bytes(CUCURBIT.read_bytes())

    manual_crop = {"1": {"left": 1.0, "top": 1.0, "right": 1.0, "bottom": 1.0}}
    client.patch(f"/api/imports/{job_id}/config", json={"crop_by_page": manual_crop})

    _run_auto_detection(job_id, source_path)

    second_job = client.get(f"/api/imports/{job_id}").json()
    assert second_job["config"]["crop_by_page"] == manual_crop
    assert second_job["applied_recipe"] is None
