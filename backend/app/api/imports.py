"""Import wizard — Lot 2 (specification §7.2, §9), automatic detection since
Lots 4-5-7.

The user drops a file, crops and calibrates it themselves, enters their own
palette, and paints each area of the grid by hand — this manual path always
remains available and is never forcibly bypassed (§4.4: "never an imposed
result"). For a PDF, `_run_auto_detection` tries, as a background task,
`app/type_a.py`, then if it recognises nothing `app/type_bc.py`, then as a
last resort `app/type_e.py` (closed catalogue of reused bitmap images,
Lot 7) — the A/B/C/E typology is a classification, never a stack of
competing guesses: a single detection result per file. The result only
pre-fills the same editable configuration: dimensions, palette, and a
background grid that the painted areas can correct
(`app/imports_engine.apply_fills`, `base` parameter).

Since Lot 6, this same background task also applies a known recipe
(`app/api/recipes.py`) when the file's fingerprint (`app/fingerprint.py`)
matches one: only `crop_by_page` is taken from it (never the dimensions or
the palette, which are specific to each pattern — see
`app/models.py::Recipe`).
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
    # content-type -> (extension on disk, "pdf" | "image")
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
    """`config["detected_cells"]` (Lot 4), only if it still matches the
    current dimensions.

    An automatically detected grid is computed for specific dimensions: if
    the user then changes `columns`/`rows` by hand (for example because they
    corrected an imprecise detection, or typed faster than the background
    analysis — see `_run_type_a_detection`), it no longer applies.
    `apply_fills` rejects a `base` of the wrong length rather than silently
    misaligning it; without this guard, the preview crashes instead of simply
    starting again from an empty grid for the new dimensions — an import must
    never end in a dead end (specification §10)."""
    detected = config.get("detected_cells")
    if detected is None or len(detected) != columns * rows:
        return None
    return list(detected)


def _detected_layer(config: dict[str, Any], key: str, columns: int, rows: int) -> list[int] | None:
    """Same guard as `_detected_base`, generalised to the 1/2 and 1/4 layers
    (Lot 9): a layer detected for specific dimensions no longer applies if
    the user has changed `columns`/`rows` since."""
    detected = config.get(key)
    if detected is None or len(detected) != columns * rows:
        return None
    return list(detected)


def _detected_special_items(
    config: dict[str, Any], key: str, palette_size: int
) -> list[dict[str, Any]]:
    """Detected backstitch segments or knots (Lot 9), silently discarding
    those whose palette index no longer refers to anything.

    Detection fixes these indices when it runs; if the user then edits the
    palette by hand (adding/removing a colour, always possible even after a
    successful detection — §4.4, "never an imposed result"), they can become
    stale. Better to silently lose these few elements than to crash the
    validation or write a reference to a colour that no longer exists."""
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


@router.post("", response_model=ImportJobOut, summary="Upload a file, create an import job")
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
    except Exception as error:  # pragma: no cover - corrupt file, defensive path
        shutil.rmtree(job_dir, ignore_errors=True)
        raise api_error(400, "import_file_unreadable") from error

    # A PDF triggers an automatic detection attempt (Lot 4) as a background
    # task — never in the request itself: on the reference fixture
    # (11 pages), structural analysis takes several tens of seconds, far
    # beyond what an HTTP request should wait for (specification §5.2: long
    # tasks via `BackgroundTasks` + status polled by the client, never
    # synchronous). The job remains usable manually (Lot 2) without waiting
    # for this detection, which only pre-fills its configuration once ready
    # (`GET /api/imports/{id}` reflects `detecting: false`).
    will_detect = kind == "pdf"
    result = {
        "page_count": page_count,
        "source_filename": file.filename or f"source.{ext}",
        "source_ext": ext,
        "source_sha256": sha256_file(source_path),
        # Computed in the background task (`_run_auto_detection`), never here
        # — see `app/fingerprint.py` for the real performance bug that
        # motivated this choice, even once the computation itself was made
        # fast.
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
    """`None` if the entry has no known glyph/symbol position, or if cropping
    fails — a missing preview falls back to `symbol_key` when rendering
    (never a broken import for a symbol that could not be illustrated,
    specification §10). Shared by types A (`app/type_a.py`) and B/C
    (`app/type_bc.py`), which use the same position dataclass."""
    if glyph is None:
        return None
    try:
        return render_symbol_svg(source_path, glyph.page_number, glyph.bbox)
    except Exception:  # pragma: no cover - defensive safety net
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
    """1/2 stitches (Lot 9, type A only — B/C/E keep the default value: no
    special stitch detection for them in this lot)."""
    cells_quarter: list[int] = field(default_factory=list)
    backstitch: list[BackstitchSegment] = field(default_factory=list)
    french_knots: list[FrenchKnot] = field(default_factory=list)
    fabric_count: int | None = None
    """Fabric count declared by the PDF, if found (type A only)."""


def _run_auto_detection(job_id: str, source_path: Path) -> None:
    """Background task (Lots 4-5-7): automatic detection, never blocking the
    upload request. Tries `detect_type_a` then, if it recognises nothing,
    `detect_type_bc`, then as a last resort `detect_type_e` (none of the
    three ever raises — see their modules) — a single detection result per
    file (§4.4: a classification, never a stack of competing guesses). A
    safety net here still guarantees that the job always leaves the
    "analysing" state, even in the face of an unforeseen bug: an import that
    stays "in progress" forever would be a dead end (§10: "no import may end
    in a dead end").

    The analysis runs **before** opening the session or reading the job's
    current state: it takes several seconds, plenty of time for the user to
    start configuring the job by hand in the meantime (the message shown
    while waiting explicitly invites them to). Reading `result["config"]`
    before the analysis rather than after would freeze a stale snapshot —
    the "has the user already started?" decision must be made on the freshest
    possible state, just before writing, not on the state from several
    seconds earlier.

    The fingerprint (Lot 6, `app/fingerprint.py`) is computed here rather
    than in `create_import`, never in the upload request — see that module
    for the details of a real performance bug found and fixed at this exact
    spot (a first `pdfplumber`-based implementation took ~14 s on the Cafe
    Brasserie fixture, replaced with PyMuPDF)."""
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
    except Exception as error:  # pragma: no cover - defensive safety net
        detection_error = error

    with get_session_factory()() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status == "committed":
            return  # Job deleted or already validated in the meantime.

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

        # Lot 6: independent of type A/B/C (a recipe helps even a file none
        # of them recognises) — only `crop_by_page` is taken from it, never
        # rewritten if it has already been cropped by hand.
        if fingerprint is not None and not result["config"].get("crop_by_page"):
            recipe = find_matching_recipe(session, fingerprint)
            if recipe is not None:
                recipe_config = json.loads(recipe.config_json)
                result["config"]["crop_by_page"] = recipe_config.get("crop_by_page") or {}
                recipe.usage_count += 1
                result["applied_recipe"] = {"id": recipe.id, "label": recipe.label}

        if detected is not None:
            config = result["config"]
            # If the user has already started filling in the configuration by
            # hand while the analysis was running (dimensions, palette — the
            # message shown while waiting explicitly invites them to, see
            # `import.detection.running` on the frontend), the automatic
            # proposal must not silently overwrite their input: it would
            # arrive after the fact, without them having seen or validated it
            # (§4.4: "never an imposed result").
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
                # Lot 9: special stitches, type A only (B/C/E leave these
                # lists empty — see `_Detected`). No manual correction
                # mechanism for these layers; `or None` to stay consistent
                # with `Grid.layer_half`/`layer_quarter` (`NULL`, not an
                # empty list, when the pattern has none).
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
                # Serialised as plain dictionaries: `result` is stored as is
                # in JSON (`_save_result`), never as a Pydantic model.
                "warnings": [warning.model_dump() for warning in detection_warnings],
            }
        _save_result(job, result)
        session.commit()


@router.get(
    "/{job_id}",
    response_model=ImportJobOut,
    summary="Job status and current configuration",
)
def get_import(job_id: str, session: Annotated[Session, Depends(get_session)]) -> ImportJobOut:
    return _job_out(_get_job(session, job_id))


@router.get(
    "/{job_id}/pages/{page_number}/preview",
    summary="Raster preview of a page",
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
    summary="Update the configuration",
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

    # Only keep a detected grid (and its uncertain-cell flags, which
    # reference the same indices) if it still matches the current dimensions
    # (see `_detected_base`) — not just for reading here, but so as not to
    # carry around indefinitely a blob of several tens of thousands of
    # integers that has become pointless.
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
    summary="Recompute the grid from the current configuration",
)
def extract(job_id: str, session: Annotated[Session, Depends(get_session)]) -> ImportJobOut:
    # Lot 2 has no detection engine: "extracting" here only replays
    # `apply_fills` on the already known configuration. The endpoint exists
    # to honour the API contract (§9) and so the wizard's summary step has a
    # stable call point for when a real engine (Lot 4+) replaces it.
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
    summary="Create the final pattern",
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

    # Fractional and special stitches (Lot 9, type A only): no manual
    # correction mechanism for these layers (unlike `cells`, never an
    # equivalent of `fills`) — they are committed as detected, or absent if
    # detection did not produce them or if the dimensions have changed since
    # (`_detected_layer`).
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

    # Cumulative length (in cells) per palette index, for
    # `backstitch_length_cm` below — never a made-up centimetre if the PDF
    # declares no fabric count (`payload.fabric_count`, entered or corrected
    # by the user at this step, see `ImportCommitRequest`).
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

    # `import_jobs.pattern_id` references `patterns.id`: the pattern (and its
    # dependent rows) must exist in the database before this update runs,
    # otherwise SQLite rejects the foreign key constraint — no ORM
    # `relationship()` links the two tables for SQLAlchemy to infer this
    # order on its own.
    session.flush()

    job.status = "committed"
    job.pattern_id = pattern_id
    job.finished_at = now
    session.commit()

    # The source file never survives extraction (CLAUDE.md): once the
    # pattern is created, the original PDF or photo is no longer needed.
    shutil.rmtree(_job_dir(settings, job_id), ignore_errors=True)

    return ImportCommitResponse(pattern_id=pattern_id)
