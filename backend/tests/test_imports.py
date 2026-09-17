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
    """La détection type A (Lot 4) tourne en tâche de fond
    (`BackgroundTasks`) — ni `TestClient` ni le serveur réel ne garantissent
    qu'elle soit terminée au retour de `POST /api/imports`, donc on sonde
    `GET /api/imports/{id}` jusqu'à ce que `detecting` retombe à faux,
    exactement comme le ferait le client réel."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"/api/imports/{job_id}").json()
        if not job["detecting"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"détection toujours en cours après {timeout}s pour le job {job_id}")


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
    }
    assert job["preview"] is None


def test_create_import_of_trivial_pdf_finishes_detection_with_no_result(
    client: TestClient,
) -> None:
    job = _upload_pdf(client)
    assert job["detecting"] is True  # tâche de fond juste programmée
    job = _wait_for_detection(client, job["id"])
    assert job["detection"] is None


def test_manual_fills_override_detected_cells(client: TestClient) -> None:
    """Une correction peinte à la main doit toujours l'emporter sur la
    grille détectée automatiquement (Lot 4) — sans passer par une vraie
    détection PDF, en posant directement `detected_cells` comme le ferait
    la tâche de fond une fois terminée."""
    job = _upload_pdf(client)
    job_id = job["id"]
    _wait_for_detection(client, job_id)

    detected_cells = [1, 1, 1, 1]  # 2x2, entièrement DMC 310 détecté
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

    # Corrige une case vers la deuxième couleur — le reste doit rester issu
    # de la détection, pas retomber à vide.
    client.patch(
        f"/api/imports/{job_id}/config",
        json={"fills": [{"x0": 0, "y0": 0, "x1": 0, "y1": 0, "palette_index": 2}]},
    )
    corrected = client.post(f"/api/imports/{job_id}/extract").json()
    assert corrected["preview"]["filled_count"] == 4  # toujours 4 cases peintes
    layer = decode_uint16_layer(base64_to_bytes(corrected["preview"]["layer_full"]))
    assert layer[0] == 2  # la correction a pris le dessus
    assert layer[1] == 1  # les autres cases restent la détection d'origine
    assert layer[2] == 1
    assert layer[3] == 1


def test_changing_dimensions_drops_a_now_mismatched_detected_base(client: TestClient) -> None:
    """Bug réel trouvé en test manuel (Lot 4) : si `detected_cells` a été
    posée pour une taille (ici 2x2, comme la tâche de fond le ferait pour de
    vraies dimensions détectées) puis que l'utilisateur change `columns`/
    `rows` sans renvoyer `detected_cells` — exactement ce qu'envoie
    l'assistant en cliquant Continuer avec ses propres dimensions tapées à
    la main — `apply_fills` recevait un `base` de la mauvaise longueur et
    l'API répondait 500 au lieu de simplement repartir d'une grille vide
    pour les nouvelles dimensions."""
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
    assert body["config"]["detected_cells"] is None  # plus de sens pour 3x3
    assert body["preview"]["cell_count"] == 9
    assert body["preview"]["filled_count"] == 0  # repart d'une grille vide, pas d'un plantage


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
    """Bout en bout, fixture réelle (Lot 4) : `POST /api/imports` d'un vrai
    export type A doit ressortir avec la configuration déjà pré-remplie par
    `app/type_a.py`, sans aucune action de l'utilisateur — c'est le critère
    "terminé quand" du roadmap (`docs/roadmap.md`, Lot 4). Plus lent que le
    reste de cette suite (analyse structurelle réelle, ~10s) : c'est
    attendu, voir `tests/test_type_a.py` pour la vérification exhaustive de
    la justesse de l'extraction elle-même — ce test-ci ne vérifie que le
    branchement dans l'API d'import."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)

    assert job["detecting"] is False
    assert job["detection"]["grid_type"] == "A"
    assert job["detection"]["confidence"] > 0.85

    config = job["config"]
    assert config["columns"] == 255
    assert config["rows"] == 180
    # 34 couleurs DMC de la légende « Full Stitches », plus d'éventuelles
    # entrées « Symbole non reconnu » (glyphes de demi/quart-point hors
    # périmètre du Lot 4, voir `app/type_a.py`) — comptées séparément ici,
    # exactement comme `tests/test_type_a.py`.
    dmc_entries = [entry for entry in config["palette"] if entry["code"]]
    assert len(dmc_entries) == 34
    assert config["detected_cells"] is not None
    assert len(config["detected_cells"]) == 255 * 180

    # Le récapitulatif (étape 4 de l'assistant) doit déjà avoir une grille
    # exploitable sans qu'aucune zone n'ait été peinte à la main.
    assert job["preview"] is not None
    assert job["preview"]["filled_count"] > 0


