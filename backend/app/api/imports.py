"""Assistant d'import — Lot 2 (cahier des charges §7.2, §9), détection
automatique depuis le Lot 4.

L'utilisateur dépose un fichier, le cadre et le calibre lui-même, saisit sa
propre palette, et peint chaque zone de la grille à la main — ce parcours
manuel reste toujours disponible et jamais contourné de force (§4.4 :
« jamais un résultat imposé »). Pour un PDF, `app/type_a.py` tente en tâche
de fond une détection automatique dont le résultat ne fait que pré-remplir
la même configuration modifiable : dimensions, palette, et une grille de
fond que les zones peintes peuvent corriger (`app/imports_engine.apply_fills`,
paramètre `base`).
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.codec import bytes_to_base64, encode_uint16_layer
from app.codec import empty_bitmap as codec_empty_bitmap
from app.config import Settings, get_settings
from app.db import get_session, get_session_factory
from app.imports_engine import (
    MAX_PREVIEW_DIMENSION,
    apply_fills,
    pdf_page_count,
    render_image_page,
    render_pdf_page,
    sha256_file,
)
from app.models import Grid, ImportJob, PaletteEntry, Pattern, Progress
from app.schemas import (
    ImportCommitRequest,
    ImportCommitResponse,
    ImportConfig,
    ImportConfigPatch,
    ImportDetection,
    ImportJobOut,
    ImportPreview,
)
from app.type_a import detect_type_a

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
        raise HTTPException(status_code=404, detail="Import introuvable")
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
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _require_editable(job: ImportJob) -> None:
    if job.status == "committed":
        raise HTTPException(
            status_code=400, detail="Cet import a déjà été validé et ne peut plus être modifié"
        )


@router.post("", response_model=ImportJobOut, summary="Dépose un fichier, crée un job d'import")
async def create_import(
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile,
) -> ImportJobOut:
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Format non pris en charge : seuls PDF, PNG et JPEG le sont",
        )
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
                raise HTTPException(
                    status_code=400,
                    detail=f"Fichier trop volumineux (> {settings.import_max_upload_mb} Mo)",
                )
            handle.write(chunk)

    try:
        page_count = pdf_page_count(source_path) if kind == "pdf" else 1
    except Exception as error:  # pragma: no cover - fichier corrompu, chemin défensif
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Fichier illisible") from error

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
        "config": {
            "crop": None,
            "columns": None,
            "rows": None,
            "palette": [],
            "fills": [],
            "detected_cells": None,
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
        background_tasks.add_task(_run_type_a_detection, job_id, source_path)

    return _job_out(job)


def _run_type_a_detection(job_id: str, source_path: Path) -> None:
    """Tâche de fond (Lot 4) : détection automatique, jamais bloquante pour
    la requête d'upload. `detect_type_a` ne lève jamais (voir `app/type_a.py`)
    mais un filet de sécurité ici garantit que le job sort toujours de l'état
    « en cours d'analyse », même face à un bug imprévu — un import qui reste
    éternellement « en cours » serait une impasse (§10 : « aucun import ne
    doit aboutir à une impasse »).

    L'analyse (`detect_type_a`) tourne **avant** d'ouvrir la session ou de
    lire l'état courant du job : elle prend plusieurs secondes, largement de
    quoi laisser l'utilisateur commencer à configurer le job à la main
    pendant ce temps (le message affiché pendant l'attente l'y invite
    explicitement). Lire `result["config"]` avant l'analyse plutôt qu'après
    figerait un instantané périmé — la décision « l'utilisateur a-t-il déjà
    commencé ? » doit se prendre sur l'état le plus frais possible, juste
    avant d'écrire, pas sur celui d'il y a plusieurs secondes."""
    detection_error: Exception | None = None
    try:
        detected = detect_type_a(source_path)
    except Exception as error:  # pragma: no cover - filet de sécurité défensif
        detected = None
        detection_error = error

    with get_session_factory()() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status == "committed":
            return  # Job supprimé ou déjà validé entre-temps.

        result = _result_of(job)

        if detection_error is not None:
            result["detecting"] = False
            result["detection"] = {
                "grid_type": "A",
                "confidence": 0.0,
                "warnings": [f"Échec inattendu de la détection automatique : {detection_error}"],
            }
            _save_result(job, result)
            session.commit()
            return

        result["detecting"] = False
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
                config["palette"] = [
                    {
                        "code": entry.code,
                        "name": entry.name,
                        "rgb_hex": entry.rgb_hex,
                        "symbol_key": entry.symbol_key,
                    }
                    for entry in detected.palette
                ]
                result["preview"] = _compute_preview(config)
            result["detection"] = {
                "grid_type": "A",
                "confidence": detected.confidence,
                "warnings": detected.warnings
                if not already_configured
                else [
                    *detected.warnings,
                    "Configuration déjà modifiée manuellement avant la fin de "
                    "l'analyse : la proposition automatique n'a pas été appliquée.",
                ],
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
        raise HTTPException(
            status_code=404, detail="Fichier source introuvable (import déjà validé ?)"
        )

    if job.kind == "pdf":
        try:
            png_bytes = render_pdf_page(source_path, page_number, max_dimension)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    else:
        if page_number != 1:
            raise HTTPException(status_code=404, detail="Une photo n'a qu'une seule page")
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

    if payload.crop is not None:
        config["crop"] = payload.crop.model_dump()
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

    # Ne garde une grille détectée que si elle correspond encore aux
    # dimensions courantes (voir `_detected_base`) — pas seulement pour la
    # lecture ici, mais pour ne pas trimballer indéfiniment un blob de
    # plusieurs dizaines de milliers d'entiers devenu sans objet.
    columns, rows = config.get("columns"), config.get("rows")
    if columns is not None and rows is not None and _detected_base(config, columns, rows) is None:
        config["detected_cells"] = None

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
        raise HTTPException(
            status_code=400,
            detail="Configuration incomplète : dimensions et palette sont requises",
        )

    now = datetime.now(UTC)
    pattern_id = uuid.uuid4().hex
    columns, rows = preview["width"], preview["height"]
    cells = apply_fills(
        columns,
        rows,
        result["config"].get("fills") or [],
        base=_detected_base(result["config"], columns, rows),
    )

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
        recipe_id=None,
        notes=None,
    )
    session.add(pattern)

    for position, entry in enumerate(result["config"]["palette"]):
        index_in_grid = position + 1
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
                symbol_svg=None,
                strands_full=2,
                strands_back=1,
                count_full=sum(1 for value in cells if value == index_in_grid),
                count_half=0,
                count_quarter=0,
                count_french=0,
                count_beads=0,
                backstitch_length_cm=None,
            )
        )

    session.add(
        Grid(
            pattern_id=pattern_id,
            layer_full=encode_uint16_layer(cells),
            layer_half=None,
            layer_quarter=None,
            backstitch_json="[]",
            french_knots_json="[]",
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
