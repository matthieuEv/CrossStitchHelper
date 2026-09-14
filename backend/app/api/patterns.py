"""Routes de persistance des motifs (cahier des charges §9, Lot 1).

Le Lot 2 (assistant d'import) n'existe pas encore : il n'y a donc pas de
route pour créer un motif depuis un PDF. Pour l'instant, les motifs
n'arrivent en base que par un script de seed (voir `app/seed.py`) — la
persistance et la synchronisation de la progression sont ce que ce module
apporte.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.codec import bytes_to_base64, count_set_bits, decode_uint16_layer
from app.db import get_session
from app.models import Pattern, Progress, ProgressEvent
from app.schemas import (
    GridOut,
    PaletteEntryOut,
    PatternDetail,
    PatternSummary,
    ProgressOp,
    ProgressOut,
    ProgressSyncRequest,
    ProgressSyncResponse,
)

router = APIRouter(prefix="/patterns", tags=["motifs"])

# Nombre maximal d'événements rejoués en une seule réponse de synchronisation.
# Au-delà, un appareil resté hors-ligne très longtemps devra faire plusieurs
# allers-retours plutôt que de recevoir une réponse arbitrairement grosse.
MAX_REPLAYED_EVENTS = 2000


def _get_pattern(session: Session, pattern_id: str) -> Pattern:
    pattern = session.get(Pattern, pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Motif introuvable")
    return pattern


def _non_empty_cell_count(pattern: Pattern) -> int:
    if pattern.grid is None:
        return 0
    return sum(1 for value in decode_uint16_layer(pattern.grid.layer_full) if value != 0)


@router.get("", response_model=list[PatternSummary], summary="Liste des motifs")
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


@router.get("/{pattern_id}", response_model=PatternDetail, summary="Métadonnées et palette")
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


@router.get("/{pattern_id}/grid", response_model=GridOut, summary="Couches de grille")
def get_grid(pattern_id: str, session: Annotated[Session, Depends(get_session)]) -> GridOut:
    pattern = _get_pattern(session, pattern_id)
    grid = pattern.grid
    if grid is None:
        raise HTTPException(status_code=404, detail="Grille introuvable pour ce motif")

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
    )


@router.get(
    "/{pattern_id}/progress", response_model=ProgressOut, summary="Bitmap de progression"
)
def get_progress(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> ProgressOut:
    pattern = _get_pattern(session, pattern_id)
    if pattern.progress is None:
        raise HTTPException(status_code=404, detail="Progression introuvable pour ce motif")
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


@router.post(
    "/{pattern_id}/progress",
    response_model=ProgressSyncResponse,
    summary="Application d'un lot de modifications de progression",
)
def sync_progress(
    pattern_id: str,
    payload: ProgressSyncRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ProgressSyncResponse:
    """Synchronisation par deltas versionnés (cahier des charges §9).

    Cocher une case est une opération idempotente : on applique donc toujours
    les opérations envoyées, qu'elles soient « en retard » ou non, puis on
    signale au client les changements faits par d'autres appareils depuis sa
    dernière version connue, pour qu'il les rejoue localement.
    """
    pattern = _get_pattern(session, pattern_id)
    progress = pattern.progress
    if progress is None:
        raise HTTPException(status_code=404, detail="Progression introuvable pour ce motif")

    cell_count = pattern.width * pattern.height
    for op in payload.ops:
        if op.index >= cell_count:
            raise HTTPException(
                status_code=400, detail=f"Index hors grille : {op.index} >= {cell_count}"
            )

    # Calculé avant l'écriture : les événements déjà connus du client ne
    # doivent pas lui être renvoyés, seuls ceux faits par d'autres appareils
    # depuis sa dernière synchronisation comptent.
    missing_ops = _events_since(session, pattern_id, payload.base_version)
    conflict = len(missing_ops) > 0

    if payload.ops:
        bitmap = bytearray(progress.bitmap)
        for op in payload.ops:
            byte_index, bit_index = divmod(op.index, 8)
            if op.stitched:
                bitmap[byte_index] |= 1 << bit_index
            else:
                bitmap[byte_index] &= ~(1 << bit_index) & 0xFF

        new_version = progress.version + 1
        progress.bitmap = bytes(bitmap)
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
