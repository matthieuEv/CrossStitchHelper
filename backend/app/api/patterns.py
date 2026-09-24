"""Pattern persistence routes (specification §9, Lots 1 and 2).

Patterns reach the database either through the seed script (`app/seed.py`)
or through the import wizard (`app/api/imports.py`, Lot 2); this module
covers what applies once a pattern exists, whatever its origin: reading,
progress synchronisation, and `.cshp` export.
"""

from __future__ import annotations

import json
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.activity import compute_activity
from app.codec import (
    bitmap_byte_length,
    bytes_to_base64,
    count_set_bits,
    decode_uint16_layer,
    set_bit,
)
from app.db import get_session
from app.export_cshp import build_cshp_archive
from app.http import api_error, content_disposition
from app.models import Pattern, Progress, ProgressEvent
from app.schemas import (
    GridOut,
    PaletteEntryOut,
    PatternActivityOut,
    PatternDetail,
    PatternSummary,
    ProgressOp,
    ProgressOut,
    ProgressSyncRequest,
    ProgressSyncResponse,
)

router = APIRouter(prefix="/patterns", tags=["patterns"])

# Maximum number of events replayed in a single sync response. Beyond that, a
# device that stayed offline for a very long time will have to make several
# round trips rather than receive an arbitrarily large response.
MAX_REPLAYED_EVENTS = 2000


def _get_pattern(session: Session, pattern_id: str) -> Pattern:
    pattern = session.get(Pattern, pattern_id)
    if pattern is None:
        raise api_error(404, "pattern_not_found")
    return pattern


def _non_empty_cell_count(pattern: Pattern) -> int:
    if pattern.grid is None:
        return 0
    return sum(1 for value in decode_uint16_layer(pattern.grid.layer_full) if value != 0)


@router.get("", response_model=list[PatternSummary], summary="List of patterns")
def list_patterns(session: Annotated[Session, Depends(get_session)]) -> list[PatternSummary]:
    patterns = (
        session.execute(
            select(Pattern).options(
                selectinload(Pattern.grid),
                selectinload(Pattern.progress),
                selectinload(Pattern.palette_entries),
            )
        )
        .scalars()
        .all()
    )

    summaries: list[PatternSummary] = []
    for pattern in patterns:
        cell_count = _non_empty_cell_count(pattern)
        stitched_count = pattern.progress.stitched_count if pattern.progress is not None else 0
        percent = round(stitched_count / cell_count * 100) if cell_count else 0
        summaries.append(
            PatternSummary(
                id=pattern.id,
                name=pattern.name,
                width=pattern.width,
                height=pattern.height,
                palette_count=len(pattern.palette_entries),
                stitched_count=stitched_count,
                cell_count=cell_count,
                percent=percent,
                created_at=pattern.created_at,
                updated_at=pattern.updated_at,
            )
        )
    return summaries


