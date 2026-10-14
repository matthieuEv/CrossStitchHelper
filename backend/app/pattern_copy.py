"""Copying a pattern's content — palette and grid — between libraries.

One implementation for every copy the application makes: duplicating a
personal pattern (issue #52), sharing it, copying a shared pattern into
one's library, freezing a proposed replacement, and updating a copy from its
original (Lot 11, issue #78). Progress is never copied: it belongs to one
profile's stitching of one pattern (`CLAUDE.md`).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.codec import empty_bitmap
from app.models import Grid, PaletteEntry, Pattern, Progress

# Columns that make up a pattern's *content*, copied whatever the library.
# Identity, ownership, library membership and timestamps are set by the
# caller; `labels_json` and `notes` are a profile's own organisation of its
# library, carried along by default on a copy but never on a content update.
_CONTENT_COLUMNS = (
    "source_filename",
    "source_sha256",
    "width",
    "height",
    "fabric_count",
    "import_config_json",
    "recipe_id",
)


def _copy_palette_and_grid(session: Session, source: Pattern, target_id: str) -> None:
    for entry in source.palette_entries:
        session.add(
            PaletteEntry(
                **{
                    column.key: getattr(entry, column.key)
                    for column in PaletteEntry.__table__.columns
                    if column.key not in ("id", "pattern_id")
                },
                id=uuid.uuid4().hex,
                pattern_id=target_id,
            )
        )
    if source.grid is not None:
        session.add(
            Grid(
                **{
                    column.key: getattr(source.grid, column.key)
                    for column in Grid.__table__.columns
                    if column.key != "pattern_id"
                },
                pattern_id=target_id,
            )
        )


def clone_pattern(
    session: Session,
    source: Pattern,
    *,
    name: str,
    library: str,
    owner_id: str | None,
    contributed_by: str | None = None,
    origin: Pattern | None = None,
) -> Pattern:
    """A new pattern with `source`'s content. A personal one starts with
    empty progress (the same chart to stitch again); a shared or proposal
    one has no progress at all. `origin` links a personal copy to the shared
    pattern it comes from, at its current revision."""
    now = datetime.now(UTC)
    copy = Pattern(
        **{column: getattr(source, column) for column in _CONTENT_COLUMNS},
        id=uuid.uuid4().hex,
        name=name,
        owner_id=owner_id,
        library=library,
        revision=1,
        contributed_by=contributed_by,
        origin_pattern_id=origin.id if origin is not None else None,
        origin_revision=origin.revision if origin is not None else None,
        notes=source.notes,
        labels_json=source.labels_json,
        created_at=now,
        updated_at=now,
    )
    session.add(copy)
    session.flush()
    _copy_palette_and_grid(session, source, copy.id)
    if library == "personal":
        session.add(
            Progress(
                pattern_id=copy.id,
                bitmap=empty_bitmap(source.width * source.height),
                version=1,
                stitched_count=0,
                updated_at=now,
            )
        )
    return copy


def replace_content(session: Session, target: Pattern, source: Pattern) -> None:
    """Give `target` the content of `source` — palette, grid, dimensions —
    keeping its identity, name, labels and progress row untouched. The
    caller decides whether that progress still fits (`same_shape`)."""
    for entry in list(target.palette_entries):
        session.delete(entry)
    if target.grid is not None:
        session.delete(target.grid)
    session.flush()
    session.expire(target, ["palette_entries", "grid"])
    for column in _CONTENT_COLUMNS:
        setattr(target, column, getattr(source, column))
    _copy_palette_and_grid(session, source, target.id)
    session.flush()
    session.expire(target, ["palette_entries", "grid"])


def _special_counts(pattern: Pattern) -> tuple[int, int]:
    if pattern.grid is None:
        return (0, 0)
    return (
        len(json.loads(pattern.grid.backstitch_json)),
        len(json.loads(pattern.grid.french_knots_json)),
    )


def same_shape(a: Pattern, b: Pattern) -> bool:
    """Whether a progress recorded on `a` keeps its meaning on `b`: same
    cells, same number of backstitches and knots (their progress is indexed
    by element, not by cell — `app/models.py::Progress`)."""
    return (a.width, a.height) == (b.width, b.height) and _special_counts(a) == _special_counts(b)
