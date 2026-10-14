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


class PatternDuplicateIn(BaseModel):
    """Name of the copy — chosen (and translated) by the client."""

    name: str = Field(min_length=1, max_length=200)


class PatternDuplicateOut(BaseModel):
    id: str


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
    labels: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    origin_pattern_id: str | None = Field(
        default=None, description="The shared pattern this one is a copy of (Lot 11)."
    )
    update_available: bool = Field(
        default=False, description="The original's content changed since it was copied."
    )


class PatternDetail(BaseModel):
    id: str
    owner_id: str | None
    name: str
    source_filename: str | None
    fabric_count: int | None
    width: int
    height: int
    notes: str | None
    labels: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    palette: list[PaletteEntryOut]

    model_config = {"from_attributes": True}


class PatternUpdate(BaseModel):
    """What a pattern's "Edit" action changes (issue #57) — each field given
    replaces the stored one, an absent field is left as is."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    labels: list[str] | None = None


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
    stitch: Literal["full", "half", "quarter"] = Field(
        default="full",
        description="Layer the area paints (issue #41) — see `apply_fills`.",
    )


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
    layer_half: str | None = Field(
        default=None, description="Same encoding, `None` when there is no 1/2 stitch."
    )
    layer_quarter: str | None = Field(
        default=None, description="Same encoding, `None` when there is no 1/4 stitch."
    )
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


LibraryChoice = Literal["personal", "shared", "both"]


class ImportCommitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fabric_count: int | None = Field(default=None, ge=1, le=64)
    labels: list[str] = Field(default_factory=list)
    library: LibraryChoice = Field(
        default="personal",
        description="Where the pattern goes (Lot 11): one's own library, the shared "
        "library, or both (a personal copy linked to the shared one).",
    )
    shared_target_peer_id: str | None = Field(
        default=None,
        max_length=32,
        description="For `shared`/`both`: a paired instance's shared library rather than "
        "this one's (Lot 11b).",
    )


class ImportCommitResponse(BaseModel):
    pattern_id: str | None = Field(
        description="The personal pattern, unless `library` was `shared`."
    )
    shared_pattern_id: str | None = None


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
    # Issue #57 — absent from backups made before it: no labels.
    labels: list[str] = Field(default_factory=list)
    # Lot 11 (format version 3) — absent before: a personal pattern.
    library: Literal["personal", "shared", "proposal"] = "personal"
    revision: int = 1
    contributed_by: str | None = None
    origin_pattern_id: str | None = None
    origin_revision: int | None = None
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


class BackupUser(BaseModel):
    """A profile (format version 2, Lot 10) — with its password hash, so a
    restored instance can be logged into with the same passwords. Never its
    sessions: a restore logs out every device of a profile it removes."""

    id: str
    email: str
    first_name: str
    last_name: str
    role: Literal["admin", "user"]
    password_hash: str
    created_at: datetime
    updated_at: datetime


class BackupSharedRequest(BaseModel):
    """A request about a shared pattern (format version 3, Lot 11)."""

    id: str
    kind: Literal["removal", "replacement"]
    status: Literal["pending", "accepted", "rejected", "cancelled"]
    shared_pattern_id: str | None = None
    pattern_name: str
    requested_by: str | None = None
    message: str | None = None
    proposal_pattern_id: str | None = None
    resolved_by: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class BackupDocument(BaseModel):
    """The exported/restored document as a whole.

    Deliberately out of scope (`app/backup.py`): ``ImportJob`` (transient
    state of an import wizard in progress, never durable data),
    ``AppMeta`` (internal bookkeeping, not user data) and sessions.

    ``users`` is ``None`` in a version 1 document (made before profiles,
    Lot 10): restoring one keeps the instance's profiles and hands every
    pattern to the admin who restores it."""

    format: Literal["csh-backup"] = "csh-backup"
    format_version: int = 3
    generated_at: datetime
    users: list[BackupUser] | None = None
    patterns: list[BackupPattern] = Field(default_factory=list)
    recipes: list[BackupRecipe] = Field(default_factory=list)
    shared_requests: list[BackupSharedRequest] = Field(default_factory=list)


class BackupRestoreSummary(BaseModel):
    users_count: int
    patterns_count: int
    recipes_count: int
    progress_events_count: int


class AutoBackupSettings(BaseModel):
    enabled: bool


class ThreadShadeOut(BaseModel):
    """A shade of a thread colour chart (`GET /api/threads/dmc`). Colours
    come from an unofficial community table — a reasonable starting point,
    never an exact identification (see `app/dmc_catalog.py`)."""

    code: str
    name: str
    rgb_hex: str


# --- Profiles (Lot 10, issue #77) -------------------------------------------

# Deliberately loose: an address is only a contact detail and a future OpenID
# Connect link (no email is ever sent), so anything with one `@` will do —
# no extra dependency (`email-validator`) for a stricter check nobody needs.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+$"
Role = Literal["admin", "user"]


class SetupRequest(BaseModel):
    """First-launch setup: the first admin's profile."""

    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    """The login screen lists the profiles ("Who's stitching?"): the profile
    is picked from that list, not typed, so its id identifies it."""

    user_id: str = Field(max_length=32)
    password: str = Field(max_length=256)


