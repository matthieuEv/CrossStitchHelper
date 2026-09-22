"""Assistant d'import — Lot 2 (cahier des charges §7.2, §9), détection
automatique depuis les Lots 4-5-7.

L'utilisateur dépose un fichier, le cadre et le calibre lui-même, saisit sa
propre palette, et peint chaque zone de la grille à la main — ce parcours
manuel reste toujours disponible et jamais contourné de force (§4.4 :
« jamais un résultat imposé »). Pour un PDF, `_run_auto_detection` tente en
tâche de fond `app/type_a.py`, puis s'il ne reconnaît rien `app/type_bc.py`,
puis en dernier recours `app/type_e.py` (catalogue fermé d'images bitmap
réutilisées, Lot 7) — la typologie A/B/C/E est une classification, jamais
un empilement de suppositions concurrentes : un seul résultat de détection
par fichier. Le résultat ne fait que pré-remplir la même configuration
modifiable : dimensions, palette, et une grille de fond que les zones
peintes peuvent corriger (`app/imports_engine.apply_fills`, paramètre
`base`).

Depuis le Lot 6, cette même tâche de fond applique aussi une recette
connue (`app/api/recipes.py`) quand l'empreinte du fichier (`app/fingerprint.py`)
en rapproche une : seul `crop_by_page` en est tiré (jamais les dimensions ni
la palette, qui sont propres à chaque motif — voir `app/models.py::Recipe`).
"""

from __future__ import annotations

import json
import math
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.recipes import find_matching_recipe
from app.codec import bytes_to_base64, encode_uint16_layer
from app.codec import empty_bitmap as codec_empty_bitmap
from app.config import Settings, get_settings
from app.db import get_session, get_session_factory
from app.fingerprint import compute_fingerprint
from app.http import api_error
from app.imports_engine import (
    MAX_PREVIEW_DIMENSION,
    PageOutOfRangeError,
    apply_fills,
    pdf_page_count,
    render_image_page,
    render_pdf_page,
    render_symbol_svg,
    sha256_file,
)
from app.models import Grid, ImportJob, PaletteEntry, Pattern, Progress
from app.schemas import (
    BackstitchSegment,
    DetectionWarning,
    FrenchKnot,
    ImportAppliedRecipe,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportConfig,
    ImportConfigPatch,
    ImportDetection,
    ImportJobOut,
    ImportPreview,
)
from app.type_a import SymbolGlyphLocation, TypeAPaletteEntry, detect_type_a
from app.type_bc import TypeBCPaletteEntry, detect_type_bc
from app.type_e import TypeEPaletteEntry, detect_type_e

router = APIRouter(prefix="/imports", tags=["import"])

_ALLOWED_TYPES: dict[str, tuple[str, str]] = {
    # content-type -> (extension sur disque, "pdf" | "image")
    "application/pdf": ("pdf", "pdf"),
    "image/png": ("png", "image"),
    "image/jpeg": ("jpg", "image"),
}


def _job_dir(settings: Settings, job_id: str) -> Path:
    return settings.imports_dir / job_id


def _source_path(settings: Settings, job: ImportJob, result: dict[str, Any]) -> Path:
    return _job_dir(settings, job.id) / f"source.{result['source_ext']}"


def _get_job(session: Session, job_id: str) -> ImportJob:
    job = session.get(ImportJob, job_id)
    if job is None:
        raise api_error(404, "import_not_found")
    return job


def _result_of(job: ImportJob) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(job.result_json)
    return result


def _save_result(job: ImportJob, result: dict[str, Any]) -> None:
    job.result_json = json.dumps(result)


