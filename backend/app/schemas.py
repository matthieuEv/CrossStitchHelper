"""Pydantic API schemas (specification §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiErrorDetail(BaseModel):
    """Body of an HTTP error (`HTTPException(detail=...)`) — a code rather
    than text frozen on the server (translation audit, Lot 8), translated on
    the client via the `error.<code>` key of `frontend/src/i18n/fr.ts`/
    `en.ts`. Same principle as `DetectionWarning` for automatic detection
    warnings. `frontend/src/lib/api.ts` can fall back to a generic message if
    a `detail` does not follow this shape (a native FastAPI validation error,
    for example — outside this mechanism)."""

    code: str
    params: dict[str, str | int | float] = Field(default_factory=dict)


class PaletteEntryOut(BaseModel):
    index_in_grid: int
    brand: str
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    strands_full: int | None = None
    strands_back: int | None = None
    count_full: int
    count_half: int
    count_quarter: int
    count_french: int
    count_beads: int
    backstitch_length_cm: float | None = None

    model_config = {"from_attributes": True}


class PatternSummary(BaseModel):
    """What a library thumbnail needs (§7.1)."""

    id: str
    name: str
    width: int
    height: int
    palette_count: int
    stitched_count: int
    cell_count: int
    percent: int
    created_at: datetime
    updated_at: datetime


class PatternDetail(BaseModel):
    id: str
    owner_id: str | None
    name: str
    source_filename: str | None
    fabric_count: int | None
    width: int
    height: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    palette: list[PaletteEntryOut]

    model_config = {"from_attributes": True}


class BackstitchSegment(BaseModel):
    """A backstitch stroke, in cell **corner** coordinates (Lot 8): (0, 0) is
    the top-left corner of the grid's cell (0, 0), (1, 0) the top-right
    corner of that same cell (= top-left corner of cell (1, 0)), etc. — never
    a pixel or a cell centre, so the stroke stays correct whatever the zoom
    or the cell size displayed on screen (same principle as
    `Grid.layer_full`, independent of rendering)."""

    x1: float
    y1: float
    x2: float
    y2: float
    palette_index: int


class FrenchKnot(BaseModel):
    """A French knot, in **cell centre** coordinates (Lot 8): (0.5, 0.5) is
    the centre of cell (0, 0) — never a corner (unlike `BackstitchSegment`)
    nor a pixel."""

    x: float
    y: float
    palette_index: int


class GridOut(BaseModel):
    pattern_id: str
    width: int
    height: int
    encoding: str
    version: int
    layer_full: str = Field(description="Base64-encoded Uint16Array, row by row.")
    layer_half: str | None = None
    layer_quarter: str | None = None
    backstitch: list[BackstitchSegment]
    french_knots: list[FrenchKnot]


class ProgressOut(BaseModel):
    pattern_id: str
    version: int
    stitched_count: int
    """Checked full stitches — the only category counting towards the overall
    completion percentage (§7.1), unchanged since Lot 1."""
    cell_count: int
    bitmap: str = Field(description="1 bit per cell, base64-encoded, row by row.")

    bitmap_half: str | None = Field(
        default=None,
        description="Checked 1/2 stitches, same shape as `bitmap` — absent if `Grid.layer_half` "
        "is empty (no 1/2 stitch in this pattern).",
    )
    bitmap_quarter: str | None = Field(
        default=None,
        description="Checked 1/4 stitches, same shape as `bitmap` — absent if `Grid.layer_quarter` "
        "is empty.",
    )
    bitmap_backstitch: str | None = Field(
        default=None,
        description="Checked backstitch segments — 1 bit per element of "
        "`GridOut.backstitch`, in the same order (never a grid: absent if there is no segment).",
    )
    bitmap_knots: str | None = Field(
        default=None,
        description="Checked knots — 1 bit per element of `GridOut.french_knots`, same "
        "convention as `bitmap_backstitch`.",
    )
    stitched_count_half: int = 0
    stitched_count_quarter: int = 0
    stitched_count_backstitch: int = 0
    stitched_count_knots: int = 0


class ProgressOp(BaseModel):
    """A change to a cell or element, expressed as an absolute state — hence
    idempotent (specification §9: "checking a cell is an idempotent
    operation, which makes conflicts trivial to resolve").

    `layer` identifies the targeted stitch category (Lot 8): `index` is then
    read in that particular category's space — a grid index (0-based, row by
    row) for `full`/`half`/`quarter`, an index into
    `GridOut.backstitch`/`french_knots` for `backstitch`/`knot`. Never an
    index space shared between categories, so the wrong cell/segment is never
    checked through a layer mix-up."""

    layer: Literal["full", "half", "quarter", "backstitch", "knot"] = "full"
    index: int = Field(ge=0)
    stitched: bool


class ProgressSyncRequest(BaseModel):
    base_version: int = Field(ge=0, description="Last progress version known to the client.")
    ops: list[ProgressOp] = Field(default_factory=list)


class ProgressSyncResponse(BaseModel):
    version: int
    stitched_count: int
    conflict: bool = Field(
        description="True if the client had missed changes made by another device."
    )
    missing_ops: list[ProgressOp] = Field(
        description=(
            "Operations applied by other devices since `base_version`, "
            "to be replayed on the client."
        )
    )


# --- Activity history (Lot 3, specification §11) ---------------------------
#
# Derived from `progress_events`, never stored separately: the delta log
# already written for multi-device synchronisation (Lot 1) is the only source
# of truth for "who stitched when".


class ActivityDayOut(BaseModel):
    """Cells stitched on a given day of the last 7 rolling days."""

    weekday: int = Field(ge=0, le=6, description="0 = Monday, ISO.")
    stitches: int


class ActivitySessionOut(BaseModel):
    """A session = progress events with no gap longer than 30 min."""

    hours_ago: float
    stitches: int
    minutes: int


class PatternActivityOut(BaseModel):
    activity: list[ActivityDayOut]
    sessions: list[ActivitySessionOut]


# --- Import wizard (Lot 2, specification §7.2, §9) -------------------------
#
# Lot 2: no automatic detection, `ImportCrop`, dimensions and palette are
# entered entirely by the user in the wizard.
#
# Lot 4 (`detected_cells`, `ImportDetection`): for a recognised type A PDF,
# `app/type_a.py` pre-fills `columns`/`rows`/`palette` and a background grid
# — the user always corrects through the same painted-area mechanism
# (`fills`) as in Lot 2, never an imposed proposal (specification §4.4:
# "never an imposed result").


class ImportCrop(BaseModel):
    """Page cropping, as a percentage of each edge (0-49)."""

    left: float = Field(ge=0, le=49)
    top: float = Field(ge=0, le=49)
    right: float = Field(ge=0, le=49)
    bottom: float = Field(ge=0, le=49)


class ImportPaletteEntry(BaseModel):
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    """Real symbol cut out of the PDF (Lot 4, `detect_type_a`) — absent for
    an entry typed by hand (Lot 2), which is still rendered via
    `symbol_key`. See `app.type_a.SymbolGlyphLocation`."""


class ImportFillZone(BaseModel):
    """An area painted with a single palette index — see
    `app.imports_engine.apply_fills`.

    ``palette_index`` 0 erases the area (turns it back into "empty cell"),
    same convention as the grid blob (§6.3): that is what allows a wrongly
    painted area to be corrected without having to remove the entry from the
    list.
    """

    x0: int = Field(ge=0)
    y0: int = Field(ge=0)
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    palette_index: int = Field(ge=0)


class ImportConfig(BaseModel):
    crop_by_page: dict[str, ImportCrop] = Field(
        default_factory=dict,
        description=(
            "Manual cropping, by page number (str key because JSON) — a page not "
            "present has not been cropped by the user yet. A purely visual aid for "
            "counting cells, never consumed by extraction."
        ),
    )
    columns: int | None = Field(default=None, ge=1, le=1000)
    rows: int | None = Field(default=None, ge=1, le=1000)
    palette: list[ImportPaletteEntry] = Field(default_factory=list)
    fills: list[ImportFillZone] = Field(default_factory=list)
    detected_cells: list[int] | None = Field(
        default=None,
        description=(
            "Grid proposed by automatic detection (Lot 4), same convention as the "
            "grid blob: length columns*rows, 0 = empty cell, n = 1-based index into "
            "`palette`. `fills` is applied on top, never underneath."
        ),
    )
    uncertain_cells: list[int] | None = Field(
        default=None,
        description=(
            "Indices (0-based, into `detected_cells`) of the cells that type B/C "
            "automatic detection (Lot 5) explicitly flags as uncertain — doubtful "
            "colour and/or ambiguous symbol. Never consumed by extraction itself, "
            "purely indicative for the import wizard: an uncertain cell is never "
            "silently wrong (mandatory rule of the `pdf-extraction-specialist`)."
        ),
    )
    detected_half: list[int] | None = Field(
        default=None,
        description=(
            "1/2 stitches proposed by automatic detection (Lot 9, type A only) — "
            "same convention as `detected_cells`. No manual correction mechanism "
            "for this layer: committed as is if the dimensions have not changed "
            "since detection."
        ),
    )
    detected_quarter: list[int] | None = Field(
        default=None, description="1/4 stitches proposed by automatic detection (Lot 9)."
    )
    detected_backstitch: list[BackstitchSegment] | None = Field(
        default=None,
        description=(
            "Backstitch segments proposed by automatic detection (Lot 9, type A "
            "only) — coordinates in the frame of the detected grid (`columns`/`rows` "
            "of this same job)."
        ),
    )
    detected_french_knots: list[FrenchKnot] | None = Field(
        default=None, description="Knots proposed by automatic detection (Lot 9)."
    )
    detected_fabric_count: int | None = Field(
        default=None,
        description=(
            "Fabric count stated plainly by the PDF (Lot 9, type A only) — only "
            "used to pre-fill the summary step's field, never consumed by extraction "
            "itself nor imposed on the user."
        ),
    )


class ImportConfigPatch(BaseModel):
    """Like `ImportConfig`, but each field provided entirely replaces the
    existing one rather than being merged finely — the client always sends
    back the complete state it holds (same principles as `done` on the
    tracking side), which makes resynchronisation trivial after navigating
    back and forth in the wizard."""

    crop_by_page: dict[str, ImportCrop] | None = None
    columns: int | None = Field(default=None, ge=1, le=1000)
    rows: int | None = Field(default=None, ge=1, le=1000)
    palette: list[ImportPaletteEntry] | None = None
    fills: list[ImportFillZone] | None = None
    detected_cells: list[int] | None = None
    uncertain_cells: list[int] | None = None
    detected_half: list[int] | None = None
    detected_quarter: list[int] | None = None
    detected_backstitch: list[BackstitchSegment] | None = None
    detected_french_knots: list[FrenchKnot] | None = None
    detected_fabric_count: int | None = None


class ImportPreview(BaseModel):
    """The grid assembled from the current configuration — absent as long as
    `columns`/`rows`/`palette` are not filled in yet."""

    width: int
    height: int
    cell_count: int
    filled_count: int
    layer_full: str = Field(description="Base64-encoded Uint16Array, like `GridOut`.")
    palette: list[ImportPaletteEntry]


class DetectionWarning(BaseModel):
    """An automatic detection warning — never text already formatted on the
    server (translation audit, Lot 8): `code` identifies the message (key
    `import.warning.<code>` of `frontend/src/i18n/fr.ts`/`en.ts`), `params`
    carries the interpolated values (counts, DMC codes, percentages…) that
    the translation key consumes via `{name}`. The final message is composed
    on the client, in the language chosen by the user — never frozen in
    French at detection time."""

    code: str
    params: dict[str, str | int | float] = Field(default_factory=dict)


class ImportDetection(BaseModel):
    """Summary of automatic detection (Lots 4-5) — never a certainty, always
    a usable score so the import wizard invites checking rather than blind
    trust (§4.4)."""

    grid_type: str = Field(description='"A", "B", "C" or "E" — see specification §4.4.')
    confidence: float = Field(ge=0, le=1)
    warnings: list[DetectionWarning] = Field(default_factory=list)


class ImportAppliedRecipe(BaseModel):
    """Recipe (Lot 6) whose `crop_by_page` was reused for this job — never
    the dimensions or the palette, see `app/models.py::Recipe`."""

    id: str
    label: str


class ImportJobOut(BaseModel):
    id: str
    status: str
    kind: str
    page_count: int
    source_filename: str
    pattern_id: str | None
    config: ImportConfig
    preview: ImportPreview | None
    detection: ImportDetection | None = None
    detecting: bool = Field(
        default=False,
        description="Automatic detection (Lot 4) running as a background task for this PDF.",
    )
    applied_recipe: ImportAppliedRecipe | None = None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class ImportCommitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fabric_count: int | None = Field(default=None, ge=1, le=64)


class ImportCommitResponse(BaseModel):
    pattern_id: str


# --- Reusable recipes (Lot 6, specification §8.7, §6.2) --------------------


class RecipeConfig(BaseModel):
    """The subset of `ImportConfig` a recipe can carry — deliberately
    restricted to geometric/structural parameters (`CLAUDE.md`: never the
    pattern's creative content). No dimensions, palette or painted areas:
    they always differ from one pattern to another, even within the same
    publisher."""

    crop_by_page: dict[str, ImportCrop] = Field(default_factory=dict)


class RecipeCreate(BaseModel):
    job_id: str
    label: str = Field(min_length=1, max_length=200)


class RecipeOut(BaseModel):
    id: str
    fingerprint: str
    label: str
    grid_type: str
    config: RecipeConfig
    created_at: datetime
    usage_count: int


# --- Full backup/restore (Lot 8, specification §7.5) -----------------------
#
# Self-contained JSON format (see `app/backup.py`), distinct from the `.cshp`
# export (Lot 2), which only covers one pattern at a time: this one covers
# the whole instance (all patterns, all progress, all recipes), for the user
# who only has access to their phone, not to the Docker volume.


class BackupPaletteEntry(BaseModel):
    id: str
    index_in_grid: int
    brand: str
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_svg: str | None = None
    strands_full: int | None = None
    strands_back: int | None = None
    count_full: int = 0
    count_half: int = 0
    count_quarter: int = 0
    count_french: int = 0
    count_beads: int = 0
    backstitch_length_cm: float | None = None


class BackupGrid(BaseModel):
    layer_full: str = Field(description="Base64-encoded Uint16Array, like `GridOut`.")
    layer_half: str | None = None
    layer_quarter: str | None = None
    backstitch_json: str = "[]"
    french_knots_json: str = "[]"
    encoding: str = "uint16le"
    version: int = 1


class BackupProgress(BaseModel):
    bitmap: str = Field(description="1 bit per cell, base64-encoded, like `ProgressOut`.")
    bitmap_half: str | None = None
    bitmap_quarter: str | None = None
    bitmap_backstitch: str | None = None
    bitmap_knots: str | None = None
    version: int = 0
    stitched_count: int = 0
    updated_at: datetime


class BackupProgressEvent(BaseModel):
    """An event from the `progress_events` log — without it, the activity
    history (§11) would vanish on restore even if progress itself is
    intact."""

    id: int
    ts: datetime
    ops_json: str
    version_after: int


class BackupPattern(BaseModel):
    id: str
    owner_id: str | None = None
    name: str
    source_filename: str | None = None
    source_sha256: str | None = None
    width: int
    height: int
    fabric_count: int | None = None
    created_at: datetime
    updated_at: datetime
    import_config_json: str | None = None
    recipe_id: str | None = None
    notes: str | None = None
    palette: list[BackupPaletteEntry] = Field(default_factory=list)
    grid: BackupGrid | None = None
    progress: BackupProgress | None = None
    progress_events: list[BackupProgressEvent] = Field(default_factory=list)


class BackupRecipe(BaseModel):
    id: str
    fingerprint: str
    label: str
    grid_type: str
    config_json: str
    created_at: datetime
    usage_count: int = 0


class BackupDocument(BaseModel):
    """The exported/restored document as a whole.

    Deliberately out of scope (`app/backup.py`): ``ImportJob`` (transient
    state of an import wizard in progress, never durable data) and
    ``AppMeta`` (internal bookkeeping, not user data)."""

    format: Literal["csh-backup"] = "csh-backup"
    format_version: int = 1
    generated_at: datetime
    patterns: list[BackupPattern] = Field(default_factory=list)
    recipes: list[BackupRecipe] = Field(default_factory=list)


class BackupRestoreSummary(BaseModel):
    patterns_count: int
    recipes_count: int
    progress_events_count: int


class AutoBackupSettings(BaseModel):
    enabled: bool
