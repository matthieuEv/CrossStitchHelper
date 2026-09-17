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

FORMAT_VERSION = 1

_README = f"""CrossStitchHelper — archive .cshp (format ouvert, version {FORMAT_VERSION})

Cette archive ZIP contient tout un motif de point de croix : ses métadonnées,
sa palette, sa grille et votre progression. Elle ne dépend d'aucun logiciel
particulier pour être relue.

Fichiers :

- pattern.json   Métadonnées, palette et segments (point arrière, nœuds),
                  en JSON. Décrit aussi le format des deux fichiers binaires
                  ci-dessous (largeur, hauteur, encodage).

- grid.bin        La grille, une case par valeur : un entier non signé sur
                  16 bits, little-endian, ligne par ligne de haut en bas et
                  de gauche à droite. 0 = case vide ; sinon, l'entier est
                  l'index (1-based) de la couleur dans `pattern.json`
                  (palette[index - 1]).

- progress.bin    Votre progression, un bit par case, même ordre de parcours
                  que grid.bin (bit de poids faible en premier dans chaque
                  octet). 1 = case brodée.

Pour re-générer la grille en une matrice lisible depuis grid.bin et
pattern.json, à peu près n'importe quel langage suffit : lire les entiers en
uint16 little-endian, `width * height` d'entre eux, et les reformer en
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
        },
        "progress": {
            "file": "progress.bin",
            "version": progress.version,
            "stitched_count": progress.stitched_count,
        },
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pattern.json", json.dumps(pattern_json, ensure_ascii=False, indent=2))
        archive.writestr("grid.bin", grid.layer_full)
        archive.writestr("progress.bin", progress.bitmap)
        archive.writestr("README.txt", _README)
    return buffer.getvalue()


def _isoformat(value: datetime) -> str:
    return value.isoformat()
