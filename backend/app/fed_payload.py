"""A shared pattern's content, as two paired instances exchange it
(Lot 11b, issue #78).

The same serialisation as a backup's palette and grid (`app/backup.py`):
one format, one set of conversions. Never any progress — it belongs to one
profile of one instance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.backup import dump_grid, dump_palette_entry, grid_from, palette_entry_from
from app.codec import base64_to_bytes
from app.http import api_error
from app.labels import labels_from_json, labels_to_json
from app.models import Pattern
from app.schemas import FedPattern

# A grid layer is width × height uint16 values: refuse anything that does not
# match before it is stored, rather than a pattern that crashes the canvas.
_BYTES_PER_CELL = 2


def to_fed(pattern: Pattern, contributed_by_name: str | None) -> FedPattern:
    return FedPattern(
        id=pattern.id,
        name=pattern.name,
        labels=labels_from_json(pattern.labels_json),
        revision=pattern.revision,
        width=pattern.width,
        height=pattern.height,
        fabric_count=pattern.fabric_count,
        notes=pattern.notes,
        contributed_by_name=contributed_by_name,
        palette=[dump_palette_entry(entry) for entry in pattern.palette_entries],
        grid=dump_grid(pattern.grid) if pattern.grid is not None else None,
    )


def _check(payload: FedPattern) -> None:
    if payload.grid is None:
        raise api_error(400, "fed_pattern_invalid")
    try:
        layer = base64_to_bytes(payload.grid.layer_full)
    except ValueError as error:
        raise api_error(400, "fed_pattern_invalid") from error
    if len(layer) != payload.width * payload.height * _BYTES_PER_CELL:
        raise api_error(400, "fed_pattern_invalid")


def _add_content(session: Session, pattern_id: str, payload: FedPattern) -> None:
    for entry in payload.palette:
        session.add(palette_entry_from(entry, pattern_id))
    if payload.grid is not None:
        session.add(grid_from(payload.grid, pattern_id))


def new_from_fed(
    session: Session,
    payload: FedPattern,
    *,
    library: str,
    name: str | None = None,
    revision: int = 1,
    contributed_by: str | None = None,
    contributed_by_name: str | None = None,
    source_peer_id: str | None = None,
    remote_id: str | None = None,
) -> Pattern:
    """A shared pattern, mirror or proposal made from a received payload —
    never a personal one (those always start from a copy made here)."""
    _check(payload)
    now = datetime.now(UTC)
    pattern = Pattern(
        id=uuid.uuid4().hex,
        owner_id=None,
        library=library,
        name=name or payload.name,
        width=payload.width,
        height=payload.height,
        fabric_count=payload.fabric_count,
        notes=payload.notes,
        labels_json=labels_to_json(payload.labels),
        revision=revision,
        contributed_by=contributed_by,
        contributed_by_name=contributed_by_name,
        source_peer_id=source_peer_id,
        remote_id=remote_id,
        created_at=now,
        updated_at=now,
    )
    session.add(pattern)
    session.flush()
    _add_content(session, pattern.id, payload)
    session.flush()
    return pattern


def replace_from_fed(session: Session, target: Pattern, payload: FedPattern) -> None:
    """Give `target` a received payload's content (palette, grid,
    dimensions), keeping its identity, name and labels."""
    _check(payload)
    for entry in list(target.palette_entries):
        session.delete(entry)
    if target.grid is not None:
        session.delete(target.grid)
    session.flush()
    session.expire(target, ["palette_entries", "grid"])
    target.width = payload.width
    target.height = payload.height
    target.fabric_count = payload.fabric_count
    _add_content(session, target.id, payload)
    session.flush()
    session.expire(target, ["palette_entries", "grid"])
