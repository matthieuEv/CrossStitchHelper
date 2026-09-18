"""Export `.cshp` — format ouvert documenté (cahier des charges §6.4, Lot 2).

Une archive ZIP autonome, lisible sans cette application : c'est la garantie
que l'utilisateur n'est jamais captif de CrossStitchHelper (leçon citée du
format Cross Stitch Markup, §6.4). `grid.bin` et `progress.bin` sont les
octets bruts déjà stockés en base (§6.1) — aucune conversion, aucune perte.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from app.models import Grid, PaletteEntry, Pattern, Progress

FORMAT_VERSION = 2

_README = f"""CrossStitchHelper — archive .cshp (format ouvert, version {FORMAT_VERSION})

Cette archive ZIP contient tout un motif de point de croix : ses métadonnées,
sa palette, sa grille et votre progression. Elle ne dépend d'aucun logiciel
particulier pour être relue.

Fichiers :

- pattern.json   Métadonnées, palette et segments (point arrière, nœuds),
                  en JSON. Décrit aussi le format des fichiers binaires
                  ci-dessous (largeur, hauteur, encodage), et lequel de ces
                  fichiers est présent dans cette archive précise.

- grid.bin        La grille des points entiers, une case par valeur : un
                  entier non signé sur 16 bits, little-endian, ligne par
                  ligne de haut en bas et de gauche à droite. 0 = case vide ;
                  sinon, l'entier est l'index (1-based) de la couleur dans
                  `pattern.json` (palette[index - 1]).

- grid_half.bin, grid_quarter.bin (Lot 8, présents seulement si ce motif a
                  des points 1/2 ou 1/4) — même format que grid.bin.

- progress.bin    Votre progression sur les points entiers, un bit par case,
                  même ordre de parcours que grid.bin (bit de poids faible en
                  premier dans chaque octet). 1 = case brodée.

- progress_half.bin, progress_quarter.bin (Lot 8, présents avec les fichiers
                  grid_*.bin correspondants) — même format que progress.bin.

- progress_backstitch.bin, progress_knots.bin (Lot 8, présents si ce motif a
                  des segments de point arrière / des nœuds) — un bit par
                  élément de `pattern.json` → `segments.backstitch` /
                  `segments.french_knots`, dans le même ordre (jamais un bit
                  par case : ce ne sont pas des grilles).

Pour re-générer une grille en une matrice lisible depuis un fichier grid*.bin
et pattern.json, à peu près n'importe quel langage suffit : lire les entiers
en uint16 little-endian, `width * height` d'entre eux, et les reformer en
`height` lignes de `width` valeurs.
"""


def build_cshp_archive(
    pattern: Pattern,
    palette_entries: list[PaletteEntry],
    grid: Grid,
    progress: Progress,
) -> bytes:
    pattern_json = {
        "format": "cshp",
        "format_version": FORMAT_VERSION,
        "pattern": {
            "id": pattern.id,
            "name": pattern.name,
            "width": pattern.width,
            "height": pattern.height,
            "fabric_count": pattern.fabric_count,
            "source_filename": pattern.source_filename,
            "notes": pattern.notes,
            "created_at": _isoformat(pattern.created_at),
            "updated_at": _isoformat(pattern.updated_at),
        },
        "palette": [
            {
                "index_in_grid": entry.index_in_grid,
                "brand": entry.brand,
                "code": entry.code,
                "name": entry.name,
                "rgb_hex": entry.rgb_hex,
                "symbol_key": entry.symbol_key,
                "symbol_svg": entry.symbol_svg,
                "strands_full": entry.strands_full,
                "strands_back": entry.strands_back,
                "count_full": entry.count_full,
                "count_half": entry.count_half,
                "count_quarter": entry.count_quarter,
                "count_french": entry.count_french,
                "count_beads": entry.count_beads,
                "backstitch_length_cm": entry.backstitch_length_cm,
            }
            for entry in palette_entries
        ],
        "segments": {
            "backstitch": json.loads(grid.backstitch_json),
            "french_knots": json.loads(grid.french_knots_json),
        },
        "grid": {
            "file": "grid.bin",
            "encoding": grid.encoding,
            "width": pattern.width,
            "height": pattern.height,
            "version": grid.version,
            "half_file": "grid_half.bin" if grid.layer_half is not None else None,
            "quarter_file": "grid_quarter.bin" if grid.layer_quarter is not None else None,
        },
        "progress": {
            "file": "progress.bin",
            "version": progress.version,
            "stitched_count": progress.stitched_count,
            "half_file": "progress_half.bin" if progress.bitmap_half is not None else None,
            "quarter_file": "progress_quarter.bin" if progress.bitmap_quarter is not None else None,
            "backstitch_file": "progress_backstitch.bin"
            if progress.bitmap_backstitch is not None
            else None,
            "knots_file": "progress_knots.bin" if progress.bitmap_knots is not None else None,
        },
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pattern.json", json.dumps(pattern_json, ensure_ascii=False, indent=2))
        archive.writestr("grid.bin", grid.layer_full)
        archive.writestr("progress.bin", progress.bitmap)
        if grid.layer_half is not None:
            archive.writestr("grid_half.bin", grid.layer_half)
        if grid.layer_quarter is not None:
            archive.writestr("grid_quarter.bin", grid.layer_quarter)
        if progress.bitmap_half is not None:
            archive.writestr("progress_half.bin", progress.bitmap_half)
        if progress.bitmap_quarter is not None:
            archive.writestr("progress_quarter.bin", progress.bitmap_quarter)
        if progress.bitmap_backstitch is not None:
            archive.writestr("progress_backstitch.bin", progress.bitmap_backstitch)
        if progress.bitmap_knots is not None:
            archive.writestr("progress_knots.bin", progress.bitmap_knots)
        archive.writestr("README.txt", _README)
    return buffer.getvalue()


def _isoformat(value: datetime) -> str:
    return value.isoformat()