class ProfileCard(BaseModel):
    """What the login screen may show about a profile to anyone who opens
    the app — first name, initials and a colour, never the email or the
    role."""

    id: str
    first_name: str
    initials: str
    avatar_hue: int = Field(description="0-359, derived from the id: stable per profile.")


class UserOut(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: Role
    initials: str
    avatar_hue: int
    created_at: datetime


class AdminUserOut(UserOut):
    """A profile as listed for admins: with the size of its personal
    library, shown before a deletion (it is deleted along with the
    profile)."""

    pattern_count: int


class AuthStatus(BaseModel):
    setup_required: bool = Field(description="True while the instance has no profile at all.")
    user: UserOut | None = None


class MeUpdate(BaseModel):
    """A profile editing its own information — never its role."""

    email: str | None = Field(default=None, max_length=254, pattern=_EMAIL_PATTERN)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserCreate(BaseModel):
    """An admin adding a profile, with the initial password they chose
    (issue #77 — no email is sent, no self-registration)."""

    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: Role = "user"
    password: str = Field(min_length=8, max_length=256)


class UserUpdate(BaseModel):
    """An admin editing a profile: each field given replaces the stored one.
    `password` is a reset (ends every session of that profile)."""

    email: str | None = Field(default=None, max_length=254, pattern=_EMAIL_PATTERN)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


# --- Shared library (Lot 11, issue #78) --------------------------------------


class SharedPatternOut(BaseModel):
    """A pattern of the shared library, as its tab lists it."""

    id: str
    name: str
    width: int
    height: int
    palette_count: int
    cell_count: int
    labels: list[str] = Field(default_factory=list)
    revision: int
    contributed_by_name: str | None = Field(
        description="Who added it; null once that profile is deleted."
    )
    created_at: datetime
    updated_at: datetime
    my_copy_ids: list[str] = Field(
        default_factory=list, description="The logged-in profile's copies of it."
    )
    source_name: str | None = Field(
        default=None,
        description="The paired instance this pattern's home is (Lot 11b); null if here.",
    )
    can_moderate: bool = Field(
        default=False,
        description="The logged-in profile may rename, replace or remove it: an admin, "
        "for a pattern of a paired instance only if that instance trusts this one's admins.",
    )


RequestKind = Literal["removal", "replacement"]
RequestStatus = Literal["pending", "accepted", "rejected", "cancelled"]


class SharedRequestOut(BaseModel):
    id: str
    kind: RequestKind
    status: RequestStatus
    shared_pattern_id: str | None
    pattern_name: str
    requested_by_name: str | None
    mine: bool
    message: str | None
    proposal_pattern_id: str | None
    created_at: datetime
    resolved_at: datetime | None
    can_decide: bool = Field(
        default=False,
        description="The logged-in profile may accept or decline it: an admin, for a "
        "request about a paired instance's pattern only if that instance trusts this "
        "one's admins (Lot 11b).",
    )


class SharedTarget(BaseModel):
    """A shared library a pattern can be added to (Lot 11b): this
    instance's (``peer_id`` null), or a paired instance's that this one
    mirrors."""

    peer_id: str | None
    name: str


class SharedLibraryOut(BaseModel):
    """The shared tab in one call: its patterns, and the requests the
    logged-in profile may see — every pending one for an admin, its own for
    everybody."""

    patterns: list[SharedPatternOut]
    requests: list[SharedRequestOut]
    targets: list[SharedTarget] = Field(default_factory=list)


class SharedPatternRef(BaseModel):
    id: str


class ShareRequest(BaseModel):
    """Which shared library to add a pattern to: this instance's (null), or
    a paired instance's (Lot 11b)."""

    target_peer_id: str | None = Field(default=None, max_length=32)


class SharedCopyRequest(BaseModel):
    """Name of the personal copy — chosen (and translated) by the client."""

    name: str = Field(min_length=1, max_length=200)


class SharedReplaceRequest(BaseModel):
    """An admin replacing a shared pattern's content with one of their own
    personal patterns."""

    source_pattern_id: str = Field(max_length=32)


class SharedRequestCreate(BaseModel):
    kind: RequestKind
    shared_pattern_id: str = Field(max_length=32)
    message: str | None = Field(default=None, max_length=1000)
    proposal_pattern_id: str | None = Field(
        default=None,
        max_length=32,
        description="For a replacement: the personal pattern whose content is proposed.",
    )


class UpdateFromOriginRequest(BaseModel):
    """Name to give a new copy, used only when the update cannot be made in
    place without losing progress (`app/shared.py::update_copy`)."""

    name: str = Field(min_length=1, max_length=200)


class UpdateFromOriginOut(BaseModel):
    pattern_id: str
    in_place: bool


# --- Between two paired instances (Lot 11b, issue #78) -----------------------


class FedPattern(BaseModel):
    """A shared pattern's content as two instances exchange it — the same
    serialisation as a backup's palette and grid, never any progress."""

    id: str
    name: str = Field(min_length=1, max_length=200)
    labels: list[str] = Field(default_factory=list)
    revision: int = 1
    width: int = Field(ge=1, le=2000)
    height: int = Field(ge=1, le=2000)
    fabric_count: int | None = None
    notes: str | None = None
    contributed_by_name: str | None = None
    palette: list[BackupPaletteEntry] = Field(default_factory=list)
    grid: BackupGrid | None = None


class FedInfo(BaseModel):
    protocol: int
    instance_id: str
    name: str


class FedPairRequest(BaseModel):
    secret: str = Field(max_length=200)
    instance_id: str = Field(max_length=64)
    name: str = Field(min_length=1, max_length=200)


class FedPairResponse(BaseModel):
    token: str
    instance_id: str
    name: str
    trust_admins: bool


class FedChanges(BaseModel):
    """What changed in the host's shared library since a cursor: patterns
    added or changed (whole), patterns removed (their ids)."""

    cursor: int
    more: bool
    upserts: list[FedPattern] = Field(default_factory=list)
    deletions: list[str] = Field(default_factory=list)


class FedContribution(BaseModel):
    pattern: FedPattern
    contributor_name: str = Field(min_length=1, max_length=200)


class FedCreated(BaseModel):
    id: str
    revision: int


class FedActor(BaseModel):
    """Who acts, on the subscribed instance, for the host's record."""

    actor_name: str = Field(min_length=1, max_length=200)


class FedRename(FedActor):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    labels: list[str] | None = None


class FedReplace(FedActor):
    pattern: FedPattern


class FedRequestCreate(BaseModel):
    kind: RequestKind
    shared_pattern_id: str = Field(max_length=32)
    message: str | None = Field(default=None, max_length=1000)
    requester_name: str = Field(min_length=1, max_length=200)
    requester_ref: str = Field(max_length=32)
    proposal: FedPattern | None = None


class FedCancel(BaseModel):
    requester_ref: str = Field(max_length=32)


class FedRequest(BaseModel):
    id: str
    kind: RequestKind
    status: RequestStatus
    shared_pattern_id: str | None
    pattern_name: str
    requested_by_name: str | None
    requester_ref: str | None = Field(
        description="The requesting profile's id on the subscribed instance, for its own "
        "requests; null for anybody else's."
    )
    message: str | None
    proposal_pattern_id: str | None
    created_at: datetime
    resolved_at: datetime | None


class FedRequests(BaseModel):
    requests: list[FedRequest]


# --- Linking instances, admin side (Lot 11b) ---------------------------------


class PeerOut(BaseModel):
    id: str
    name: str
    role: Literal["host", "subscriber"]
    base_url: str | None
    trust_admins: bool
    last_sync_at: datetime | None
    last_error: str | None
    created_at: datetime


class InvitationOut(BaseModel):
    id: str
    trust_admins: bool
    created_at: datetime
    expires_at: datetime


class FederationOut(BaseModel):
    instance_id: str
    instance_name: str
    peers: list[PeerOut]
    invitations: list[InvitationOut]


class InstanceNameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class InvitationCreate(BaseModel):
    """`public_url`: how the invited instance's *server* reaches this one —
    by default the address the admin uses (the frontend fills it in)."""

    public_url: str = Field(min_length=8, max_length=500, pattern=r"^https?://")
    trust_admins: bool = False


class InvitationCreated(BaseModel):
    code: str
    expires_at: datetime


class JoinRequest(BaseModel):
    code: str = Field(min_length=8, max_length=2000)


class SyncResult(BaseModel):
    synced: int
    errors: list[str] = Field(default_factory=list)

