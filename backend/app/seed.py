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

import math
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.codec import bitmap_from_indices, encode_uint16_layer
from app.models import Grid, PaletteEntry, Pattern, Progress

DEMO_PATTERN_ID = "demo-perf-255x180"
WIDTH = 255
HEIGHT = 180

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

    for position, (code, name, hex_color, symbol) in enumerate(_PALETTE):
        index_in_grid = position + 1
        count_full = sum(1 for value in cells if value == index_in_grid)
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
                count_full=count_full,
                count_half=0,
                count_quarter=0,
                count_french=0,
                count_beads=0,
                backstitch_length_cm=None,
            )
        )

    session.add(
        Grid(
            pattern_id=pattern.id,
            layer_full=encode_uint16_layer(cells),
            layer_half=None,
            layer_quarter=None,
            backstitch_json="[]",
            french_knots_json="[]",
            encoding="uint16le",
            version=1,
        )
    )

    # Progression de départ : le cadre extérieur déjà brodé, pour avoir un
    # motif ni vide ni terminé à l'ouverture.
    stitched_indices = [i for i, value in enumerate(cells) if value == 1]
    session.add(
        Progress(
            pattern_id=pattern.id,
            bitmap=bitmap_from_indices(stitched_indices, WIDTH * HEIGHT),
            version=1,
            stitched_count=len(stitched_indices),
            updated_at=now,
        )
    )

    session.commit()
    session.refresh(pattern)
    return pattern
