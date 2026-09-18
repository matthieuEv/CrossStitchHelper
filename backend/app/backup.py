"""Sauvegarde/restauration complète des données (Lot 8, cahier des charges §7.5).

Distinct de l'export `.cshp` (`app/export_cshp.py`, Lot 2) qui ne couvre
qu'un seul motif : celui-ci couvre toute l'instance — tous les motifs, leur
palette, leur grille, leur progression, le journal `progress_events` (sans
lequel l'historique d'activité, §11, disparaîtrait d'une restauration), et
les recettes réutilisables (Lot 6). Format JSON (pas une archive ZIP comme
`.cshp`) : c'est ce qu'annonce déjà le bouton « Exporter (.json) » des
réglages (§7.5, figé au portage des maquettes), et un utilisateur qui n'a
accès qu'à son téléphone doit pouvoir l'ouvrir/l'inspecter sans outil
supplémentaire. Les champs binaires suivent la même convention base64 que le
reste de l'API (`app/codec.py`), jamais les octets bruts d'un ZIP.

Volontairement hors périmètre : ``ImportJob`` (état transitoire d'un
assistant d'import en cours, jamais une donnée durable — voir
`app/models.py`) et ``AppMeta`` (bookkeeping interne, pas une donnée
utilisateur).

Une restauration est un **remplacement complet**, jamais une fusion : c'est
la sémantique attendue d'une « restauration » (par opposition à un
« import »), et cela évite toute ambiguïté sur les identifiants en conflit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.codec import base64_to_bytes, bytes_to_base64
from app.models import Grid, PaletteEntry, Pattern, Progress, ProgressEvent, Recipe
from app.schemas import (
    BackupDocument,
    BackupGrid,
    BackupPaletteEntry,
    BackupPattern,
    BackupProgress,
    BackupProgressEvent,
    BackupRecipe,
    BackupRestoreSummary,
)

FORMAT: Literal["csh-backup"] = "csh-backup"
FORMAT_VERSION = 1


class BackupFormatError(ValueError):
    """Le document fourni n'est pas une sauvegarde CrossStitchHelper reconnue,
    ou une version de format que cette instance ne sait pas lire."""


def build_backup(session: Session) -> BackupDocument:
    patterns = (
        session.execute(
            select(Pattern).options(
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

    return BackupDocument(
        format=FORMAT,
        format_version=FORMAT_VERSION,
        generated_at=datetime.now(UTC),
        patterns=[
            _dump_pattern(pattern, events_by_pattern.get(pattern.id, [])) for pattern in patterns
        ],
        recipes=[_dump_recipe(recipe) for recipe in recipes],
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
        palette=[_dump_palette_entry(entry) for entry in pattern.palette_entries],
        grid=_dump_grid(pattern.grid) if pattern.grid is not None else None,
        progress=_dump_progress(pattern.progress) if pattern.progress is not None else None,
        progress_events=[_dump_event(event) for event in events],
    )


def _dump_palette_entry(entry: PaletteEntry) -> BackupPaletteEntry:
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
        count_french=entry.count_french,
        count_beads=entry.count_beads,
        backstitch_length_cm=entry.backstitch_length_cm,
    )


def _dump_grid(grid: Grid) -> BackupGrid:
    return BackupGrid(
        layer_full=bytes_to_base64(grid.layer_full),
        layer_half=bytes_to_base64(grid.layer_half) if grid.layer_half is not None else None,
        layer_quarter=bytes_to_base64(grid.layer_quarter)
        if grid.layer_quarter is not None
        else None,
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


def restore_backup(session: Session, document: BackupDocument) -> BackupRestoreSummary:
    if document.format != FORMAT:
        raise BackupFormatError(f"Format inattendu : {document.format!r} (attendu {FORMAT!r}).")
    if document.format_version != FORMAT_VERSION:
        raise BackupFormatError(
            f"Version de sauvegarde non prise en charge : {document.format_version} "
            f"(cette instance sait lire la version {FORMAT_VERSION})."
        )

    # Suppression des motifs : entraîne par cascade SQLite (`PRAGMA
    # foreign_keys=ON`, `app/db.py`) celle de leur palette, grille,
    # progression et journal d'événements associés — jamais un cas
    # particulier à écrire ici.
    session.execute(delete(Pattern))
    session.execute(delete(Recipe))

    for pattern_data in document.patterns:
        pattern = Pattern(
            id=pattern_data.id,
            owner_id=pattern_data.owner_id,
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
        )
        session.add(pattern)

        for entry in pattern_data.palette:
            session.add(
                PaletteEntry(
                    id=entry.id,
                    pattern_id=pattern.id,
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
                    count_french=entry.count_french,
                    count_beads=entry.count_beads,
                    backstitch_length_cm=entry.backstitch_length_cm,
                )
            )

        if pattern_data.grid is not None:
            grid = pattern_data.grid
            session.add(
                Grid(
                    pattern_id=pattern.id,
                    layer_full=base64_to_bytes(grid.layer_full),
                    layer_half=base64_to_bytes(grid.layer_half)
                    if grid.layer_half is not None
                    else None,
                    layer_quarter=base64_to_bytes(grid.layer_quarter)
                    if grid.layer_quarter is not None
                    else None,
                    backstitch_json=grid.backstitch_json,
                    french_knots_json=grid.french_knots_json,
                    encoding=grid.encoding,
                    version=grid.version,
                )
            )

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

    session.commit()

    return BackupRestoreSummary(
        patterns_count=len(document.patterns),
        recipes_count=len(document.recipes),
        progress_events_count=sum(len(p.progress_events) for p in document.patterns),
    )
