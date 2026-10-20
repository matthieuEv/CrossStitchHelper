"""Full data backup/restore (Lot 8, specification §7.5).

Distinct from the `.cshp` export (`app/export_cshp.py`, Lot 2), which only
covers a single pattern: this one covers the whole instance — all patterns,
their palette, their grid, their progress, the `progress_events` log
(without which the activity history, §11, would vanish on restore), and the
reusable recipes (Lot 6). JSON format (not a ZIP archive like `.cshp`): that
is what the settings' "Export (.json)" button already announces (§7.5,
frozen when the mockups were ported), and a user who only has their phone
must be able to open/inspect it with no extra tool. Binary fields follow the
same base64 convention as the rest of the API (`app/codec.py`), never the
raw bytes of a ZIP.

Deliberately out of scope: ``ImportJob`` (transient state of an import
wizard in progress, never durable data — see `app/models.py`), ``AppMeta``
(internal bookkeeping, not user data) and sessions.

Mirrors of a paired instance's shared library, and the requests mirrored
with them (Lot 11b), are never in a backup: they belong to that instance and
are pulled again from it after a restore (`_after_restore`). The pairings
themselves stay as they are — a restore is about this instance's data.

Format version 4 (issue #83) stores 1/4 stitches as a list of cells with a
corner (`quarter_json`) and adds 3/4 stitches. An older document's 1/4
layer is read as top-left items — where they were always drawn — with their
progress and their activity log moved along (`_upgrade_legacy_quarters`).

Format version 3 (Lot 11) adds the shared library: each pattern's library,
revision and links, and the requests about shared patterns. Version 2
documents restore with every pattern personal.

Since format version 2 (Lot 10), the document also carries the profiles,
password hashes included — a backup is therefore an admin-only download
(`app/api/backup.py`). A version 1 document (before profiles) still
restores: the instance keeps its profiles and every pattern goes to the
admin who restores it.

A restore is a **full replacement**, never a merge: that is the expected
semantics of a "restore" (as opposed to an "import"), and it avoids any
ambiguity about conflicting identifiers.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.codec import (
    base64_to_bytes,
    bitmap_byte_length,
    bytes_to_base64,
    decode_uint16_layer,
    get_bit,
    set_bit,
)
from app.instance import next_seq
from app.labels import labels_from_json, labels_to_json
from app.models import (
    Grid,
    PaletteEntry,
    Pattern,
    Peer,
    Progress,
    ProgressEvent,
    Recipe,
    SharedRequest,
    SharedTombstone,
    User,
)
from app.schemas import (
    BackupDocument,
    BackupGrid,
    BackupPaletteEntry,
    BackupPattern,
    BackupProgress,
    BackupProgressEvent,
    BackupRecipe,
    BackupRestoreSummary,
    BackupSharedRequest,
    BackupUser,
)

FORMAT: Literal["csh-backup"] = "csh-backup"
FORMAT_VERSION = 4
SUPPORTED_VERSIONS = (1, 2, 3, 4)


class BackupFormatError(ValueError):
    """The document provided is not a recognised CrossStitchHelper backup, or
    is a format version this instance cannot read.

    Carries `code`/`params` rather than an already formatted message —
    translated on the client (translation audit, Lot 8), see
    `app/schemas.py::ApiErrorDetail` and `app/api/backup.py`."""

    def __init__(self, code: str, **params: str | int) -> None:
        self.code = code
        self.params: dict[str, str | int] = params
        super().__init__(code)


def build_backup(session: Session) -> BackupDocument:
    patterns = (
        session.execute(
            select(Pattern)
            .where(Pattern.source_peer_id.is_(None))
            .options(
                selectinload(Pattern.palette_entries),
                selectinload(Pattern.grid),
                selectinload(Pattern.progress),
            )
        )
        .scalars()
        .all()
    )

    events_by_pattern: dict[str, list[ProgressEvent]] = {}
    for event in session.execute(select(ProgressEvent).order_by(ProgressEvent.id)).scalars():
        events_by_pattern.setdefault(event.pattern_id, []).append(event)

    recipes = session.execute(select(Recipe).order_by(Recipe.created_at)).scalars().all()
    users = session.execute(select(User).order_by(User.created_at)).scalars().all()
    requests = (
        session.execute(
            select(SharedRequest)
            .where(SharedRequest.source_peer_id.is_(None))
            .order_by(SharedRequest.created_at)
        )
        .scalars()
        .all()
    )

    return BackupDocument(
        format=FORMAT,
        format_version=FORMAT_VERSION,
        generated_at=datetime.now(UTC),
        users=[_dump_user(user) for user in users],
        patterns=[
            _dump_pattern(pattern, events_by_pattern.get(pattern.id, [])) for pattern in patterns
        ],
        recipes=[_dump_recipe(recipe) for recipe in recipes],
        shared_requests=[_dump_request(request) for request in requests],
    )


def _dump_user(user: User) -> BackupUser:
    return BackupUser(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role="admin" if user.role == "admin" else "user",
        password_hash=user.password_hash,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _dump_pattern(pattern: Pattern, events: list[ProgressEvent]) -> BackupPattern:
    return BackupPattern(
        id=pattern.id,
        owner_id=pattern.owner_id,
        name=pattern.name,
        source_filename=pattern.source_filename,
        source_sha256=pattern.source_sha256,
        width=pattern.width,
        height=pattern.height,
        fabric_count=pattern.fabric_count,
        created_at=pattern.created_at,
        updated_at=pattern.updated_at,
        import_config_json=pattern.import_config_json,
        recipe_id=pattern.recipe_id,
        notes=pattern.notes,
        labels=labels_from_json(pattern.labels_json),
        library=pattern.library,  # type: ignore[arg-type]
        revision=pattern.revision,
        contributed_by=pattern.contributed_by,
        origin_pattern_id=pattern.origin_pattern_id,
        origin_revision=pattern.origin_revision,
        palette=[dump_palette_entry(entry) for entry in pattern.palette_entries],
        grid=dump_grid(pattern.grid) if pattern.grid is not None else None,
        progress=_dump_progress(pattern.progress) if pattern.progress is not None else None,
        progress_events=[_dump_event(event) for event in events],
    )


def _dump_request(request: SharedRequest) -> BackupSharedRequest:
    return BackupSharedRequest(
        id=request.id,
        kind=request.kind,  # type: ignore[arg-type]
        status=request.status,  # type: ignore[arg-type]
        shared_pattern_id=request.shared_pattern_id,
        pattern_name=request.pattern_name,
        requested_by=request.requested_by,
        message=request.message,
        proposal_pattern_id=request.proposal_pattern_id,
        resolved_by=request.resolved_by,
        created_at=request.created_at,
        resolved_at=request.resolved_at,
    )


def dump_palette_entry(entry: PaletteEntry) -> BackupPaletteEntry:
    return BackupPaletteEntry(
        id=entry.id,
        index_in_grid=entry.index_in_grid,
        brand=entry.brand,
        code=entry.code,
        name=entry.name,
        rgb_hex=entry.rgb_hex,
        symbol_key=entry.symbol_key,
        symbol_svg=entry.symbol_svg,
        strands_full=entry.strands_full,
        strands_back=entry.strands_back,
        count_full=entry.count_full,
        count_half=entry.count_half,
        count_quarter=entry.count_quarter,
        count_three_quarter=entry.count_three_quarter,
        count_french=entry.count_french,
        count_beads=entry.count_beads,
        backstitch_length_cm=entry.backstitch_length_cm,
    )


def palette_entry_from(
    entry: BackupPaletteEntry, pattern_id: str, *, keep_id: bool = False
) -> PaletteEntry:
    """A palette row from its serialised form — a backup's, or a pattern
    received from a paired instance (`app/federation.py`, which gives it a
    fresh id of this instance's own)."""
    return PaletteEntry(
        id=entry.id if keep_id else uuid.uuid4().hex,
        pattern_id=pattern_id,
        index_in_grid=entry.index_in_grid,
        brand=entry.brand,
        code=entry.code,
        name=entry.name,
        rgb_hex=entry.rgb_hex,
        symbol_key=entry.symbol_key,
        symbol_svg=entry.symbol_svg,
        strands_full=entry.strands_full,
        strands_back=entry.strands_back,
        count_full=entry.count_full,
        count_half=entry.count_half,
        count_quarter=entry.count_quarter,
        count_three_quarter=entry.count_three_quarter,
        count_french=entry.count_french,
        count_beads=entry.count_beads,
        backstitch_length_cm=entry.backstitch_length_cm,
    )


def _legacy_quarter_cells(grid: BackupGrid) -> list[tuple[int, int]]:
    """(cell index, palette index) of each 1/4 stitch of a format 1-3 grid —
    a cell layer then, without a corner — in row order."""
    if grid.layer_quarter is None:
        return []
    cells = decode_uint16_layer(base64_to_bytes(grid.layer_quarter))
    return [(index, value) for index, value in enumerate(cells) if value]


def _quarter_json(grid: BackupGrid, width: int) -> str:
    legacy = _legacy_quarter_cells(grid)
    if not legacy:
        return grid.quarter_json
    # Top-left: where a 1/4 stitch without a corner was always drawn.
    return json.dumps(
        [
            {"x": index % width, "y": index // width, "corner": "tl", "palette_index": value}
            for index, value in legacy
        ]
    )


def _upgrade_legacy_quarters(pattern_data: BackupPattern) -> None:
    """A format 1-3 pattern's checked 1/4 stitches and logged 1/4 operations
    were per cell: move them to the index of the item made for that cell
    (`_quarter_json`), so no progress and no activity is lost."""
    legacy = (
        _legacy_quarter_cells(pattern_data.grid) if pattern_data.grid is not None else []
    )
    if not legacy:
        return
    item_of_cell = {cell: item for item, (cell, _value) in enumerate(legacy)}

    progress = pattern_data.progress
    if progress is not None and progress.bitmap_quarter is not None:
        old = base64_to_bytes(progress.bitmap_quarter)
        new = bytearray(bitmap_byte_length(len(legacy)))
        for cell, item in item_of_cell.items():
            if cell < len(old) * 8 and get_bit(old, cell):
                set_bit(new, item, True)
        progress.bitmap_quarter = bytes_to_base64(bytes(new))

    for event in pattern_data.progress_events:
        ops = json.loads(event.ops_json)
        upgraded = []
        for op in ops:
            if op.get("layer") == "quarter":
                if op["index"] not in item_of_cell:
                    continue
                op = {**op, "index": item_of_cell[op["index"]]}
            upgraded.append(op)
        event.ops_json = json.dumps(upgraded)


def grid_from(grid: BackupGrid, pattern_id: str, width: int) -> Grid:
    return Grid(
        pattern_id=pattern_id,
        layer_full=base64_to_bytes(grid.layer_full),
        layer_half=base64_to_bytes(grid.layer_half) if grid.layer_half is not None else None,
        quarter_json=_quarter_json(grid, width),
        three_quarter_json=grid.three_quarter_json,
        backstitch_json=grid.backstitch_json,
        french_knots_json=grid.french_knots_json,
        encoding=grid.encoding,
        version=grid.version,
    )


def dump_grid(grid: Grid) -> BackupGrid:
    return BackupGrid(
        layer_full=bytes_to_base64(grid.layer_full),
        layer_half=bytes_to_base64(grid.layer_half) if grid.layer_half is not None else None,
        quarter_json=grid.quarter_json,
        three_quarter_json=grid.three_quarter_json,
        backstitch_json=grid.backstitch_json,
        french_knots_json=grid.french_knots_json,
        encoding=grid.encoding,
        version=grid.version,
    )


def _dump_progress(progress: Progress) -> BackupProgress:
    return BackupProgress(
        bitmap=bytes_to_base64(progress.bitmap),
        bitmap_half=bytes_to_base64(progress.bitmap_half)
        if progress.bitmap_half is not None
        else None,
        bitmap_quarter=bytes_to_base64(progress.bitmap_quarter)
        if progress.bitmap_quarter is not None
        else None,
        bitmap_three_quarter=bytes_to_base64(progress.bitmap_three_quarter)
        if progress.bitmap_three_quarter is not None
        else None,
        bitmap_backstitch=bytes_to_base64(progress.bitmap_backstitch)
        if progress.bitmap_backstitch is not None
        else None,
        bitmap_knots=bytes_to_base64(progress.bitmap_knots)
        if progress.bitmap_knots is not None
        else None,
        version=progress.version,
        stitched_count=progress.stitched_count,
        updated_at=progress.updated_at,
    )


def _dump_event(event: ProgressEvent) -> BackupProgressEvent:
    return BackupProgressEvent(
        id=event.id, ts=event.ts, ops_json=event.ops_json, version_after=event.version_after
    )


def _dump_recipe(recipe: Recipe) -> BackupRecipe:
    return BackupRecipe(
        id=recipe.id,
        fingerprint=recipe.fingerprint,
        label=recipe.label,
        grid_type=recipe.grid_type,
        config_json=recipe.config_json,
        created_at=recipe.created_at,
        usage_count=recipe.usage_count,
    )


def restore_backup(
    session: Session, document: BackupDocument, *, restored_by: User
) -> BackupRestoreSummary:
    """Replace the instance's data with `document`.

    `restored_by` is the admin running the restore: owner of every pattern of
    a version 1 document, and of any pattern whose owner the document does
    not contain."""
    if document.format != FORMAT:
        raise BackupFormatError("backup_unexpected_format", got=document.format, expected=FORMAT)
    if document.format_version not in SUPPORTED_VERSIONS:
        raise BackupFormatError(
            "backup_unsupported_version",
            got=document.format_version,
            expected=FORMAT_VERSION,
        )
    if document.users is not None and not any(u.role == "admin" for u in document.users):
        # Restoring it would leave nobody able to manage profiles.
        raise BackupFormatError("backup_without_admin")

    # Deleting the patterns cascades in SQLite (`PRAGMA foreign_keys=ON`,
    # `app/db.py`) to their palette, grid, progress and associated event log
    # — never a special case to write here.
    shared_before = {
        pattern_id
        for (pattern_id,) in session.execute(
            select(Pattern.id).where(
                Pattern.library == "shared", Pattern.source_peer_id.is_(None)
            )
        )
    }
    session.execute(delete(SharedRequest))
    session.execute(delete(Pattern))
    session.execute(delete(Recipe))

    if document.users is not None:
        _replace_users(session, document.users)
    known_owners = {user_id for (user_id,) in session.execute(select(User.id))}
    if restored_by.id in known_owners:
        default_owner: str | None = restored_by.id
    else:
        default_owner = session.execute(
            select(User.id).where(User.role == "admin").order_by(User.created_at).limit(1)
        ).scalar_one_or_none()

    def known(user_id: str | None) -> str | None:
        return user_id if user_id in known_owners else None

    for pattern_data in document.patterns:
        personal = pattern_data.library == "personal"
        owner_id = pattern_data.owner_id
        if personal and (owner_id is None or owner_id not in known_owners):
            owner_id = default_owner
        pattern = Pattern(
            id=pattern_data.id,
            # Shared and proposal patterns belong to nobody (`app/models.py`).
            owner_id=owner_id if personal else None,
            library=pattern_data.library,
            revision=pattern_data.revision,
            contributed_by=known(pattern_data.contributed_by),
            # Links between patterns are set once they all exist (below):
            # SQLite checks a foreign key at each insert.
            origin_pattern_id=None,
            origin_revision=pattern_data.origin_revision,
            name=pattern_data.name,
            source_filename=pattern_data.source_filename,
            source_sha256=pattern_data.source_sha256,
            width=pattern_data.width,
            height=pattern_data.height,
            fabric_count=pattern_data.fabric_count,
            created_at=pattern_data.created_at,
            updated_at=pattern_data.updated_at,
            import_config_json=pattern_data.import_config_json,
            recipe_id=pattern_data.recipe_id,
            notes=pattern_data.notes,
            labels_json=labels_to_json(pattern_data.labels),
        )
        session.add(pattern)

        for entry in pattern_data.palette:
            session.add(palette_entry_from(entry, pattern.id, keep_id=True))

        _upgrade_legacy_quarters(pattern_data)
        if pattern_data.grid is not None:
            session.add(grid_from(pattern_data.grid, pattern.id, pattern_data.width))

        if pattern_data.progress is not None:
            progress = pattern_data.progress
            session.add(
                Progress(
                    pattern_id=pattern.id,
                    bitmap=base64_to_bytes(progress.bitmap),
                    bitmap_half=base64_to_bytes(progress.bitmap_half)
                    if progress.bitmap_half is not None
                    else None,
                    bitmap_quarter=base64_to_bytes(progress.bitmap_quarter)
                    if progress.bitmap_quarter is not None
                    else None,
                    bitmap_three_quarter=base64_to_bytes(progress.bitmap_three_quarter)
                    if progress.bitmap_three_quarter is not None
                    else None,
                    bitmap_backstitch=base64_to_bytes(progress.bitmap_backstitch)
                    if progress.bitmap_backstitch is not None
                    else None,
                    bitmap_knots=base64_to_bytes(progress.bitmap_knots)
                    if progress.bitmap_knots is not None
                    else None,
                    version=progress.version,
                    stitched_count=progress.stitched_count,
                    updated_at=progress.updated_at,
                )
            )

        for event in pattern_data.progress_events:
            session.add(
                ProgressEvent(
                    id=event.id,
                    pattern_id=pattern.id,
                    ts=event.ts,
                    ops_json=event.ops_json,
                    version_after=event.version_after,
                )
            )

    session.flush()
    restored_ids = {pattern_data.id for pattern_data in document.patterns}
    for pattern_data in document.patterns:
        if pattern_data.origin_pattern_id in restored_ids:
            restored = session.get(Pattern, pattern_data.id)
            assert restored is not None
            restored.origin_pattern_id = pattern_data.origin_pattern_id

    for request_data in document.shared_requests:
        session.add(
            SharedRequest(
                id=request_data.id,
                kind=request_data.kind,
                status=request_data.status,
                shared_pattern_id=request_data.shared_pattern_id
                if request_data.shared_pattern_id in restored_ids
                else None,
                pattern_name=request_data.pattern_name,
                requested_by=known(request_data.requested_by),
                message=request_data.message,
                proposal_pattern_id=request_data.proposal_pattern_id
                if request_data.proposal_pattern_id in restored_ids
                else None,
                resolved_by=known(request_data.resolved_by),
                created_at=request_data.created_at,
                resolved_at=request_data.resolved_at,
            )
        )

    for recipe_data in document.recipes:
        session.add(
            Recipe(
                id=recipe_data.id,
                fingerprint=recipe_data.fingerprint,
                label=recipe_data.label,
                grid_type=recipe_data.grid_type,
                config_json=recipe_data.config_json,
                created_at=recipe_data.created_at,
                usage_count=recipe_data.usage_count,
            )
        )

    _after_restore(session, shared_before)
    session.commit()

    return BackupRestoreSummary(
        users_count=len(document.users) if document.users is not None else 0,
        patterns_count=len(document.patterns),
        recipes_count=len(document.recipes),
        progress_events_count=sum(len(p.progress_events) for p in document.patterns),
    )


def _replace_users(session: Session, users: list[BackupUser]) -> None:
    """Make the profiles exactly those of the document. Profiles present on
    both sides are updated in place rather than deleted and re-created, so
    their sessions survive — the admin restoring a backup that contains
    them stays logged in. Removed profiles lose their sessions with them."""
    wanted = {user.id: user for user in users}
    for existing in session.execute(select(User)).scalars().all():
        if existing.id not in wanted:
            session.delete(existing)
    session.flush()
    for data in users:
        user = session.get(User, data.id)
        if user is None:
            user = User(id=data.id)
            session.add(user)
        user.email = data.email
        user.first_name = data.first_name
        user.last_name = data.last_name
        user.role = data.role
        user.password_hash = data.password_hash
        user.created_at = data.created_at
        user.updated_at = data.updated_at
    session.flush()


def _after_restore(session: Session, shared_before: set[str]) -> None:
    """Keep paired instances right after a restore (Lot 11b): a subscriber
    re-reads every restored shared pattern of this instance and drops those
    that are gone; this instance re-reads its hosts from the start, its
    mirrors having been deleted with every other pattern."""
    session.flush()
    restored = [
        pattern_id
        for (pattern_id,) in session.execute(
            select(Pattern.id).where(
                Pattern.library == "shared", Pattern.source_peer_id.is_(None)
            )
        )
    ]
    for pattern_id in restored:
        # A Core update, so the restored `updated_at` stays what the backup
        # says (the ORM's `onupdate` would set it to now).
        session.execute(
            update(Pattern)
            .where(Pattern.id == pattern_id)
            .values(shared_seq=next_seq(session), updated_at=Pattern.updated_at)
        )
    for gone in shared_before - set(restored):
        session.merge(SharedTombstone(pattern_id=gone, seq=next_seq(session)))
    for peer in session.execute(select(Peer).where(Peer.role == "host")).scalars():
        peer.cursor = 0