def test_real_type_a_pdf_prefills_real_symbol_images_not_just_letters(
    client: TestClient,
) -> None:
    """Le symbole affiché doit être celui du PDF, pas une lettre synthétique
    (`app.type_a.symbol_key`, jamais destinée qu'à un repli interne) —
    branchement bout en bout de `app.imports_engine.render_symbol_svg`, dont
    la justesse est vérifiée exhaustivement dans `tests/test_type_a.py`."""
    job = _wait_for_detection(client, _upload_real_type_a_pdf(client)["id"], timeout=30.0)

    dmc_entries = [entry for entry in job["config"]["palette"] if entry["code"]]
    assert dmc_entries
    for entry in dmc_entries:
        assert entry["symbol_svg"] is not None
        assert entry["symbol_svg"].startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert "image/png;base64," in entry["symbol_svg"]


def test_symbol_images_survive_commit_into_a_real_pattern(client: TestClient) -> None:
    """Le symbole réel doit rester disponible après validation — le PDF
    source, lui, ne l'est plus (§3 : jamais conservé au-delà de
    l'extraction), donc c'est le seul moment où il est capturable."""
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


def test_manual_config_started_before_detection_finishes_is_not_overwritten(
    client: TestClient,
) -> None:
    """Bug réel trouvé en test manuel (Lot 4) : le message affiché pendant
    l'analyse invite explicitement l'utilisateur à cadrer ou saisir les
    dimensions à la main en attendant (`import.detection.running`). Si la
    tâche de fond termine après coup, elle ne doit pas écraser cette saisie
    en silence — sans quoi le client, qui a cessé d'appliquer les réponses
    du serveur dès qu'il a détecté une modification manuelle
    (`manualEditRef` côté frontend), renvoie ensuite ses propres dimensions
    par-dessus une `detected_cells` désormais incohérente, plantant l'API
    (voir `test_changing_dimensions_drops_a_now_mismatched_detected_base`).

    Le minutage réel de la tâche de fond programmée par `POST /api/imports`
    n'est pas garanti (ni par le serveur réel, ni par `TestClient`) : plutôt
    que de deviner une fenêtre de course, ce test construit un job déjà
    entièrement stabilisé (upload d'un PDF trivial, dont la détection se
    termine quasi instantanément et ne modifie rien), y substitue le vrai
    fichier de référence, corrige la configuration à la main, puis invoque
    `_run_type_a_detection` directement — reproduisant exactement l'ordre
    des opérations du bug sans dépendre d'aucun minutage."""
    from app.api.imports import _run_type_a_detection
    from app.config import get_settings

    if not _TYPE_A_FIXTURE.is_file():
        pytest.skip(f"fixture manquante : {_TYPE_A_FIXTURE}")

    job = _upload_pdf(client)
    job_id = job["id"]
    _wait_for_detection(client, job_id)  # PDF trivial : rien à détecter, config reste vierge

    source_path = get_settings().imports_dir / job_id / "source.pdf"
    source_path.write_bytes(_TYPE_A_FIXTURE.read_bytes())

    # L'utilisateur corrige à la main — l'équivalent de ce qu'il aurait tapé
    # en attendant, s'il avait été plus rapide que l'analyse sur un vrai
    # serveur.
    client.patch(f"/api/imports/{job_id}/config", json={"columns": 92, "rows": 74})

    _run_type_a_detection(job_id, source_path)

    job = client.get(f"/api/imports/{job_id}").json()
    assert "modifiée manuellement" in " ".join(job["detection"]["warnings"])
    config = job["config"]
    assert config["columns"] == 92  # jamais réécrasé par la détection
    assert config["rows"] == 74
    assert config["detected_cells"] is None  # jamais posée par-dessus une saisie déjà en cours