def _detected_base(config: dict[str, Any], columns: int, rows: int) -> list[int] | None:
    """`config["detected_cells"]` (Lot 4), seulement si elle correspond encore
    aux dimensions courantes.

    Une grille détectée automatiquement est calculée pour des dimensions
    précises : si l'utilisateur change ensuite `columns`/`rows` à la main
    (par exemple parce qu'il a corrigé une détection imprécise, ou tapé plus
    vite que l'analyse en tâche de fond — voir `_run_type_a_detection`), elle
    ne s'applique plus. `apply_fills` refuse `base` d'une mauvaise longueur
    plutôt que de mal l'aligner en silence ; sans ce garde-fou, l'aperçu
    plante au lieu de simplement repartir d'une grille vide pour les
    nouvelles dimensions — un import ne doit jamais aboutir à une impasse
    (cahier des charges §10)."""
    detected = config.get("detected_cells")
    if detected is None or len(detected) != columns * rows:
        return None
    return list(detected)


def _detected_layer(config: dict[str, Any], key: str, columns: int, rows: int) -> list[int] | None:
    """Même garde-fou que `_detected_base`, généralisé aux couches 1/2 et
    1/4 (Lot 9) : une couche détectée pour des dimensions précises ne
    s'applique plus si l'utilisateur a changé `columns`/`rows` depuis."""
    detected = config.get(key)
    if detected is None or len(detected) != columns * rows:
        return None
    return list(detected)


def _detected_special_items(
    config: dict[str, Any], key: str, palette_size: int
) -> list[dict[str, Any]]:
    """Segments de point arrière ou nœuds détectés (Lot 9), en écartant
    silencieusement ceux dont l'index de palette ne correspond plus à rien.

    La détection fixe ces index au moment où elle tourne ; si l'utilisateur
    modifie ensuite la palette à la main (ajout/retrait d'une couleur,
    toujours possible même après une détection réussie — §4.4, « jamais un
    résultat imposé »), ils peuvent devenir périmés. Mieux vaut perdre
    silencieusement ces quelques éléments que planter la validation ou
    écrire une référence à une couleur qui n'existe plus."""
    items = config.get(key) or []
    return [item for item in items if 1 <= item.get("palette_index", 0) <= palette_size]


def _compute_preview(config: dict[str, Any]) -> dict[str, Any] | None:
    columns = config.get("columns")
    rows = config.get("rows")
    palette = config.get("palette") or []
    if columns is None or rows is None or not palette:
        return None

    cells = apply_fills(
        columns, rows, config.get("fills") or [], base=_detected_base(config, columns, rows)
    )
    filled_count = sum(1 for value in cells if value != 0)
    return {
        "width": columns,
        "height": rows,
        "cell_count": columns * rows,
        "filled_count": filled_count,
        "layer_full": bytes_to_base64(encode_uint16_layer(cells)),
        "palette": palette,
    }