@router.get("/{pattern_id}", response_model=PatternDetail, summary="Metadata and palette")
def get_pattern(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> PatternDetail:
    pattern = _get_pattern(session, pattern_id)
    return PatternDetail(
        id=pattern.id,
        owner_id=pattern.owner_id,
        name=pattern.name,
        source_filename=pattern.source_filename,
        fabric_count=pattern.fabric_count,
        width=pattern.width,
        height=pattern.height,
        notes=pattern.notes,
        created_at=pattern.created_at,
        updated_at=pattern.updated_at,
        palette=[PaletteEntryOut.model_validate(entry) for entry in pattern.palette_entries],
    )


@router.get("/{pattern_id}/grid", response_model=GridOut, summary="Grid layers")
def get_grid(pattern_id: str, session: Annotated[Session, Depends(get_session)]) -> GridOut:
    pattern = _get_pattern(session, pattern_id)
    grid = pattern.grid
    if grid is None:
        raise api_error(404, "pattern_grid_not_found")

    return GridOut(
        pattern_id=pattern.id,
        width=pattern.width,
        height=pattern.height,
        encoding=grid.encoding,
        version=grid.version,
        layer_full=bytes_to_base64(grid.layer_full),
        layer_half=bytes_to_base64(grid.layer_half) if grid.layer_half is not None else None,
        layer_quarter=bytes_to_base64(grid.layer_quarter)
        if grid.layer_quarter is not None
        else None,
        backstitch=json.loads(grid.backstitch_json),
        french_knots=json.loads(grid.french_knots_json),
    )


def _progress_out(pattern: Pattern, progress: Progress) -> ProgressOut:
    return ProgressOut(
        pattern_id=pattern.id,
        version=progress.version,
        stitched_count=progress.stitched_count,
        cell_count=pattern.width * pattern.height,
        bitmap=bytes_to_base64(progress.bitmap),
        bitmap_half=bytes_to_base64(progress.bitmap_half)
        if progress.bitmap_half is not None
        else None,
        bitmap_quarter=bytes_to_base64(progress.bitmap_quarter)
        if progress.bitmap_quarter is not None
        else None,
        bitmap_backstitch=bytes_to_base64(progress.bitmap_backstitch)
        if progress.bitmap_backstitch is not None
        else None,
        bitmap_knots=bytes_to_base64(progress.bitmap_knots)
        if progress.bitmap_knots is not None
        else None,
        stitched_count_half=count_set_bits(progress.bitmap_half or b""),
        stitched_count_quarter=count_set_bits(progress.bitmap_quarter or b""),
        stitched_count_backstitch=count_set_bits(progress.bitmap_backstitch or b""),
        stitched_count_knots=count_set_bits(progress.bitmap_knots or b""),
    )


@router.get(
    "/{pattern_id}/progress", response_model=ProgressOut, summary="Progress bitmap"
)
def get_progress(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> ProgressOut:
    pattern = _get_pattern(session, pattern_id)
    if pattern.progress is None:
        raise api_error(404, "pattern_progress_not_found")
    return _progress_out(pattern, pattern.progress)


def _events_since(session: Session, pattern_id: str, version: int) -> list[ProgressOp]:
    events = (
        session.execute(
            select(ProgressEvent)
            .where(ProgressEvent.pattern_id == pattern_id, ProgressEvent.version_after > version)
            .order_by(ProgressEvent.version_after)
            .limit(MAX_REPLAYED_EVENTS)
        )
        .scalars()
        .all()
    )
    ops: list[ProgressOp] = []
    for event in events:
        ops.extend(ProgressOp.model_validate(op) for op in json.loads(event.ops_json))
    return ops


_LAYER_ATTR = {
    "full": "bitmap",
    "half": "bitmap_half",
    "quarter": "bitmap_quarter",
    "backstitch": "bitmap_backstitch",
    "knot": "bitmap_knots",
}


def _layer_bound(pattern: Pattern, layer: str) -> int:
    """Number of addressable elements in this category — 0 if the pattern
    has none (`Grid.layer_half`/`layer_quarter` absent, or empty
    `backstitch_json`/`french_knots_json` list), which naturally rejects any
    `index` (always >= 0) through the same check as the other categories,
    with no special case to write."""
    if layer in ("full", "half", "quarter"):
        return pattern.width * pattern.height
    assert pattern.grid is not None  # guaranteed by the caller, see sync_progress
    field = "backstitch_json" if layer == "backstitch" else "french_knots_json"
    return len(json.loads(getattr(pattern.grid, field)))


@router.post(
    "/{pattern_id}/progress",
    response_model=ProgressSyncResponse,
    summary="Apply a batch of progress changes",
)
def sync_progress(
    pattern_id: str,
    payload: ProgressSyncRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ProgressSyncResponse:
    """Versioned-delta synchronisation (specification §9).

    Checking a cell is an idempotent operation: the operations sent are
    therefore always applied, whether "late" or not, then the client is told
    about the changes made by other devices since its last known version, so
    it can replay them locally.

    Since Lot 8, `ProgressOp.layer` distinguishes up to five stitch
    categories (full stitch, 1/2, 1/4, backstitch, knot), each with its own
    bitmap (`Progress.bitmap*`) and its own index space — never shared
    between categories, so the wrong element is never checked through a
    layer mix-up (see `app/models.py::Progress`).
    """
    pattern = _get_pattern(session, pattern_id)
    progress = pattern.progress
    if progress is None:
        raise api_error(404, "pattern_progress_not_found")
    if pattern.grid is None:
        raise api_error(404, "pattern_grid_not_found")

    bounds = {layer: _layer_bound(pattern, layer) for layer in _LAYER_ATTR}
    for op in payload.ops:
        bound = bounds[op.layer]
        if op.index >= bound:
            raise api_error(
                400,
                "pattern_progress_index_out_of_range",
                layer=op.layer,
                index=op.index,
                bound=bound,
            )

    # Computed before writing: events already known to the client must not
    # be sent back to it, only those made by other devices since its last
    # sync count.
    missing_ops = _events_since(session, pattern_id, payload.base_version)
    conflict = len(missing_ops) > 0

    if payload.ops:
        ops_by_layer: dict[str, list[ProgressOp]] = {}
        for op in payload.ops:
            ops_by_layer.setdefault(op.layer, []).append(op)

        for layer, ops in ops_by_layer.items():
            attr = _LAYER_ATTR[layer]
            current: bytes | None = getattr(progress, attr)
            bitmap = (
                bytearray(current)
                if current is not None
                else bytearray(bitmap_byte_length(bounds[layer]))
            )
            for op in ops:
                set_bit(bitmap, op.index, op.stitched)
            setattr(progress, attr, bytes(bitmap))

        new_version = progress.version + 1
        progress.version = new_version
        progress.stitched_count = count_set_bits(progress.bitmap)

        session.add(
            ProgressEvent(
                pattern_id=pattern_id,
                ops_json=json.dumps([op.model_dump() for op in payload.ops]),
                version_after=new_version,
            )
        )
        session.commit()
    else:
        new_version = progress.version

    return ProgressSyncResponse(
        version=new_version,
        stitched_count=progress.stitched_count,
        conflict=conflict,
        missing_ops=missing_ops,
    )


@router.get(
    "/{pattern_id}/activity",
    response_model=PatternActivityOut,
    summary="Activity history derived from progress events",
)
def get_activity(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> PatternActivityOut:
    _get_pattern(session, pattern_id)  # 404 if the pattern does not exist.
    events = (
        session.execute(
            select(ProgressEvent)
            .where(ProgressEvent.pattern_id == pattern_id)
            .order_by(ProgressEvent.ts)
        )
        .scalars()
        .all()
    )
    # SQLite does not keep the time zone in storage: `event.ts` comes back
    # naive even though the column is `DateTime(timezone=True)` and always
    # written in UTC (`_utcnow`, `app/models.py`) — without this explicit
    # re-attachment, comparing with `datetime.now(UTC)` raises a `TypeError`.
    parsed = [
        (
            event.ts if event.ts.tzinfo is not None else event.ts.replace(tzinfo=UTC),
            json.loads(event.ops_json),
        )
        for event in events
    ]
    return compute_activity(parsed)


@router.get(
    "/{pattern_id}/export",
    summary=".cshp export (open format)",
    response_class=Response,
)
def export_pattern(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> Response:
    pattern = _get_pattern(session, pattern_id)
    if pattern.grid is None or pattern.progress is None:
        raise api_error(404, "pattern_grid_or_progress_not_found")

    archive = build_cshp_archive(pattern, pattern.palette_entries, pattern.grid, pattern.progress)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"{pattern.name}.cshp")},
    )
