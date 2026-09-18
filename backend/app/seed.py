"""Motif de démonstration pour les tests de performance (Lot 1).

Le roadmap (`docs/roadmap.md`, Lot 1) demande une grille de 255 × 180 cases
injectée directement en base — le moteur d'extraction (Lots 4 à 7) n'existe
pas encore, donc rien ne peut créer un motif réaliste de cette taille
autrement. Le dessin lui-même n'a aucune importance : seule sa taille
(45 900 cases, la taille de référence citée dans `CLAUDE.md`) compte, pour
vérifier le rendu canvas et la synchronisation de progression à l'échelle
réelle.

Génération déterministe (graine fixe) : le même motif à chaque exécution du
script.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.codec import bitmap_byte_length, bitmap_from_indices, encode_uint16_layer, set_bit
from app.models import Grid, PaletteEntry, Pattern, Progress

DEMO_PATTERN_ID = "demo-perf-255x180"
WIDTH = 255
HEIGHT = 180

# Centre du motif (voir `_build_cells`) — les points spéciaux (Lot 8) s'y
# regroupent en un petit motif décoratif, pour que la fonctionnalité soit
# visible sans avoir à chercher où dans une grille de 45 900 cases.
_CX, _CY = WIDTH // 2, HEIGHT // 2

# Palette purement synthétique (jamais de contenu créatif réel importé,
# conformément à CLAUDE.md — c'est un motif géométrique généré, pas une
# œuvre transcrite).
_PALETTE = [
    ("310", "Noir", "#2b2b2b", "▲"),
    ("permanent", "Blanc cassé", "#f3ede0", "·"),
    ("816", "Rouge grenat", "#7c1f2b", "x"),
    ("947", "Orange brûlé", "#e2632a", "o"),
    ("725", "Jaune moyen", "#f0c33c", ":"),
    ("906", "Vert parrot clair", "#7fae3a", "="),
    ("909", "Vert émeraude très foncé", "#1f6b45", "\\"),
    ("798", "Bleu delft foncé", "#2c5f8a", "/"),
    ("333", "Violet très foncé", "#5b4b8a", "■"),
    ("3803", "Rose mauve très foncé", "#8a3b5e", "◆"),
    ("415", "Gris perle", "#b9bcbe", "∨"),
    ("permanent-2", "Bleu ciel clair", "#bcd9ea", "≡"),
]


def _seeded_random(seed: int) -> Iterator[float]:
    state = seed
    while True:
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        yield state / 0x7FFFFFFF


def _build_cells() -> list[int]:
    """Dessine des anneaux concentriques + une bordure — un motif purement
    géométrique, rapide à générer, sans dépendance de rendu de texte."""
    cells = [0] * (WIDTH * HEIGHT)
    cx, cy = WIDTH / 2, HEIGHT / 2
    palette_count = len(_PALETTE)
    random = _seeded_random(20260914)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Bordure : cadre plein sur les 3 dernières cases de chaque bord.
            if x < 3 or x >= WIDTH - 3 or y < 3 or y >= HEIGHT - 3:
                cells[y * WIDTH + x] = 1  # noir
                continue

            dx = (x - cx) / (WIDTH / 2)
            dy = (y - cy) / (HEIGHT / 2)
            radius = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)

            # Anneaux + légère modulation angulaire, pour un dessin non
            # trivialement répétitif tout en restant bon marché à calculer.
            ring = int(radius * 14 + math.sin(angle * 6) * 1.3)
            if ring % 4 == 0:
                continue  # case vide : laisse « respirer » le motif

            index = 2 + (ring + int(angle * 3)) % (palette_count - 2)
            # Un peu de grain pseudo-aléatoire pour éviter des anneaux trop nets.
            if next(random) < 0.04:
                index = 2 + (index + 1) % (palette_count - 2)
            cells[y * WIDTH + x] = index

    return cells


# Index de palette (1-based, voir `_PALETTE`) réutilisés pour les points
# spéciaux du Lot 8 — aucune nouvelle couleur : les mêmes fils qui composent
# déjà les anneaux, pour ne pas gonfler la légende du motif de démonstration.
_QUARTER_INDEX = 3  # 816, rouge grenat
_HALF_INDEX = 8  # 798, bleu delft foncé
_BACKSTITCH_INDEX = 1  # 310, noir — convention courante pour un contour
_KNOT_INDEX = 10  # 3803, rose mauve très foncé

# Décalages (dx, dy) depuis le centre (`_CX`, `_CY`) — un petit motif
# décoratif purement géométrique (pas de contenu créatif réel, CLAUDE.md),
# choisi pour que les cinq catégories de points soient toutes visibles
# groupées au même endroit plutôt que dispersées dans les 45 900 cases.
_QUARTER_OFFSETS = [
    (-18, -5), (-16, -8), (-14, -11), (14, -11), (16, -8), (18, -5),
    (-18, 5), (-16, 8), (-14, 11), (14, 11), (16, 8), (18, 5),
]  # fmt: skip
_HALF_OFFSETS = [
    (-10, -14), (-6, -16), (0, -17), (6, -16), (10, -14),
    (-10, 14), (-6, 16), (0, 17), (6, 16), (10, 14),
]  # fmt: skip


def _build_special_stitches(
    cell_count: int,
) -> tuple[list[int], list[int], list[dict[str, float | int]], list[dict[str, float | int]]]:
    """Construit, autour du centre du motif, un petit losange en point
    arrière entourant quelques points 1/2, 1/4 et des nœuds — de quoi
    exercer réellement les cinq catégories de points du Lot 8 (aucun
    connecteur d'extraction ne les produit encore, voir Lot 9 : sans ce
    contenu synthétique, l'interface bâtie ici n'aurait jamais rien à
    afficher tant que ce lot futur n'existe pas).

    Renvoie ``(quarter_cells, half_cells, backstitch, french_knots)`` —
    les deux premiers dans la même convention que `_build_cells` (une
    valeur par case, 0 = vide), les deux derniers déjà au format JSON
    attendu par `Grid.backstitch_json`/`french_knots_json`
    (`app/schemas.py::BackstitchSegment`/`FrenchKnot` pour la convention de
    coordonnées : coins de case pour l'un, centre de case pour l'autre)."""
    quarter_cells = [0] * cell_count
    for dx, dy in _QUARTER_OFFSETS:
        quarter_cells[(_CY + dy) * WIDTH + (_CX + dx)] = _QUARTER_INDEX

    half_cells = [0] * cell_count
    for dx, dy in _HALF_OFFSETS:
        half_cells[(_CY + dy) * WIDTH + (_CX + dx)] = _HALF_INDEX

    top, right, bottom, left = (
        (_CX, _CY - 15),
        (_CX + 15, _CY),
        (_CX, _CY + 15),
        (_CX - 15, _CY),
    )
    backstitch: list[dict[str, float | int]] = [
        {"x1": p1[0], "y1": p1[1], "x2": p2[0], "y2": p2[1], "palette_index": _BACKSTITCH_INDEX}
        for p1, p2 in [(top, right), (right, bottom), (bottom, left), (left, top)]
    ]

    knot_cells = [
        (0, -20), (-6, -3), (5, -2), (-4, 6), (6, 7), (0, 20),
    ]  # fmt: skip
    french_knots: list[dict[str, float | int]] = [
        {"x": _CX + dx + 0.5, "y": _CY + dy + 0.5, "palette_index": _KNOT_INDEX}
        for dx, dy in knot_cells
    ]

    return quarter_cells, half_cells, backstitch, french_knots


def seed_demo_pattern(session: Session, *, force: bool = False) -> Pattern:
    """Insère (ou remplace, si `force`) le motif de démonstration 255 × 180.

    Idempotent par défaut : si le motif existe déjà, il est renvoyé tel
    quel — un ré-import ne doit jamais écraser une progression déjà cochée
    (contrainte structurante de `CLAUDE.md`).
    """
    existing = session.get(Pattern, DEMO_PATTERN_ID)
    if existing is not None and not force:
        return existing
    if existing is not None and force:
        session.delete(existing)
        session.flush()

    now = datetime.now(UTC)
    cells = _build_cells()
    cell_count = WIDTH * HEIGHT
    quarter_cells, half_cells, backstitch, french_knots = _build_special_stitches(cell_count)

    pattern = Pattern(
        id=DEMO_PATTERN_ID,
        owner_id=None,
        name="Démonstration — anneaux 255×180",
        source_filename=None,
        source_sha256=None,
        width=WIDTH,
        height=HEIGHT,
        fabric_count=14,
        created_at=now,
        updated_at=now,
        import_config_json=None,
        recipe_id=None,
        notes="Motif synthétique pour les tests de performance du rendu (Lot 1).",
    )
    session.add(pattern)

    backstitch_length_by_index: dict[int, float] = {}
    for segment in backstitch:
        length = math.hypot(segment["x2"] - segment["x1"], segment["y2"] - segment["y1"])
        backstitch_length_by_index[int(segment["palette_index"])] = (
            backstitch_length_by_index.get(int(segment["palette_index"]), 0.0) + length
        )

    for position, (code, name, hex_color, symbol) in enumerate(_PALETTE):
        index_in_grid = position + 1
        # Longueur de point arrière en cm : purement indicative ici (fabric_count
        # 14, 1 case ≈ 1/14 pouce ≈ 0,181 cm) — jamais consommée par un calcul,
        # seulement affichée (§7.3).
        length_cells = backstitch_length_by_index.get(index_in_grid)
        session.add(
            PaletteEntry(
                id=uuid.uuid4().hex,
                pattern_id=pattern.id,
                index_in_grid=index_in_grid,
                brand="DMC",
                code=code,
                name=name,
                rgb_hex=hex_color,
                symbol_key=symbol,
                symbol_svg=None,
                strands_full=2,
                strands_back=1,
                count_full=sum(1 for value in cells if value == index_in_grid),
                count_half=sum(1 for value in half_cells if value == index_in_grid),
                count_quarter=sum(1 for value in quarter_cells if value == index_in_grid),
                count_french=sum(
                    1 for knot in french_knots if knot["palette_index"] == index_in_grid
                ),
                count_beads=0,
                backstitch_length_cm=(length_cells * 2.54 / 14) if length_cells else None,
            )
        )

    session.add(
        Grid(
            pattern_id=pattern.id,
            layer_full=encode_uint16_layer(cells),
            layer_half=encode_uint16_layer(half_cells),
            layer_quarter=encode_uint16_layer(quarter_cells),
            backstitch_json=json.dumps(backstitch),
            french_knots_json=json.dumps(french_knots),
            encoding="uint16le",
            version=1,
        )
    )

    # Progression de départ : le cadre extérieur déjà brodé (points entiers),
    # et pour chaque catégorie spéciale une partie déjà cochée — un motif ni
    # vide ni terminé à l'ouverture, et la preuve que chaque bitmap se
    # persiste et se recharge correctement dès le seed, pas seulement après
    # une première synchronisation manuelle.
    stitched_indices = [i for i, value in enumerate(cells) if value == 1]
    half_done = [i for i, value in enumerate(half_cells) if value != 0][:5]
    quarter_done = [i for i, value in enumerate(quarter_cells) if value != 0][:6]
    backstitch_done = [0, 1]
    knots_done = [0, 2, 4]
    session.add(
        Progress(
            pattern_id=pattern.id,
            bitmap=bitmap_from_indices(stitched_indices, cell_count),
            bitmap_half=bitmap_from_indices(half_done, cell_count),
            bitmap_quarter=bitmap_from_indices(quarter_done, cell_count),
            bitmap_backstitch=_partial_bitmap(backstitch_done, len(backstitch)),
            bitmap_knots=_partial_bitmap(knots_done, len(french_knots)),
            version=1,
            stitched_count=len(stitched_indices),
            updated_at=now,
        )
    )

    session.commit()
    session.refresh(pattern)
    return pattern


def _partial_bitmap(done_indices: list[int], element_count: int) -> bytes:
    """Comme `bitmap_from_indices`, mais pour un bitmap dimensionné sur un
    nombre d'éléments (segments de point arrière, nœuds) plutôt que sur la
    grille — `bitmap_from_indices` suppose implicitement un bitmap de la
    taille de la grille entière, ce qui serait faux (et coûteux en octets
    pour rien) pour ces deux catégories."""
    bitmap = bytearray(bitmap_byte_length(element_count))
    for index in done_indices:
        set_bit(bitmap, index, True)
    return bytes(bitmap)
