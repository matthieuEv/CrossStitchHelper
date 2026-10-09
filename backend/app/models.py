"""SQLAlchemy models.

Complete domain model from Lot 1 (see ``docs/roadmap.md`` and specification
§6): ``patterns``, ``palette_entries``, ``grids``, ``progress``,
``progress_events``. Structural constraint recalled in ``CLAUDE.md``:
**progress is stored separately from the grid**, in distinct tables linked
only by ``pattern_id`` — a re-import never touches ``progress``.

``recipes`` (§6.2, Lot 6) completes this model: a file fingerprint
(``app/fingerprint.py``) associated with a reusable import configuration.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AppMeta(Base):
    """Instance metadata, as key/value pairs.

    Serves two concrete needs: providing a non-empty first migration (hence
    an Alembic chain really verified end to end), and letting the health
    endpoint prove that the database responds to reads, not just that the
    file exists.
    """

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"AppMeta(key={self.key!r}, value={self.value!r})"


class Pattern(Base):
    """An imported pattern (or, before Lot 2, injected directly into the
    database).

    ``owner_id`` is nullable from the single-user V1 onwards, so as not to
    close the door on multi-user later (specification §5.2).
    """

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fabric_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    import_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipe_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    palette_entries: Mapped[list[PaletteEntry]] = relationship(
        back_populates="pattern",
        cascade="all, delete-orphan",
        order_by="PaletteEntry.index_in_grid",
    )
    grid: Mapped[Grid | None] = relationship(back_populates="pattern", cascade="all, delete-orphan")
    progress: Mapped[Progress | None] = relationship(
        back_populates="pattern", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Pattern(id={self.id!r}, name={self.name!r}, {self.width}x{self.height})"


class PaletteEntry(Base):
    """A colour in a pattern's palette.

    ``index_in_grid`` is the integer used in the grid blob (§6.3): 0 means
    "empty cell", so real palette indices start at 1.
    """

    __tablename__ = "palette_entries"
    __table_args__ = (UniqueConstraint("pattern_id", "index_in_grid"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_in_grid: Mapped[int] = mapped_column(Integer, nullable=False)

    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rgb_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol_svg: Mapped[str | None] = mapped_column(Text, nullable=True)

    strands_full: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strands_back: Mapped[int | None] = mapped_column(Integer, nullable=True)

    count_full: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_half: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_quarter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_french: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_beads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backstitch_length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    pattern: Mapped[Pattern] = relationship(back_populates="palette_entries")

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"PaletteEntry(pattern_id={self.pattern_id!r}, code={self.code!r})"


class Grid(Base):
    """A pattern's grid layers, compacted (§6.1).

    One row per pattern: ``pattern_id`` is both primary key and foreign key
    (strict one-to-one relationship).

    ``backstitch_json``/``french_knots_json`` (Lot 8): see
    ``app/schemas.py::BackstitchSegment``/``FrenchKnot`` for the exact
    coordinate convention (cell corners for one, cell centre for the other —
    never pixels).
    """

    __tablename__ = "grids"

    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    layer_full: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    layer_half: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    layer_quarter: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    backstitch_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    french_knots_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    encoding: Mapped[str] = mapped_column(String(16), nullable=False, default="uint16le")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    pattern: Mapped[Pattern] = relationship(back_populates="grid")

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Grid(pattern_id={self.pattern_id!r}, version={self.version})"


class Progress(Base):
    """A pattern's progress bitmap — separate from ``Grid`` (§6.1).

    ``version`` is incremented on every applied delta (see
    :mod:`app.api.patterns`); it is the value the client compares to detect
    whether it missed changes made from another device.

    ``bitmap`` covers full stitches only (``Grid.layer_full``) — it is
    authoritative for ``stitched_count`` and the overall percentage (§7.1),
    unchanged since Lot 1. The next four columns (Lot 8) follow the same
    principle for the other stitch categories, each ``NULL`` as long as the
    corresponding grid has no content in that category (same convention as
    ``Grid.layer_half``/``layer_quarter``): ``bitmap_half``/``bitmap_quarter``
    have the same shape as ``bitmap`` (1 bit per cell,
    ``Grid.layer_half``/``layer_quarter``); ``bitmap_backstitch``/
    ``bitmap_knots`` are sized on the number of elements of
    ``Grid.backstitch_json``/``french_knots_json`` (1 bit per segment/knot,
    never per cell — these are not grids)."""

    __tablename__ = "progress"

    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    bitmap: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    bitmap_half: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bitmap_quarter: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bitmap_backstitch: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bitmap_knots: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stitched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    pattern: Mapped[Pattern] = relationship(back_populates="progress")

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Progress(pattern_id={self.pattern_id!r}, version={self.version})"


class ProgressEvent(Base):
    """Log of applied progress deltas, for undo and multi-device resume
    (§6.2).

    ``version_after`` matches ``Progress.version`` immediately after this
    event was applied: a client that knows an older version can therefore
    fetch, in one request, all the events to replay to catch up with the
    current state.
    """

    __tablename__ = "progress_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    ops_json: Mapped[str] = mapped_column(Text, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return (
            f"ProgressEvent(pattern_id={self.pattern_id!r}, version_after={self.version_after})"
        )


class Recipe(Base):
    """A validated import configuration, reusable on a future file with the
    same fingerprint (Lot 6, specification §8.7, §6.2).

    ``config_json`` contains **only geometric and structural parameters**
    (`CLAUDE.md`: "never the pattern's creative content") — currently only
    ``crop_by_page`` (see `app/api/recipes.py`). Never the dimensions, the
    palette or the painted areas: those are content specific to each pattern,
    which always differs from one file to the next even within the same
    publisher (specification §4.1, Winter Wreath/Summer Flight vs Botanical
    Citrus/Cucurbit case).
    """

    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    grid_type: Mapped[str] = mapped_column(String(8), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Recipe(id={self.id!r}, label={self.label!r}, fingerprint={self.fingerprint[:8]!r})"


class ImportJob(Base):
    """The state of an import in progress (wizard, Lot 2 — specification §6.2,
    §9).

    ``result_json`` carries both what the user entered in the wizard
    (``config``: cropping, dimensions, palette, painted areas) and what was
    computed from it (``preview``: the assembled grid). Lot 2 has no
    automatic detection engine — ``config`` is therefore entirely manual,
    never inferred from an analysis of the file.
    """

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    pattern_id: Mapped[str | None] = mapped_column(
        ForeignKey("patterns.id", ondelete="SET NULL"), nullable=True
    )
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"ImportJob(id={self.id!r}, status={self.status!r}, kind={self.kind!r})"