def _job_out(job: ImportJob) -> ImportJobOut:
    result = _result_of(job)
    return ImportJobOut(
        id=job.id,
        status=job.status,
        kind=job.kind,
        page_count=result["page_count"],
        source_filename=result["source_filename"],
        pattern_id=job.pattern_id,
        config=ImportConfig(**result["config"]),
        preview=ImportPreview(**result["preview"]) if result.get("preview") is not None else None,
        detection=(
            ImportDetection(**result["detection"]) if result.get("detection") is not None else None
        ),
        detecting=bool(result.get("detecting", False)),
        applied_recipe=(
            ImportAppliedRecipe(**result["applied_recipe"])
            if result.get("applied_recipe") is not None
            else None
        ),
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _require_editable(job: ImportJob) -> None:
    if job.status == "committed":
        raise api_error(400, "import_already_committed")


@router.post("", response_model=ImportJobOut, summary="Dépose un fichier, crée un job d'import")
async def create_import(
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile,
) -> ImportJobOut:
    if file.content_type not in _ALLOWED_TYPES:
        raise api_error(400, "import_unsupported_file_type")
    ext, kind = _ALLOWED_TYPES[file.content_type]

    job_id = uuid.uuid4().hex
    job_dir = _job_dir(settings, job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / f"source.{ext}"

    max_bytes = settings.import_max_upload_mb * 1024 * 1024
    written = 0
    with source_path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                handle.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise api_error(400, "import_file_too_large", max_mb=settings.import_max_upload_mb)
            handle.write(chunk)

    try:
        page_count = pdf_page_count(source_path) if kind == "pdf" else 1
    except Exception as error:  # pragma: no cover - fichier corrompu, chemin défensif
        shutil.rmtree(job_dir, ignore_errors=True)
        raise api_error(400, "import_file_unreadable") from error

    # Un PDF déclenche une tentative de détection automatique (Lot 4) en
    # tâche de fond — jamais dans la requête elle-même : sur la fixture de
    # référence (11 pages), l'analyse structurelle prend plusieurs dizaines
    # de secondes, largement au-dessus de ce qu'une requête HTTP doit
    # attendre (cahier des charges §5.2 : tâches longues via
    # `BackgroundTasks` + statut interrogé par le client, jamais
    # synchrone). Le job reste utilisable manuellement (Lot 2) sans attendre
    # cette détection, qui ne fait que pré-remplir sa configuration une fois
    # prête (`GET /api/imports/{id}` reflète `detecting: false`).
    will_detect = kind == "pdf"
    result = {
        "page_count": page_count,
        "source_filename": file.filename or f"source.{ext}",
        "source_ext": ext,
        "source_sha256": sha256_file(source_path),
        # Calculée dans la tâche de fond (`_run_auto_detection`), jamais ici
        # — voir `app/fingerprint.py` pour le bug de performance réel qui a
        # motivé ce choix, même une fois le calcul lui-même rendu rapide.
        "source_fingerprint": None,
        "applied_recipe": None,
        "config": {
            "crop_by_page": {},
            "columns": None,
            "rows": None,
            "palette": [],
            "fills": [],
            "detected_cells": None,
            "uncertain_cells": None,
        },
        "preview": None,
        "detection": None,
        "detecting": will_detect,
    }

    job = ImportJob(
        id=job_id,
        status="ready",
        kind=kind,
        pattern_id=None,
        progress_pct=100,
        result_json=json.dumps(result),
        error=None,
    )
    session.add(job)
    session.commit()

    if will_detect:
        background_tasks.add_task(_run_auto_detection, job_id, source_path)

    return _job_out(job)


def _symbol_svg_for(glyph: SymbolGlyphLocation | None, source_path: Path) -> str | None:
    """`None` si l'entrée n'a pas de position de glyphe/symbole connue, ou si
    le découpage échoue — un aperçu manquant retombe sur `symbol_key` côté
    rendu (jamais un import cassé pour un symbole qu'on n'a pas pu
    illustrer, cahier des charges §10). Commun aux types A (`app/type_a.py`)
    et B/C (`app/type_bc.py`), qui partagent la même dataclass de position."""
    if glyph is None:
        return None
    try:
        return render_symbol_svg(source_path, glyph.page_number, glyph.bbox)
    except Exception:  # pragma: no cover - filet de sécurité défensif
        return None


@dataclass
class _Detected:
    grid_type: Literal["A", "B", "C", "E"]
    columns: int
    rows: int
    cells: list[int]
    palette: list[TypeAPaletteEntry] | list[TypeBCPaletteEntry] | list[TypeEPaletteEntry]
    confidence: float
    warnings: list[DetectionWarning]
    uncertain_cells: list[int]
    cells_half: list[int] = field(default_factory=list)
    """Points 1/2 (Lot 9, type A seulement — B/C/E laissent la valeur par
    défaut : aucune détection de points spéciaux pour eux dans ce lot)."""
    cells_quarter: list[int] = field(default_factory=list)
    backstitch: list[BackstitchSegment] = field(default_factory=list)
    french_knots: list[FrenchKnot] = field(default_factory=list)
    fabric_count: int | None = None
    """Compte de toile déclaré par le PDF, si trouvé (type A seulement)."""


def _run_auto_detection(job_id: str, source_path: Path) -> None:
    """Tâche de fond (Lots 4-5-7) : détection automatique, jamais bloquante
    pour la requête d'upload. Essaie `detect_type_a` puis, s'il ne reconnaît
    rien, `detect_type_bc`, puis en dernier recours `detect_type_e` (aucun
    des trois ne lève jamais — voir leurs modules) — un seul résultat de
    détection par fichier (§4.4 : une classification, jamais un empilement
    de suppositions concurrentes). Un filet de sécurité ici garantit malgré
    tout que le job sort toujours de l'état « en cours d'analyse », même
    face à un bug imprévu : un import qui reste éternellement « en cours »
    serait une impasse (§10 : « aucun import ne doit aboutir à une
    impasse »).

    L'analyse tourne **avant** d'ouvrir la session ou de lire l'état courant
    du job : elle prend plusieurs secondes, largement de quoi laisser
    l'utilisateur commencer à configurer le job à la main pendant ce temps
    (le message affiché pendant l'attente l'y invite explicitement). Lire
    `result["config"]` avant l'analyse plutôt qu'après figerait un
    instantané périmé — la décision « l'utilisateur a-t-il déjà commencé ? »
    doit se prendre sur l'état le plus frais possible, juste avant d'écrire,
    pas sur celui d'il y a plusieurs secondes.

    L'empreinte (Lot 6, `app/fingerprint.py`) est calculée ici plutôt que
    dans `create_import`, jamais dans la requête d'upload — voir le module
    pour le détail d'un bug de performance réel trouvé et corrigé à cet
    endroit précis (une première implémentation à base de `pdfplumber`
    prenait ~14 s sur la fixture Café Brasserie, remplacée par PyMuPDF)."""
    fingerprint = compute_fingerprint(source_path, "pdf")

    detection_error: Exception | None = None
    detected: _Detected | None = None
    try:
        type_a = detect_type_a(source_path)
        if type_a is not None:
            detected = _Detected(
                grid_type="A",
                columns=type_a.columns,
                rows=type_a.rows,
                cells=type_a.cells,
                palette=type_a.palette,
                confidence=type_a.confidence,
                warnings=type_a.warnings,
                uncertain_cells=[],
                cells_half=type_a.cells_half,
                cells_quarter=type_a.cells_quarter,
                backstitch=type_a.backstitch,
                french_knots=type_a.french_knots,
                fabric_count=type_a.fabric_count,
            )
        else:
            type_bc = detect_type_bc(source_path)
            if type_bc is not None:
                detected = _Detected(
                    grid_type=type_bc.grid_type,
                    columns=type_bc.columns,
                    rows=type_bc.rows,
                    cells=type_bc.cells,
                    palette=type_bc.palette,
                    confidence=type_bc.confidence,
                    warnings=type_bc.warnings,
                    uncertain_cells=type_bc.uncertain_cells,
                )
            else:
                type_e = detect_type_e(source_path)
                if type_e is not None:
                    detected = _Detected(
                        grid_type="E",
                        columns=type_e.columns,
                        rows=type_e.rows,
                        cells=type_e.cells,
                        palette=type_e.palette,
                        confidence=type_e.confidence,
                        warnings=type_e.warnings,
                        uncertain_cells=type_e.uncertain_cells,
                    )
    except Exception as error:  # pragma: no cover - filet de sécurité défensif
        detection_error = error

    with get_session_factory()() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status == "committed":
            return  # Job supprimé ou déjà validé entre-temps.

        result = _result_of(job)
        result["source_fingerprint"] = fingerprint

        if detection_error is not None:
            result["detecting"] = False
            result["detection"] = {
                "grid_type": "?",
                "confidence": 0.0,
                "warnings": [
                    DetectionWarning(
                        code="detection.unexpected_failure",
                        params={"error": str(detection_error)},
                    ).model_dump()
                ],
            }
            _save_result(job, result)
            session.commit()
            return

        result["detecting"] = False

        # Lot 6 : indépendant du type A/B/C (une recette aide même un fichier
        # qu'aucun des deux ne reconnaît) — seul `crop_by_page` en est tiré,
        # jamais réécrit s'il a déjà été cadré à la main.
        if fingerprint is not None and not result["config"].get("crop_by_page"):
            recipe = find_matching_recipe(session, fingerprint)
            if recipe is not None:
                recipe_config = json.loads(recipe.config_json)
                result["config"]["crop_by_page"] = recipe_config.get("crop_by_page") or {}
                recipe.usage_count += 1
                result["applied_recipe"] = {"id": recipe.id, "label": recipe.label}

        if detected is not None:
            config = result["config"]
            # Si l'utilisateur a déjà commencé à renseigner la configuration
            # à la main pendant que l'analyse tournait (dimensions, palette —
            # le message affiché pendant l'attente l'invite explicitement à
            # le faire, voir `import.detection.running` côté frontend), la
            # proposition automatique ne doit pas écraser sa saisie en
            # silence : elle arriverait après coup, sans qu'il l'ait vue ni
            # validée (§4.4 : « jamais un résultat imposé »).
            already_configured = (
                config.get("columns") is not None
                or config.get("rows") is not None
                or config.get("palette")
            )
            if not already_configured:
                config["columns"] = detected.columns
                config["rows"] = detected.rows
                config["detected_cells"] = detected.cells
                config["uncertain_cells"] = detected.uncertain_cells or None
                # Lot 9 : points spéciaux, type A seulement (B/C/E laissent
                # ces listes vides — voir `_Detected`). Aucun mécanisme de
                # correction manuelle pour ces couches ; `or None` pour
                # rester cohérent avec `Grid.layer_half`/`layer_quarter`
                # (`NULL`, pas une liste vide, quand le motif n'en a aucun).
                config["detected_half"] = detected.cells_half or None
                config["detected_quarter"] = detected.cells_quarter or None
                config["detected_backstitch"] = [
                    segment.model_dump() for segment in detected.backstitch
                ] or None
                config["detected_french_knots"] = [
                    knot.model_dump() for knot in detected.french_knots
                ] or None
                config["detected_fabric_count"] = detected.fabric_count
                config["palette"] = [
                    {
                        "code": entry.code,
                        "name": entry.name,
                        "rgb_hex": entry.rgb_hex,
                        "symbol_key": entry.symbol_key,
                        "symbol_svg": _symbol_svg_for(entry.symbol_glyph, source_path),
                    }
                    for entry in detected.palette
                ]
                result["preview"] = _compute_preview(config)
            detection_warnings = list(detected.warnings)
            if already_configured:
                detection_warnings.append(DetectionWarning(code="detection.manual_config_kept"))
            result["detection"] = {
                "grid_type": detected.grid_type,
                "confidence": detected.confidence,
                # Sérialisé en dictionnaires simples : `result` est stocké tel
                # quel en JSON (`_save_result`), jamais un modèle Pydantic.
                "warnings": [warning.model_dump() for warning in detection_warnings],
            }
        _save_result(job, result)
        session.commit()


@router.get(
    "/{job_id}",
    response_model=ImportJobOut,
    summary="État du job et configuration courante",
)
def get_import(job_id: str, session: Annotated[Session, Depends(get_session)]) -> ImportJobOut:
    return _job_out(_get_job(session, job_id))


@router.get(
    "/{job_id}/pages/{page_number}/preview",
    summary="Aperçu raster d'une page",
    response_class=Response,
)
def get_page_preview(
    job_id: str,
    page_number: int,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    max_dimension: Annotated[int, Query(ge=200, le=MAX_PREVIEW_DIMENSION)] = MAX_PREVIEW_DIMENSION,
) -> Response:
    job = _get_job(session, job_id)
    result = _result_of(job)
    source_path = _source_path(settings, job, result)
    if not source_path.is_file():
        raise api_error(404, "import_source_missing")

    if job.kind == "pdf":
        try:
            png_bytes = render_pdf_page(source_path, page_number, max_dimension)
        except PageOutOfRangeError as error:
            raise api_error(
                404, "import_page_out_of_range", page=error.page_number, count=error.page_count
            ) from error
    else:
        if page_number != 1:
            raise api_error(404, "import_photo_single_page")
        png_bytes = render_image_page(source_path, max_dimension)

    return Response(
        content=png_bytes, media_type="image/png", headers={"Cache-Control": "no-cache"}
    )


@router.patch(
    "/{job_id}/config",
    response_model=ImportJobOut,
    summary="Met à jour la configuration",
)
def patch_config(
    job_id: str,
    payload: ImportConfigPatch,
    session: Annotated[Session, Depends(get_session)],
) -> ImportJobOut:
    job = _get_job(session, job_id)
    _require_editable(job)
    result = _result_of(job)
    config = result["config"]

    if payload.crop_by_page is not None:
        config["crop_by_page"] = {
            page: crop.model_dump() for page, crop in payload.crop_by_page.items()
        }
    if payload.columns is not None:
        config["columns"] = payload.columns
    if payload.rows is not None:
        config["rows"] = payload.rows
    if payload.palette is not None:
        config["palette"] = [entry.model_dump() for entry in payload.palette]
    if payload.fills is not None:
        config["fills"] = [fill.model_dump() for fill in payload.fills]
    if payload.detected_cells is not None:
        config["detected_cells"] = payload.detected_cells
    if payload.uncertain_cells is not None:
        config["uncertain_cells"] = payload.uncertain_cells

    # Ne garde une grille détectée (et son signalement de cases incertaines,
    # qui référence les mêmes index) que si elle correspond encore aux
    # dimensions courantes (voir `_detected_base`) — pas seulement pour la
    # lecture ici, mais pour ne pas trimballer indéfiniment un blob de
    # plusieurs dizaines de milliers d'entiers devenu sans objet.
    columns, rows = config.get("columns"), config.get("rows")
    if columns is not None and rows is not None and _detected_base(config, columns, rows) is None:
        config["detected_cells"] = None
        config["uncertain_cells"] = None

    result["preview"] = _compute_preview(config)
    _save_result(job, result)
    session.commit()
    return _job_out(job)


@router.post(
    "/{job_id}/extract",
    response_model=ImportJobOut,
    summary="Recalcule la grille depuis la configuration courante",
)
def extract(job_id: str, session: Annotated[Session, Depends(get_session)]) -> ImportJobOut:
    # Le Lot 2 n'a aucun moteur de détection : « extraire » ne fait ici que
    # rejouer `apply_fills` sur la configuration déjà connue. L'endpoint
    # existe pour respecter le contrat d'API (§9) et pour que l'étape
    # récapitulative de l'assistant ait un point d'appel stable quand un
    # vrai moteur (Lot 4+) viendra le remplacer.
    job = _get_job(session, job_id)
    _require_editable(job)
    result = _result_of(job)
    result["preview"] = _compute_preview(result["config"])
    _save_result(job, result)
    session.commit()
    return _job_out(job)


@router.post(
    "/{job_id}/commit",
    response_model=ImportCommitResponse,
    summary="Crée le motif définitif",
)
def commit(
    job_id: str,
    payload: ImportCommitRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportCommitResponse:
    job = _get_job(session, job_id)
    _require_editable(job)
    result = _result_of(job)
    preview = _compute_preview(result["config"])
    if preview is None:
        raise api_error(400, "import_config_incomplete")

    now = datetime.now(UTC)
    pattern_id = uuid.uuid4().hex
    columns, rows = preview["width"], preview["height"]
    cells = apply_fills(
        columns,
        rows,
        result["config"].get("fills") or [],
        base=_detected_base(result["config"], columns, rows),
    )

    # Points fractionnés et spéciaux (Lot 9, type A seulement) : aucun
    # mécanisme de correction manuelle pour ces couches (contrairement à
    # `cells`, jamais de `fills` équivalent) — elles sont commitées telles
    # que détectées, ou absentes si la détection ne les a pas produites ou
    # si les dimensions ont changé depuis (`_detected_layer`).
    config = result["config"]
    cells_half = _detected_layer(config, "detected_half", columns, rows)
    cells_quarter = _detected_layer(config, "detected_quarter", columns, rows)
    palette_size = len(config["palette"])
    backstitch = _detected_special_items(config, "detected_backstitch", palette_size)
    french_knots = _detected_special_items(config, "detected_french_knots", palette_size)

    pattern = Pattern(
        id=pattern_id,
        owner_id=None,
        name=payload.name,
        source_filename=result["source_filename"],
        source_sha256=result["source_sha256"],
        width=columns,
        height=rows,
        fabric_count=payload.fabric_count,
        created_at=now,
        updated_at=now,
        import_config_json=json.dumps(result["config"]),
        recipe_id=(result.get("applied_recipe") or {}).get("id"),
        notes=None,
    )
    session.add(pattern)

    # Longueur cumulée (en cases) par index de palette, pour
    # `backstitch_length_cm` ci-dessous — jamais un centimètre inventé si le
    # PDF ne déclare pas de compte de toile (`payload.fabric_count`, saisi ou
    # corrigé par l'utilisateur à cette étape, voir `ImportCommitRequest`).
    backstitch_length_by_index: dict[int, float] = {}
    for segment in backstitch:
        length = math.hypot(segment["x2"] - segment["x1"], segment["y2"] - segment["y1"])
        index = segment["palette_index"]
        backstitch_length_by_index[index] = backstitch_length_by_index.get(index, 0.0) + length

    for position, entry in enumerate(result["config"]["palette"]):
        index_in_grid = position + 1
        length_cells = backstitch_length_by_index.get(index_in_grid)
        session.add(
            PaletteEntry(
                id=uuid.uuid4().hex,
                pattern_id=pattern_id,
                index_in_grid=index_in_grid,
                brand="DMC",
                code=entry["code"],
                name=entry["name"],
                rgb_hex=entry["rgb_hex"],
                symbol_key=entry["symbol_key"],
                symbol_svg=entry.get("symbol_svg"),
                strands_full=2,
                strands_back=1,
                count_full=sum(1 for value in cells if value == index_in_grid),
                count_half=sum(1 for value in cells_half or () if value == index_in_grid),
                count_quarter=sum(1 for value in cells_quarter or () if value == index_in_grid),
                count_french=sum(
                    1 for knot in french_knots if knot["palette_index"] == index_in_grid
                ),
                count_beads=0,
                backstitch_length_cm=(
                    length_cells * 2.54 / payload.fabric_count
                    if length_cells and payload.fabric_count
                    else None
                ),
            )
        )

    session.add(
        Grid(
            pattern_id=pattern_id,
            layer_full=encode_uint16_layer(cells),
            layer_half=encode_uint16_layer(cells_half) if cells_half else None,
            layer_quarter=encode_uint16_layer(cells_quarter) if cells_quarter else None,
            backstitch_json=json.dumps(backstitch),
            french_knots_json=json.dumps(french_knots),
            encoding="uint16le",
            version=1,
        )
    )
    session.add(
        Progress(
            pattern_id=pattern_id,
            bitmap=codec_empty_bitmap(columns * rows),
            version=1,
            stitched_count=0,
            updated_at=now,
        )
    )

    # `import_jobs.pattern_id` référence `patterns.id` : le motif (et ses
    # lignes dépendantes) doit exister en base avant que cette mise à jour ne
    # soit exécutée, sans quoi SQLite refuse la contrainte de clé étrangère —
    # aucune `relationship()` ORM ne relie les deux tables pour que
    # SQLAlchemy déduise cet ordre tout seul.
    session.flush()

    job.status = "committed"
    job.pattern_id = pattern_id
    job.finished_at = now
    session.commit()

    # Le fichier source ne survit jamais à l'extraction (CLAUDE.md) : une
    # fois le motif créé, plus besoin du PDF ou de la photo d'origine.
    shutil.rmtree(_job_dir(settings, job_id), ignore_errors=True)

    return ImportCommitResponse(pattern_id=pattern_id)
