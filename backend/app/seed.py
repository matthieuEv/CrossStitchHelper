"""Demo pattern for performance tests (Lot 1).

The roadmap (`docs/roadmap.md`, Lot 1) calls for a 255 × 180 grid injected
directly into the database — the extraction engine (Lots 4 to 7) did not
exist yet, so nothing else could create a realistic pattern of that size.
The drawing itself does not matter at all: only its size (45,900 cells, the
reference size cited in `CLAUDE.md`) counts, to verify canvas rendering and
progress synchronisation at real scale.

Deterministic generation (fixed seed): the same pattern on every run of the
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

# Centre of the pattern (see `_build_cells`) — the special stitches (Lot 8)
# are grouped there into a small decorative motif, so the feature is visible
# without having to search where in a 45,900-cell grid.
_CX, _CY = WIDTH // 2, HEIGHT // 2

# Purely synthetic palette (never real imported creative content, per
# CLAUDE.md — this is a generated geometric pattern, not a transcribed work).
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
    """Draw concentric rings + a border — a purely geometric pattern, quick
    to generate, with no text-rendering dependency."""
    cells = [0] * (WIDTH * HEIGHT)
    cx, cy = WIDTH / 2, HEIGHT / 2
    palette_count = len(_PALETTE)
    random = _seeded_random(20260914)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Border: solid frame over the last 3 cells of each edge.
            if x < 3 or x >= WIDTH - 3 or y < 3 or y >= HEIGHT - 3:
                cells[y * WIDTH + x] = 1  # black
                continue

            dx = (x - cx) / (WIDTH / 2)
            dy = (y - cy) / (HEIGHT / 2)
            radius = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)

            # Rings + slight angular modulation, for a drawing that is not
            # trivially repetitive while staying cheap to compute.
            ring = int(radius * 14 + math.sin(angle * 6) * 1.3)
            if ring % 4 == 0:
                continue  # empty cell: lets the pattern "breathe"

            index = 2 + (ring + int(angle * 3)) % (palette_count - 2)
            # A little pseudo-random grain to avoid overly crisp rings.
            if next(random) < 0.04:
                index = 2 + (index + 1) % (palette_count - 2)
            cells[y * WIDTH + x] = index

    return cells


# Palette indices (1-based, see `_PALETTE`) reused for the Lot 8 special
# stitches — no new colour: the same threads that already make up the rings,
# so as not to bloat the demo pattern's legend.
_QUARTER_INDEX = 3  # 816, garnet red
_HALF_INDEX = 8  # 798, dark delft blue
_BACKSTITCH_INDEX = 1  # 310, black — common convention for an outline
_KNOT_INDEX = 10  # 3803, very dark mauve pink

# Offsets (dx, dy) from the centre (`_CX`, `_CY`) — a small, purely geometric
# decorative motif (no real creative content, CLAUDE.md), chosen so the five
# stitch categories are all visible grouped in one place rather than
# scattered across the 45,900 cells.
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
    """Build, around the pattern's centre, a small backstitch diamond
    surrounding a few 1/2 and 1/4 stitches and knots — enough to really
    exercise the five stitch categories of Lot 8 (no extraction connector
    produced them yet, see Lot 9: without this synthetic content, the
    interface built here would never have had anything to display until that
    future lot existed).

    Returns ``(quarter_cells, half_cells, backstitch, french_knots)`` — the
    first two in the same convention as `_build_cells` (one value per cell,
    0 = empty), the last two already in the JSON format expected by
    `Grid.backstitch_json`/`french_knots_json`
    (`app/schemas.py::BackstitchSegment`/`FrenchKnot` for the coordinate
    convention: cell corners for one, cell centre for the other)."""
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
    """Insert (or replace, if `force`) the 255 × 180 demo pattern.

    Idempotent by default: if the pattern already exists, it is returned as
    is — a re-import must never overwrite progress already checked
    (structural constraint from `CLAUDE.md`).
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
        # Backstitch length in cm: purely indicative here (fabric_count 14,
        # 1 cell ≈ 1/14 inch ≈ 0.181 cm) — never consumed by a computation,
        # only displayed (§7.3).
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

    # Starting progress: the outer frame already stitched (full stitches),
    # and for each special category a part already checked — a pattern
    # neither empty nor finished when opened, and proof that each bitmap is
    # persisted and reloaded correctly from the seed onwards, not only after
    # a first manual sync.
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
    """Like `bitmap_from_indices`, but for a bitmap sized on a number of
    elements (backstitch segments, knots) rather than on the grid —
    `bitmap_from_indices` implicitly assumes a bitmap the size of the whole
    grid, which would be wrong (and a waste of bytes) for these two
    categories."""
    bitmap = bytearray(bitmap_byte_length(element_count))
    for index in done_indices:
        set_bit(bitmap, index, True)
    return bytes(bitmap)
