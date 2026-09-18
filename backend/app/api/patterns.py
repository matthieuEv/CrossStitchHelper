"""Routes de persistance des motifs (cahier des charges §9, Lot 1 et 2).

Les motifs arrivent en base soit par le script de seed (`app/seed.py`), soit
par l'assistant d'import (`app/api/imports.py`, Lot 2) ; ce module couvre ce
qui s'applique une fois qu'un motif existe, quelle que soit son origine :
lecture, synchronisation de la progression, et export `.cshp`.
"""

from __future__ import annotations

import json
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
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
from app.http import content_disposition
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


_LAYER_ATTR = {
    "full": "bitmap",
    "half": "bitmap_half",
    "quarter": "bitmap_quarter",
    "backstitch": "bitmap_backstitch",
    "knot": "bitmap_knots",
}


def _layer_bound(pattern: Pattern, layer: str) -> int:
    """Nombre d'éléments adressables dans cette catégorie — 0 si le motif
    n'en a aucun (`Grid.layer_half`/`layer_quarter` absent, ou liste
    `backstitch_json`/`french_knots_json` vide), ce qui rejette naturellement
    tout `index` (toujours >= 0) via la même vérification que les autres
    catégories, sans cas particulier à écrire."""
    if layer in ("full", "half", "quarter"):
        return pattern.width * pattern.height
    assert pattern.grid is not None  # garanti par l'appelant, voir sync_progress
    field = "backstitch_json" if layer == "backstitch" else "french_knots_json"
    return len(json.loads(getattr(pattern.grid, field)))


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

    Depuis le Lot 8, `ProgressOp.layer` distingue jusqu'à cinq catégories de
    points (point entier, 1/2, 1/4, point arrière, nœud), chacune avec son
    propre bitmap (`Progress.bitmap*`) et son propre espace d'index — jamais
    partagé entre catégories, pour ne jamais cocher le mauvais élément par
    confusion de couche (voir `app/models.py::Progress`).
    """
    pattern = _get_pattern(session, pattern_id)
    progress = pattern.progress
    if progress is None:
        raise HTTPException(status_code=404, detail="Progression introuvable pour ce motif")
    if pattern.grid is None:
        raise HTTPException(status_code=404, detail="Grille introuvable pour ce motif")

    bounds = {layer: _layer_bound(pattern, layer) for layer in _LAYER_ATTR}
    for op in payload.ops:
        bound = bounds[op.layer]
        if op.index >= bound:
            raise HTTPException(
                status_code=400,
                detail=f"Index hors limites pour la catégorie « {op.layer} » : "
                f"{op.index} >= {bound}",
            )

    # Calculé avant l'écriture : les événements déjà connus du client ne
    # doivent pas lui être renvoyés, seuls ceux faits par d'autres appareils
    # depuis sa dernière synchronisation comptent.
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
    summary="Historique d'activité dérivé des événements de progression",
)
def get_activity(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> PatternActivityOut:
    _get_pattern(session, pattern_id)  # 404 si le motif n'existe pas.
    events = (
        session.execute(
            select(ProgressEvent)
            .where(ProgressEvent.pattern_id == pattern_id)
            .order_by(ProgressEvent.ts)
        )
        .scalars()
        .all()
    )
    # SQLite ne conserve pas le fuseau horaire au stockage : `event.ts` en
    # ressort naïf bien que la colonne soit `DateTime(timezone=True)` et
    # toujours écrite en UTC (`_utcnow`, `app/models.py`) — sans ce réattachement
    # explicite, comparer à `datetime.now(UTC)` lève une `TypeError`.
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
    summary="Export .cshp (format ouvert)",
    response_class=Response,
)
def export_pattern(
    pattern_id: str, session: Annotated[Session, Depends(get_session)]
) -> Response:
    pattern = _get_pattern(session, pattern_id)
    if pattern.grid is None or pattern.progress is None:
        raise HTTPException(status_code=404, detail="Grille ou progression introuvable")

    archive = build_cshp_archive(pattern, pattern.palette_entries, pattern.grid, pattern.progress)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"{pattern.name}.cshp")},
    )
