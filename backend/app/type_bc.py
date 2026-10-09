"""Automatic detection of types B and C (DMC-style vector grids,
specification §4.3, §4.4 and §8.4-8.5, Lot 5).

Unlike type A (`app/type_a.py`), there is **no embedded symbol font** here:
each cell's colour comes from a vector rectangle's fill, and the symbol (when
there is one) from a small vector path (lines/curves/rectangle fragments) —
never text.

Nothing is hard-coded for a particular fixture. In particular, **the
relationship between the pages of the same PDF is never assumed fixed** (the
lesson of the `summer-flight-dmc` trap case, specification §4.3): this module
measures, for each candidate page, the density of vector paths relative to
colour rectangles before deciding whether a separate symbol page must be
overlaid, or whether the colour page itself already carries the symbols
(observed on `summer-flight-dmc` as well as on `winter-wreath-dmc` — both
behave the same despite what a quick look at the specification might
suggest: only the real measurement on the file is authoritative, never a
fixed-structure assumption, cf. `CLAUDE.md`).

Pure module: no FastAPI/SQLAlchemy dependency. The `detect_type_bc` entry
point never raises — it returns `None` if the PDF does not look like a type
B/C (including when it is actually a type A, or a type E based on reused
bitmap images like `river-and-mountains-laserarts`, specification §4.3)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pdfplumber
import pymupdf
from pdfplumber.page import Page
from PIL import Image

from app.dmc_catalog import lab_distance, nearest_dmc, rgb_to_lab
from app.grid_lines import is_grid_ruling

# `app.schemas` only depends on Pydantic — importing it here does not break
# the module's purity (no FastAPI/SQLAlchemy dependency, see docstring).
from app.schemas import DetectionWarning
from app.type_a import SymbolGlyphLocation, detect_type_a

# See `app/type_a.py` for the rationale of this typing: pdfplumber represents
# each positioned object (rectangle, line, curve) as a heterogeneous
# dictionary, with no public TypedDict to reuse.
Obj = dict[str, Any]
Color = tuple[float, ...]
Bbox = tuple[float, float, float, float]

# --------------------------------------------------------------------------
# Thresholds — all adjustable, none is specific to a particular fixture.
# --------------------------------------------------------------------------

# Minimum number of cell-sized rectangles for a page to be a "colour grid"
# candidate (below that, it is probably just a legend or a cover page with a
# few colour swatches).
_MIN_CELLSIZED_RECTS = 150
# Size tolerance for a filled rectangle to be considered "a cell" rather than
# a symbol stroke fragment (much smaller) or a large legend swatch (much
# larger).
_CELL_SIZE_MIN_RATIO = 0.6
_CELL_SIZE_MAX_RATIO = 1.35
# Acceptable pitch width/height ratio for a cross-stitch grid (cells close to
# square, never a text table).
_PITCH_RATIO_MIN = 0.5
_PITCH_RATIO_MAX = 2.0
# A genuine type B/C file observed (§4.1, §4.3) is 100% vector — no bitmap
# image on its grid pages. `river-and-mountains-laserarts` (type E,
# catalogue of reused icons) also carries a dressing of background rectangles
# per cell on all its grid pages (common publisher template), which would
# otherwise make it eligible as a B/C colour page — the presence of at least
# one image on the page is enough to exclude it: no tolerance, even at the
# cost of missing an isolated logo (a safe fallback to assisted mode rather
# than a silent false positive, mandatory rule of the
# `pdf-extraction-specialist`).
_MAX_IMAGES_ON_COLOR_PAGE = 0
# Density (vector paths / coloured cells) beyond which the colour page itself
# already carries the symbols (measured: ~0.02-0.04 on the "clean"
# winter-wreath/botanical/cucurbit pages versus ~0.2-0.5 on the already
# combined winter-wreath and summer-flight pages — see the module docstring).
# A wide margin between the two observed regimes.
_SYMBOLS_ALREADY_PRESENT_DENSITY = 0.1
# Minimum density on a candidate "symbols" page to accept it as an overlay
# layer rather than an unrelated annex page.
_MIN_SYMBOL_PAGE_DENSITY = 0.15
# A single fill cannot reasonably cover such a huge fraction of a
# multicoloured grid: beyond it, it is a background layer (alternating
# shading, page background fill) rather than a real thread to stitch — see
# `_exclude_background_color`.
_BACKGROUND_DOMINANCE_RATIO = 0.3
# Merging nearly identical colours (CMYK/RGB rounding noise) into a single
# palette entry — well below the smallest perceptible gap observed between
# two genuinely distinct shades in our reference fixtures (~4.4 in Lab).
_COLOR_MERGE_LAB_EPSILON = 2.5
# Beyond this Lab distance, the nearest DMC match is deemed doubtful and
# flagged (specification §8.5).
_UNCERTAIN_COLOR_DISTANCE = 12.0
# Lot 5 "uncertain cells" fix (continued): a first avenue (loosening a
# bit-difference threshold on the old coarse 6x6 bitmap, built from each
# cell's few vector path points, from 3 to 4-6) was abandoned after visual
# verification on `botanical-citrus-dmc` — at a 4-bit gap, it wrongly merged
# a "+" symbol and an "up arrow" symbol. A second, deeper diagnosis showed
# why no global threshold on that bitmap could work: on `cucurbit-dmc`,
# cells carrying genuinely different symbols (a circle, an arrow, a cross —
# confirmed by rendering the cells via `render_symbol_svg`) could land on the
# *same* 6x6 bitmap (pure aliasing, for lack of resolution with only 4 to 6
# source path points per cell) — an identity problem from the initial exact
# grouping onwards, not just a merge tolerance issue.
#
# `_build_symbol_signatures` therefore now builds each cell's fingerprint
# (`_raster_fingerprint`) from the real raster rendering of the symbol page
# (page rendered only once per file via PyMuPDF, cf.
# `_render_symbol_page_gray`) rather than from vector path points — ~256
# pixels per cell versus ~4-6 points, a much lower aliasing risk.
# `_merge_near_duplicate_signatures` then compares these fingerprints with a
# tolerance for a small shift of a few pixels (the observed redraw noise is
# indeed a translation, not a change of shape) and an extra guard on ink area
# (a real difference in shape, even at a small post-shift overlap distance,
# almost always changes the amount of ink — useful for example against a
# symbol that would be a strict subset of another). Thresholds measured on
# the 4 DMC fixtures (see `backend/tests/test_type_bc.py`) before being
# fixed, never guessed — see the details under each threshold below.
#
# Third diagnosis (`winter-wreath-dmc` regression, 22% -> 35% uncertain
# cells after switching to raster rendering): visual rendering
# (`render_symbol_svg`) of several cells of the same canonical colour (olive
# green) spread across the whole grid, not just near the origin — two cells
# carrying the same symbol (a diagonal bar) fell into two different groups.
# The difference was not a fragment of the neighbouring cell (initial
# hypothesis) but **a major grid line** (a "decade" line, drawn every 10
# cells, much thicker than the minor grid — measured directly on the page's
# vector `lines`: ~0.13-0.27 pt for the minor grid versus up to 1.07-1.34 pt
# for the decade lines, i.e. up to ~6 px wide once rendered at the zoom used
# here). With the old 4 px margin, cells adjacent to a decade line kept a
# fragment of that thick line in their crop — and only those, which explains
# why only a fraction of the cells of the same colour tipped into a second
# group (confirmed: the grid positions of the wrongly grouped cells cluster
# near columns/rows that are multiples of 10, not uniformly across the grid
# as a systematic registration imprecision would have produced).
#
# `river-and-mountains-laserarts` aside (type E, never eligible here), the
# symbol pages of `botanical-citrus-dmc` and `cucurbit-dmc` also carry ~6 px
# wide lines at the same zoom, but far fewer of them (a few dozen, probably
# the border rectangle and a few landmarks, not a complete decade grid laid
# over the whole grid as on `winter-wreath-dmc`) — which explains why they
# never showed this symptom before `winter-wreath-dmc` was measured
# specifically.
#
# `_RASTER_CORE_MARGIN_PX` was therefore widened from 4 to 5 px and measured
# on the 4 reference DMC fixtures (never only on the one that regressed, cf.
# `CLAUDE.md`): the uncertain-cell rate of `winter-wreath-dmc` drops to 17.7%
# (611/3460), below its rate from before even the switch to raster rendering
# (~22%), while `botanical-citrus-dmc` (0.8%) and `cucurbit-dmc` (3.7%) stay
# identical to their value measured at 4 px — see
# `backend/tests/test_type_bc.py`. A wider sweep (5 to 10 px) shows
# non-monotonic behaviour beyond 6 px (useful resolution starts to degrade:
# `cucurbit-dmc` climbs back to 17.7% uncertain at 8 px) — 5 px is the lowest
# value that eliminates the contamination measured on `winter-wreath-dmc`,
# never loosened beyond what is necessary. The remaining uncertain cells on
# `winter-wreath-dmc` after this fix (611 cells) come overwhelmingly
# (592/611, measured) from two shades with no close DMC match in the partial
# community catalogue (§8.5) — real and already expected uncertainty,
# independent of shape recognition, never something this fix must or can
# make disappear.
_RASTER_CELL_PX = 24
"""Rendering resolution of the symbol page: pixels per cell (non-uniform
zoom if the pitch is not perfectly square, cf. `_render_symbol_page_gray`).
Fine enough to tell apart shapes a few pixels wide, without needlessly
inflating the rendering time of a whole page."""
_RASTER_CORE_MARGIN_PX = 5
"""Margin removed from each side of the cell before comparison — excludes
the printed grid, which runs exactly along the cell boundary and would
otherwise distort any overlap comparison (measured: without this margin,
almost all cells of the same file look alike because of the shared grid,
not the symbol).

Widened from 4 to 5 px (Lot 5, third "uncertain cells" fix,
`winter-wreath-dmc` regression): at 4 px, cells adjacent to a "decade" grid
line (drawn every 10 cells, much thicker than the minor grid — up to ~6 px
wide once rendered) kept a fragment of that line in their crop, which made
their raster fingerprint drift and broke the grouping of symbols that were
nonetheless identical. See the detailed comment above `_RASTER_CELL_PX` for
the full diagnosis and the measurements on the 4 DMC fixtures."""
_RASTER_SHIFT_TOLERANCE_PX = 4
"""Maximum shift (in pixels, in each direction) tolerated to align two cells
before comparing them — absorbs the observed sub-position noise (slightly
shifted redraw of the same symbol), measured as sufficient on the 4
reference DMC fixtures without needing to be widened further (loosening it
no longer reduces the distance measured on the test cases beyond this
threshold, cf. task report)."""
_RASTER_INK_DELTA = 40
"""A pixel counts as ink if it is at least this many grey levels darker than
the cell's dominant colour (the background) — never an absolute brightness
threshold: a type B/C cell's background colour is not always white (combined
colour+symbol page, `winter-wreath-dmc` case), an absolute threshold would
then classify the whole colour fill as "ink" and make strictly everything
merge (measured: 52 wrong merges on `winter-wreath-dmc` with an absolute
threshold, versus 3 with this threshold relative to the local dominant
colour)."""
_RASTER_MERGE_MAX_JACCARD = 0.40
"""Jaccard distance (1 - intersection area / union area, best tolerated
shift) below which two cells are grouped. Measured on `cucurbit-dmc` (grid
positions (24,29)/(22,31)/(23,29)/(21,31), the same redrawn circle): maximum
distance 0.369 between the 4 cells. Measured on `botanical-citrus-dmc` ("+"
versus arrow): 0.475. Threshold placed halfway with a comfortable margin on
both sides — never tightened to the point of breaking at the slightest minor
deviation, never loosened to the point of swallowing the "+"/arrow pair."""
_RASTER_MERGE_MIN_AREA_RATIO = 0.75
"""Ratio (smallest ink area / largest) below which two cells are never
grouped, even at a small Jaccard distance — an independent guard against a
real symbol that would be a strict subset of another (a simple stroke
contained in a richer symbol, for example): that situation can make the
Jaccard distance drop without the two shapes being really identical, so the
Jaccard distance alone is not always enough. On the 4 reference DMC
fixtures, the groupings actually made all have an area ratio of at least
0.938 (`botanical-citrus-dmc`'s "+"/arrow pair, which stays distinct thanks
to the Jaccard distance, not this guard) to 0.943 (`cucurbit-dmc`'s redrawn
circle, which does merge) — this threshold is therefore never the deciding
factor on these four particular files, but remains a protection measured as
cheap (it blocks no correct grouping observed) against a case not covered by
these fixtures."""
# Number of distinct groups / number of coloured cells beyond which shape
# recognition is deemed too unreliable for the whole file (fallback to
# type B). Measured with the raster fingerprint (see above): 0.006-0.014 on
# the three DMC fixtures with reliable recognition versus 0.290 on the
# `summer-flight-dmc` trap case (richly shaded illustration, §4.3) — a wide
# margin between the two regimes, but clearly lower than with the old vector
# bitmap (where the same trap case reached ~0.9): the much less noisy raster
# fingerprint also groups the fragments of `summer-flight-dmc`'s shaded
# illustration better without making them reliable (194 distinct groups over
# 668 coloured cells is still far more than a plausible symbol catalogue) —
# this threshold therefore had to be tightened accordingly, not just copied.
_MAX_SIGNATURE_FRAGMENTATION = 0.1


@dataclass
class TypeBCPaletteEntry:
    code: str
    name: str
    rgb_hex: str
    symbol_key: str
    symbol_glyph: SymbolGlyphLocation | None = None


@dataclass
class TypeBCResult:
    columns: int
    rows: int
    cells: list[int]
    """Length `columns * rows`, row by row, (0,0) at the top left first.
    0 = empty cell, n = 1-based index into `palette`."""
    palette: list[TypeBCPaletteEntry]
    grid_type: Literal["B", "C"]
    confidence: float
    uncertain_cells: list[int] = field(default_factory=list)
    """0-based indices into `cells` of the cells whose colour and/or symbol
    is uncertain — never a wrong cell left unflagged (mandatory rule of the
    `pdf-extraction-specialist`)."""
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Never text already composed in French: a message code and its
    parameters, translated on the client (`import.warning.<code>`, Lot 8
    translation audit)."""


def detect_type_bc(pdf_path: Path) -> TypeBCResult | None:
    """Return `None` (never raising) if the PDF does not look like a type B/C
    export — see the module for the details of the detection."""
    try:
        # A genuine type A export (embedded symbol font, tested on the six
        # reference fixtures) must never also be offered as B/C — avoid any
        # competing double result for the same file (§4.4: the typology is a
        # classification, not a stack of guesses).
        if detect_type_a(pdf_path) is not None:
            return None

        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages
            infos = [_analyze_page(page) for page in pages]

            color_page = _select_color_page(infos)
            if color_page is None:
                return None
            # `_select_color_page` only returns pages where these three
            # values are already guaranteed non-`None` (filter on
            # `len(cellsized_rects) >= _MIN_CELLSIZED_RECTS`, which implies a
            # detected pitch, and `border is not None`) — assertions so mypy
            # knows it too, never to hide a real case.
            assert color_page.border is not None
            assert color_page.pitch_x is not None
            assert color_page.pitch_y is not None
            color_border = color_page.border
            color_pitch_x = color_page.pitch_x
            color_pitch_y = color_page.pitch_y

            symbol_page, grid_type, page_warning = _select_symbol_page(infos, color_page)
            warnings: list[DetectionWarning] = [page_warning] if page_warning is not None else []
            confidence = 1.0

            grid = _GridGeometry(
                columns=round((color_border[2] - color_border[0]) / color_pitch_x),
                rows=round((color_border[3] - color_border[1]) / color_pitch_y),
                origin_x=color_border[0],
                origin_top=color_border[1],
                pitch_x=color_pitch_x,
                pitch_y=color_pitch_y,
            )
            if grid.columns <= 0 or grid.rows <= 0:
                return None
            if color_page.border_is_fallback:
                warnings.append(DetectionWarning(code="type_bc.border_inferred"))
                confidence -= 0.15

            raw_cell_colors = _build_color_grid(color_page, grid)
            raw_cell_colors, background_warning = _exclude_background_color(
                raw_cell_colors, grid.columns * grid.rows
            )
            if background_warning is not None:
                warnings.append(background_warning)

            if not raw_cell_colors:
                return None

            canonical_of, canonical_colors = _cluster_colors(raw_cell_colors)
            cell_color_id: dict[tuple[int, int], int] = {
                pos: canonical_of[color] for pos, color in raw_cell_colors.items()
            }

            cell_signature: dict[tuple[int, int], int] = {}
            representative_bbox: dict[int, Bbox] = {}
            symbol_page_number: int | None = None
            if grid_type == "C" and symbol_page is not None:
                symbol_page_number = symbol_page.index + 1
                # Reuse the colour page's geometry as is when the symbol page
                # is the same page (`winter-wreath-dmc`/`summer-flight-dmc`
                # case, §4.3): recomputing a pitch from a rounded border
                # would introduce a tiny but systematic gap with the grid
                # already used to extract the colour, which artificially
                # fragments the shape signatures (measured: x4 the number of
                # groups obtained). Registration only makes sense for a
                # genuinely distinct page.
                sym_grid = grid if symbol_page is color_page else _symbol_grid_for(
                    symbol_page, grid
                )
                cell_signature, representative_bbox = _build_symbol_signatures(
                    symbol_page, sym_grid, set(cell_color_id), pdf_path
                )
                if not any(cell_signature.values()):
                    # Measured density sufficient but no usable shape grouped
                    # per cell (registration out of tolerance, for example):
                    # never claim a symbol recognition we do not really have
                    # — honest fallback to B.
                    grid_type = "B"
                    warnings.append(DetectionWarning(code="type_bc.symbol_page_unusable"))
                    confidence -= 0.2
                elif cell_signature:
                    n_clusters = len(set(cell_signature.values()))
                    n_colored = len(cell_signature)
                    if n_clusters / n_colored > _MAX_SIGNATURE_FRAGMENTATION:
                        # Far more distinct signatures than plausible for a
                        # real symbol catalogue (observed: very richly shaded
                        # illustration on `summer-flight-dmc`, where each cell
                        # carries, besides the symbol, several shading
                        # fragments that make its signature drift) — shape
                        # recognition is not reliable enough for the whole
                        # file: honest fallback to B rather than an unusable
                        # "fake" palette of several hundred entries
                        # (specification §4.4: type B when shape recognition
                        # confidence is too low for the whole file).
                        grid_type = "B"
                        cell_signature = {}
                        warnings.append(
                            DetectionWarning(code="type_bc.symbol_recognition_unreliable")
                        )
                        confidence -= 0.2

            (
                palette,
                cells,
                uncertain_cells,
                palette_warnings,
                palette_penalty,
            ) = _build_palette_and_cells(
                grid=grid,
                cell_color_id=cell_color_id,
                canonical_colors=canonical_colors,
                cell_signature=cell_signature,
                representative_bbox=representative_bbox,
                grid_type=grid_type,
                symbol_page_number=symbol_page_number,
            )
            warnings.extend(palette_warnings)
            confidence -= palette_penalty

            confidence = max(0.0, min(1.0, confidence))
            return TypeBCResult(
                columns=grid.columns,
                rows=grid.rows,
                cells=cells,
                palette=palette,
                grid_type=grid_type,
                confidence=confidence,
                uncertain_cells=uncertain_cells,
                warnings=warnings,
            )
    except Exception:  # pragma: no cover - safety net, see docstring
        # Never raise: an unexpected PDF must simply not be recognised as
        # type B/C rather than make the whole import fail (mandatory rule
        # "never block an import").
        return None


# --------------------------------------------------------------------------
# Per-page structural analysis
# --------------------------------------------------------------------------


@dataclass
class _PageInfo:
    index: int
    page: Page
    filled_rects: list[Obj]
    cellsized_rects: list[Obj]
    curves: list[Obj]
    lines: list[Obj]
    n_images: int
    pitch_x: float | None
    pitch_y: float | None
    border: Bbox | None
    border_is_fallback: bool


def _analyze_page(page: Page) -> _PageInfo:
    filled_rects = [r for r in page.rects if r.get("fill")]
    pitch = _estimate_pitch_from_rects(filled_rects)
    pitch_x, pitch_y = pitch if pitch is not None else (None, None)
    cellsized_rects: list[Obj] = []
    if pitch_x is not None and pitch_y is not None:
        min_w, max_w = _CELL_SIZE_MIN_RATIO * pitch_x, _CELL_SIZE_MAX_RATIO * pitch_x
        min_h, max_h = _CELL_SIZE_MIN_RATIO * pitch_y, _CELL_SIZE_MAX_RATIO * pitch_y
        cellsized_rects = [
            r
            for r in filled_rects
            if min_w <= (r["x1"] - r["x0"]) <= max_w and min_h <= (r["bottom"] - r["top"]) <= max_h
        ]
    # The border is detected independently of the cell pitch: a pure symbol
    # page (stroke fragments, no large colour fills) has no reliable cell
    # pitch derivable from its rectangles (its filled rectangles, when there
    # are any, are small stroke fragments, not cells), but still carries the
    # same grid frame as the colour page — essential to select it as the
    # symbol page to overlay (`_select_symbol_page`).
    border = _detect_border(page)
    border_is_fallback = False
    if border is None and len(cellsized_rects) >= _MIN_CELLSIZED_RECTS:
        xs = [r["x0"] for r in cellsized_rects] + [r["x1"] for r in cellsized_rects]
        ys = [r["top"] for r in cellsized_rects] + [r["bottom"] for r in cellsized_rects]
        border = (min(xs), min(ys), max(xs), max(ys))
        border_is_fallback = True
    return _PageInfo(
        index=page.page_number - 1,
        page=page,
        filled_rects=filled_rects,
        cellsized_rects=cellsized_rects,
        curves=list(page.curves),
        lines=list(page.lines),
        n_images=len(page.images),
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        border=border,
        border_is_fallback=border_is_fallback,
    )


def _estimate_pitch(distinct_sorted: list[float]) -> float | None:
    if len(distinct_sorted) < 2:
        return None
    diffs = [b - a for a, b in zip(distinct_sorted, distinct_sorted[1:], strict=False)]
    plausible = [d for d in diffs if d > 0.5]
    if not plausible:
        return None
    return statistics.median(plausible)


def _estimate_pitch_from_rects(filled_rects: list[Obj]) -> tuple[float, float] | None:
    if len(filled_rects) < _MIN_CELLSIZED_RECTS:
        return None
    widths = sorted(r["x1"] - r["x0"] for r in filled_rects)
    heights = sorted(r["bottom"] - r["top"] for r in filled_rects)
    pitch_x = statistics.median(widths)
    pitch_y = statistics.median(heights)
    if pitch_x <= 0 or pitch_y <= 0:
        return None
    if not (_PITCH_RATIO_MIN <= pitch_x / pitch_y <= _PITCH_RATIO_MAX):
        return None
    return pitch_x, pitch_y


# --------------------------------------------------------------------------
# Grid border detection (total extent, not just the stitched area: a printed
# grid almost always leaves unstitched background cells, whose size the
# extent of the colour rectangles alone would underestimate — see the module
# docstring).
# --------------------------------------------------------------------------


def _segment_coverage(
    segments: list[tuple[float, float]], span_min: float, span_max: float
) -> float:
    span = span_max - span_min
    if span <= 0:
        return 0.0
    ivs = sorted(segments)
    covered = 0.0
    cur_a: float | None = None
    cur_b = 0.0
    for a, b in ivs:
        if cur_a is None:
            cur_a, cur_b = a, b
            continue
        if a <= cur_b + 1.5:
            cur_b = max(cur_b, b)
        else:
            covered += cur_b - cur_a
            cur_a, cur_b = a, b
    if cur_a is not None:
        covered += cur_b - cur_a
    return covered / span


def _detect_border(page: Page, tol: float = 1.5) -> Bbox | None:
    """Outer border of the printed grid frame: either a single unfilled but
    stroked rectangle (`stroke`), or four sides of the same stroke width
    forming a closed rectangle among the page's `lines`. Both
    representations are observed depending on the file (see tests) — never
    assumed interchangeable without geometric verification (a mere
    co-occurrence of 2 page-edge lines, landmark arrows for example, is not a
    border)."""
    page_area = page.width * page.height
    best: tuple[float, Bbox] | None = None

    for r in page.rects:
        if r.get("stroke") and not r.get("fill"):
            bbox = (r["x0"], r["top"], r["x1"], r["bottom"])
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if 0.05 * page_area < area < 0.97 * page_area and (best is None or area > best[0]):
                best = (area, bbox)

    groups: dict[float, list[Obj]] = defaultdict(list)
    for line in page.lines:
        lw = round(float(line.get("linewidth") or 0.0), 2)
        groups[lw].append(line)

    for lines in groups.values():
        if len(lines) < 4:
            continue
        horiz = [line for line in lines if abs(line["top"] - line["bottom"]) < 0.5]
        vert = [line for line in lines if abs(line["x0"] - line["x1"]) < 0.5]
        if not horiz or not vert:
            continue
        min_x = min(min(line["x0"], line["x1"]) for line in lines)
        max_x = max(max(line["x0"], line["x1"]) for line in lines)
        min_y = min(min(line["top"], line["bottom"]) for line in lines)
        max_y = max(max(line["top"], line["bottom"]) for line in lines)
        top_segs = [
            (min(line["x0"], line["x1"]), max(line["x0"], line["x1"]))
            for line in horiz
            if abs(line["top"] - min_y) < tol
        ]
        bot_segs = [
            (min(line["x0"], line["x1"]), max(line["x0"], line["x1"]))
            for line in horiz
            if abs(line["top"] - max_y) < tol
        ]
        left_segs = [
            (min(line["top"], line["bottom"]), max(line["top"], line["bottom"]))
            for line in vert
            if abs(line["x0"] - min_x) < tol
        ]
        right_segs = [
            (min(line["top"], line["bottom"]), max(line["top"], line["bottom"]))
            for line in vert
            if abs(line["x0"] - max_x) < tol
        ]
        coverage = min(
            _segment_coverage(top_segs, min_x, max_x),
            _segment_coverage(bot_segs, min_x, max_x),
            _segment_coverage(left_segs, min_y, max_y),
            _segment_coverage(right_segs, min_y, max_y),
        )
        if coverage < 0.7:
            continue
        bbox = (min_x, min_y, max_x, max_y)
        area = (max_x - min_x) * (max_y - min_y)
        if 0.05 * page_area < area < 0.97 * page_area and (best is None or area > best[0]):
            best = (area, bbox)

    return best[1] if best is not None else None


# --------------------------------------------------------------------------
# Selecting the colour page and, if needed, the symbol page
# --------------------------------------------------------------------------


def _select_color_page(infos: list[_PageInfo]) -> _PageInfo | None:
    """The candidate colour page: the one that tiles the largest number of
    cells with filled cell-sized rectangles, excluding pages dominated by
    bitmap images (type E, never a real B/C grid — see the module
    docstring)."""
    candidates = [
        info
        for info in infos
        if len(info.cellsized_rects) >= _MIN_CELLSIZED_RECTS
        and info.border is not None
        and info.n_images <= _MAX_IMAGES_ON_COLOR_PAGE
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda info: len(info.cellsized_rects))


def _page_density(info: _PageInfo) -> float:
    """Vector paths (curves) relative to the number of coloured cells — see
    the `_SYMBOLS_ALREADY_PRESENT_DENSITY` / `_MIN_SYMBOL_PAGE_DENSITY`
    thresholds at the top of the module for their use. Curves alone (not
    lines) are the most discriminating signal measured on the four reference
    fixtures: they carry almost exclusively the rounded parts of symbols,
    nearly absent from a clean colour page, whereas lines also include the
    decimal grid (present in comparable quantity on all pages, coloured or
    not — a much less discriminating signal)."""
    n_cells = max(1, len(info.cellsized_rects))
    return len(info.curves) / n_cells


def _select_symbol_page(
    infos: list[_PageInfo], color_page: _PageInfo
) -> tuple[_PageInfo | None, Literal["B", "C"], DetectionWarning | None]:
    """Decide, by measurement and never by an assumed fixed page position
    (§4.3: `summer-flight-dmc` trap case), whether the colour page itself
    already carries the symbols, whether a neighbouring page must be
    overlaid, or whether no usable symbol is available (type B fallback)."""
    own_density = _page_density(color_page)
    if own_density >= _SYMBOLS_ALREADY_PRESENT_DENSITY:
        return color_page, "C", None

    border = color_page.border
    assert border is not None
    color_width = border[2] - border[0]
    color_height = border[3] - border[1]

    best: _PageInfo | None = None
    best_density = 0.0
    for info in infos:
        if info.index == color_page.index or info.border is None:
            continue
        b = info.border
        width, height = b[2] - b[0], b[3] - b[1]
        if abs(width - color_width) > 0.1 * color_width:
            continue
        if abs(height - color_height) > 0.1 * color_height:
            continue
        density = len(info.curves) / max(1, len(color_page.cellsized_rects))
        if density > best_density:
            best_density = density
            best = info

    if best is not None and best_density >= _MIN_SYMBOL_PAGE_DENSITY:
        return best, "C", None

    return None, "B", DetectionWarning(code="type_bc.no_symbol_page")


# --------------------------------------------------------------------------
# Grid geometry and per-cell colour extraction
# --------------------------------------------------------------------------


@dataclass
class _GridGeometry:
    columns: int
    rows: int
    origin_x: float
    origin_top: float
    pitch_x: float
    pitch_y: float

    def cell_of(self, cx: float, cy: float) -> tuple[int, int]:
        col0 = int((cx - self.origin_x) / self.pitch_x)
        row0 = int((cy - self.origin_top) / self.pitch_y)
        return row0, col0

    def cell_origin(self, row0: int, col0: int) -> tuple[float, float]:
        return (
            self.origin_x + col0 * self.pitch_x,
            self.origin_top + row0 * self.pitch_y,
        )


def _normalize_color(raw: Any) -> Color:
    """`non_stroking_color` can be a scalar (grey level), an RGB triplet or a
    CMYK quadruplet depending on the PDF's colour space (specification §8.4)
    — always reduced to a rounded tuple."""
    if isinstance(raw, int | float):
        value = round(float(raw), 4)
        return (value, value, value)
    if isinstance(raw, list | tuple):
        return tuple(round(float(v), 4) for v in raw)
    return (0.0, 0.0, 0.0)


@lru_cache(maxsize=4096)
def _cmyk_to_rgb_via_mupdf(cmyk: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Convert CMYK to RGB via PyMuPDF's colour conversion (already a project
    dependency, specification §7.2) instead of the naive `R=(1-C)(1-K)`
    formula recommended as a fallback by the PDF specification. Measured
    (Lot 5, uncertain cells fix): on DMC vector grids, a good share of fills
    are in CMYK, and the naive formula clearly oversaturates shades obtained
    by mixing cyan+yellow (greens in particular) — up to ~25 Lab distance
    points away from the actually rendered colour for the same shade, far
    above `_UNCERTAIN_COLOR_DISTANCE`, which wrongly tipped almost all cells
    of a colour into uncertain during DMC matching (confirmed by comparing
    both formulas with the colour actually rendered by PyMuPDF on
    `botanical-citrus-dmc` and `cucurbit-dmc`). Cached: the number of
    distinct CMYK shades per file is around ten, far below the number of
    cells."""
    c, m, y, k = (max(0.0, min(1.0, v)) for v in cmyk)
    samples = bytes([round(c * 255), round(m * 255), round(y * 255), round(k * 255)])
    pixmap_cmyk = pymupdf.Pixmap(pymupdf.csCMYK, 1, 1, samples, False)  # type: ignore[no-untyped-call]
    pixmap_rgb = pymupdf.Pixmap(pymupdf.csRGB, pixmap_cmyk)  # type: ignore[no-untyped-call]
    r, g, b = pixmap_rgb.pixel(0, 0)[:3]  # type: ignore[no-untyped-call]
    return r / 255, g / 255, b / 255


def _color_to_rgb(color: Color) -> tuple[float, float, float]:
    """Convert a normalised colour (RGB, CMYK or grey) to 0-1 RGB."""
    if len(color) == 3:
        return color[0], color[1], color[2]
    if len(color) == 4:
        c, m, y, k = color
        return _cmyk_to_rgb_via_mupdf((c, m, y, k))
    if len(color) == 1:
        v = color[0]
        return v, v, v
    return 0.0, 0.0, 0.0


def _build_color_grid(
    color_page: _PageInfo, grid: _GridGeometry
) -> dict[tuple[int, int], Color]:
    """Colour per cell, in the PDF's drawing order (`page.rects` is already
    in content-stream order): when several rectangles overlap exactly on the
    same cell (observed: a background fill under the cell's real fill, cf.
    `_exclude_background_color`), the last one drawn is visually the one
    that counts — never the smallest in area (type A heuristic, invalid here
    since both rectangles are the same size)."""
    border = color_page.border
    assert border is not None
    margin_x = grid.pitch_x * 0.5
    margin_y = grid.pitch_y * 0.5
    cells: dict[tuple[int, int], Color] = {}
    for rect in color_page.cellsized_rects:
        cx = (rect["x0"] + rect["x1"]) / 2
        cy = (rect["top"] + rect["bottom"]) / 2
        if not (
            border[0] - margin_x <= cx <= border[2] + margin_x
            and border[1] - margin_y <= cy <= border[3] + margin_y
        ):
            continue
        row0, col0 = grid.cell_of(cx, cy)
        if row0 < 0 or col0 < 0 or row0 >= grid.rows or col0 >= grid.columns:
            continue
        cells[(row0, col0)] = _normalize_color(rect["non_stroking_color"])
    return cells


def _exclude_background_color(
    cells: dict[tuple[int, int], Color], total_grid_cells: int
) -> tuple[dict[tuple[int, int], Color], DetectionWarning | None]:
    """Exclude a colour that dominates an implausible fraction of the whole
    grid (observed: a neutral background fill applied under every cell,
    coloured or not, on `summer-flight-dmc` — no real thread of a
    multicoloured pattern ever covers such a proportion). Detection by
    frequency, never by a hard-coded colour value: it triggers on none of the
    three other reference fixtures, where no colour exceeds ~5% of the
    cells."""
    if not cells:
        return cells, None
    counts = Counter(cells.values())
    dominant_color, dominant_count = counts.most_common(1)[0]
    if dominant_count < _BACKGROUND_DOMINANCE_RATIO * total_grid_cells:
        return cells, None
    filtered = {pos: c for pos, c in cells.items() if c != dominant_color}
    warning = DetectionWarning(
        code="type_bc.background_color_excluded",
        params={"cells": dominant_count},
    )
    return filtered, warning


# --------------------------------------------------------------------------
# Merging nearly identical colours (CMYK/RGB rounding noise)
# --------------------------------------------------------------------------


def _cluster_colors(
    cells: dict[tuple[int, int], Color]
) -> tuple[dict[Color, int], list[tuple[float, float, float]]]:
    """Group the distinct raw colours by Lab proximity
    (`_COLOR_MERGE_LAB_EPSILON`) into canonical colours. Returns the raw
    colour -> canonical index mapping table and the list of canonical colours
    (RGB mean of the grouped colours, weighted by their number of cells)."""
    raw_counts = Counter(cells.values())
    raw_colors = sorted(raw_counts, key=lambda c: -raw_counts[c])
    raw_rgb = {c: _color_to_rgb(c) for c in raw_colors}
    raw_lab = {c: rgb_to_lab(raw_rgb[c]) for c in raw_colors}

    canonical_rgb: list[tuple[float, float, float]] = []
    canonical_weight: list[int] = []
    canonical_of: dict[Color, int] = {}

    for raw in raw_colors:  # from most to least frequent
        best_index: int | None = None
        best_distance = float("inf")
        for index, rgb in enumerate(canonical_rgb):
            distance = lab_distance(raw_lab[raw], rgb_to_lab(rgb))
            if distance < best_distance:
                best_distance = distance
                best_index = index
        if best_index is not None and best_distance <= _COLOR_MERGE_LAB_EPSILON:
            weight = raw_counts[raw]
            prev_weight = canonical_weight[best_index]
            prev_rgb = canonical_rgb[best_index]
            new_weight = prev_weight + weight
            blended = raw_rgb[raw]
            canonical_rgb[best_index] = (
                (prev_rgb[0] * prev_weight + blended[0] * weight) / new_weight,
                (prev_rgb[1] * prev_weight + blended[1] * weight) / new_weight,
                (prev_rgb[2] * prev_weight + blended[2] * weight) / new_weight,
            )
            canonical_weight[best_index] = new_weight
            canonical_of[raw] = best_index
        else:
            canonical_of[raw] = len(canonical_rgb)
            canonical_rgb.append(raw_rgb[raw])
            canonical_weight.append(raw_counts[raw])

    return canonical_of, canonical_rgb


# --------------------------------------------------------------------------
# Vector symbol recognition (symbol page, overlaid or not)
# --------------------------------------------------------------------------


def _symbol_grid_for(symbol_page: _PageInfo, grid: _GridGeometry) -> _GridGeometry:
    """Grid geometry to use for reading `symbol_page`'s paths: same number
    of columns/rows as the colour page (deemed more reliable, derived from
    the cell rectangles rather than the paths), but a pitch and an origin
    re-registered on `symbol_page`'s own border rather than reused as is.
    Needed in practice: the two pages of the same PDF share neither exactly
    the same origin nor exactly the same scale (gaps of a few points measured
    on the reference fixtures, which accumulate across the grid's width
    without this registration) — this is the "fine registration adjustment"
    planned by specification §7.2 step 5."""
    if symbol_page.border is None:
        return grid
    b = symbol_page.border
    width, height = b[2] - b[0], b[3] - b[1]
    return _GridGeometry(
        columns=grid.columns,
        rows=grid.rows,
        origin_x=b[0],
        origin_top=b[1],
        pitch_x=width / grid.columns,
        pitch_y=height / grid.rows,
    )


def _is_grid_ruling(line: Obj, grid: _GridGeometry, tol_ratio: float = 0.15) -> bool:
    """A decimal grid line (or its minor ruling) is aligned exactly on a
    cell boundary, unlike a symbol stroke, which lies inside a cell. Filtered
    only for `lines` (axis-aligned by construction) — never for curves, which
    are never used to draw a rectilinear grid.

    The rule itself lives in `app/grid_lines.py` since Lot 9 (type A needs
    it for its backstitches); the call below passes it the bbox, exactly like
    the original Lot 5 version, and with no length criterion — type B/C
    behaviour is unchanged."""
    return is_grid_ruling(
        float(line["x0"]),
        float(line["top"]),
        float(line["x1"]),
        float(line["bottom"]),
        origin_x=grid.origin_x,
        origin_top=grid.origin_top,
        pitch_x=grid.pitch_x,
        pitch_y=grid.pitch_y,
        tol_ratio=tol_ratio,
    )


def _build_symbol_signatures(
    symbol_page: _PageInfo,
    sym_grid: _GridGeometry,
    colored_cells: set[tuple[int, int]],
    pdf_path: Path,
) -> tuple[dict[tuple[int, int], int], dict[int, Bbox]]:
    """Shape signature per cell: a fingerprint from the cell's real raster
    rendering (see `_raster_fingerprint`), never from a bitmap derived from
    vector path points — makes it possible to group the cells carrying the
    same symbol without knowing the catalogue of possible symbols in advance
    (mandatory rule: never a hard-coded symbol list, cf. Lot 4).

    A first version of this module derived that fingerprint from a coarse
    bitmap (6x6 grid) built directly from the cell's few vector path points.
    Diagnosis (Lot 5, second "uncertain cells" fix): on `cucurbit-dmc`, that
    coarse bitmap sometimes *aliased* genuinely different symbols (confirmed
    visually via `render_symbol_svg`: a circle, an arrow and a cross shared
    the same 6x6 bitmap, for lack of sufficient resolution with so few source
    points) — an *identity* problem from the initial exact grouping onwards,
    upstream of any merge tolerance. Using the raster rendering directly (far
    richer: ~256 pixels versus ~4-6 vector points per cell) eliminates this
    aliasing risk at the source.

    Vector paths (rectangles/curves/non-grid lines) are still used, but only
    for two things independent of the exact shape: detecting *whether* a
    cell carries a symbol (empty cell vs marked cell) and providing the real
    bbox displayed by the wizard (`SymbolGlyphLocation`, precise PDF
    coordinates, more faithful than a crop derived from the raster
    rendering). Spatial index per cell before any processing (like
    `_build_rect_index` in `app/type_a.py`): essential here too —
    `summer-flight-dmc` carries more than 10,000 rectangles and 2,000 paths
    per page, a naive path x cell comparison would be far too slow.

    `sym_grid` is the geometry already re-registered on `symbol_page` (see
    `_symbol_grid_for` and its call site) — never recomputed here, to keep a
    single place that decides between reusing the colour grid as is or
    re-registering on the symbol page's own border."""
    cellsized_ids = {id(r) for r in symbol_page.cellsized_rects}

    buckets: dict[tuple[int, int], list[Obj]] = defaultdict(list)
    for rect in symbol_page.filled_rects:
        if id(rect) in cellsized_ids:
            continue
        _bucket_object(rect, sym_grid, buckets)
    for curve in symbol_page.curves:
        _bucket_object(curve, sym_grid, buckets)
    for line in symbol_page.lines:
        if _is_grid_ruling(line, sym_grid):
            continue
        _bucket_object(line, sym_grid, buckets)

    # Vector bbox of the marked cells (PDF coordinates, for
    # `SymbolGlyphLocation`) — also serves as a presence test (empty vs
    # marked cell), independent of the shape's exact identity.
    vector_bbox: dict[tuple[int, int], Bbox] = {}
    for pos in colored_cells:
        objs = buckets.get(pos)
        if not objs:
            continue
        xs: list[float] = []
        ys: list[float] = []
        for obj in objs:
            for px, py in obj.get("pts") or ():
                xs.append(px)
                ys.append(py)
        if xs and ys:
            vector_bbox[pos] = (min(xs), min(ys), max(xs), max(ys))

    if not vector_bbox:
        return {pos: 0 for pos in colored_cells}, {}

    gray, origin_px, origin_py = _render_symbol_page_gray(pdf_path, symbol_page.index + 1, sym_grid)

    signatures: dict[tuple[int, int], int] = {}
    representative_bbox: dict[int, Bbox] = {}
    representative_pos: dict[int, tuple[int, int]] = {}
    for pos in colored_cells:
        if pos not in vector_bbox:
            signatures[pos] = 0
            continue
        fingerprint = _raster_fingerprint(gray, origin_px, origin_py, pos)
        signatures[pos] = fingerprint
        if fingerprint != 0 and fingerprint not in representative_bbox:
            representative_bbox[fingerprint] = vector_bbox[pos]
            representative_pos[fingerprint] = pos

    return _merge_near_duplicate_signatures(
        signatures, representative_bbox, representative_pos, gray, origin_px, origin_py
    )


def _render_symbol_page_gray(
    pdf_path: Path, page_number: int, sym_grid: _GridGeometry
) -> tuple[Image.Image, int, int]:
    """Render the whole symbol page in greyscale, only once per file, at a
    resolution where each cell of `sym_grid` takes exactly `_RASTER_CELL_PX`
    x `_RASTER_CELL_PX` pixels (non-uniform zoom if the pitch is not
    perfectly square). Rendering the whole page rather than one fragment per
    cell is essential to stay within the time budget (specification §10):
    `_merge_near_duplicate_signatures` then only compares the few dozen
    *distinct* bitmaps observed in the file, never each of the coloured cells
    (which can number in the thousands)."""
    zoom_x = _RASTER_CELL_PX / sym_grid.pitch_x
    zoom_y = _RASTER_CELL_PX / sym_grid.pitch_y
    matrix = pymupdf.Matrix(zoom_x, zoom_y)  # type: ignore[no-untyped-call]
    with pymupdf.open(pdf_path) as doc:  # type: ignore[no-untyped-call]
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("L")
    origin_px = round(sym_grid.origin_x * zoom_x)
    origin_py = round(sym_grid.origin_top * zoom_y)
    return image, origin_px, origin_py


def _cell_ink_grid(
    gray: Image.Image,
    origin_px: int,
    origin_py: int,
    pos: tuple[int, int],
    pad: int,
) -> list[list[int]]:
    """Binary ink grid (0/1) for cell `pos`, cropped with a
    `_RASTER_CORE_MARGIN_PX` margin (excludes the printed grid, cf.
    `_RASTER_CORE_MARGIN_PX`) and an extra `pad` on each side to allow the
    shift search (`_best_shifted_jaccard_distance`). Pixels outside the
    image (cell near the page edge) count as white, never black:
    `Image.crop` would otherwise fill the out-of-bounds area with black,
    which would make a mere page edge pass for ink.

    Ink threshold relative to the dominant colour *of that particular cell*
    (`_RASTER_INK_DELTA`), never an absolute brightness threshold — see its
    docstring for the reason (combined colour+symbol page where the
    background is not white, `winter-wreath-dmc` case)."""
    row0, col0 = pos
    width, height = gray.size
    x0 = origin_px + col0 * _RASTER_CELL_PX + _RASTER_CORE_MARGIN_PX - pad
    y0 = origin_py + row0 * _RASTER_CELL_PX + _RASTER_CORE_MARGIN_PX - pad
    size = (_RASTER_CELL_PX - 2 * _RASTER_CORE_MARGIN_PX) + 2 * pad
    pixels = gray.load()
    assert pixels is not None
    values: list[list[int]] = [[255] * size for _ in range(size)]
    for y in range(size):
        py = y0 + y
        if not (0 <= py < height):
            continue
        for x in range(size):
            px = x0 + x
            if 0 <= px < width:
                # "L" mode (greyscale) image: the value is always an integer
                # despite the broad type of PIL's stubs (shared with the RGB
                # tuples of the other modes).
                values[y][x] = int(pixels[px, py])  # type: ignore[arg-type]
    background = Counter(v for row in values for v in row).most_common(1)[0][0]
    return [[1 if background - v >= _RASTER_INK_DELTA else 0 for v in row] for row in values]


def _raster_fingerprint(
    gray: Image.Image, origin_px: int, origin_py: int, pos: tuple[int, int]
) -> int:
    """Integer fingerprint (one bit per ink pixel) of a cell's real raster
    rendering, with no shift margin — the exact grouping key used by
    `_build_symbol_signatures` (two cells whose rendering is identical to the
    pixel get the same fingerprint). Far finer than the old 6x6 bitmap
    derived from path points (see the `_build_symbol_signatures` docstring),
    hence much less prone to aliasing two genuinely different symbols onto
    the same fingerprint."""
    grid = _cell_ink_grid(gray, origin_px, origin_py, pos, 0)
    fingerprint = 0
    bit = 0
    for row in grid:
        for value in row:
            if value:
                fingerprint |= 1 << bit
            bit += 1
    return fingerprint


def _best_shifted_jaccard_distance(
    core: list[list[int]], padded: list[list[int]], max_shift: int
) -> float:
    """Jaccard distance between `core` (reference cell, no extra margin) and
    `padded` (compared cell, with a `max_shift`-pixel margin on each side),
    trying every small shift within that margin and keeping the best
    (smallest) — absorbs the sub-position noise of a redrawn symbol (see
    `_RASTER_SHIFT_TOLERANCE_PX`). `core` and `padded` are already 0/1 grids
    (`_cell_ink_grid`)."""
    h, w = len(core), len(core[0])
    best = 1.0
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            intersection = 0
            union = 0
            for y in range(h):
                padded_row = padded[y + max_shift + dy]
                core_row = core[y]
                for x in range(w):
                    a = core_row[x]
                    b = padded_row[x + max_shift + dx]
                    if a or b:
                        union += 1
                        if a and b:
                            intersection += 1
            distance = 0.0 if union == 0 else 1 - intersection / union
            if distance < best:
                best = distance
    return best


def _merge_near_duplicate_signatures(
    signatures: dict[tuple[int, int], int],
    representative_bbox: dict[int, Bbox],
    representative_pos: dict[int, tuple[int, int]],
    gray: Image.Image,
    origin_px: int,
    origin_py: int,
) -> tuple[dict[tuple[int, int], int], dict[int, Bbox]]:
    """Merge the fingerprints that represent the same symbol redrawn with a
    slight shift (sub-position noise), comparing the cells' real raster
    rendering with a small shift tolerance — see the docstring of
    `_RASTER_MERGE_MAX_JACCARD` and related constants for the full diagnosis
    that led to these thresholds. Greedy merge, from the most frequent
    fingerprint to the least frequent, never between two fingerprints that
    are both already frequent (a sign of two genuinely distinct symbols
    rather than a noisy variant of one). `gray`/`origin_px`/`origin_py` are
    the rendering already produced by `_build_symbol_signatures`
    (`_render_symbol_page_gray`) — never recomputed here, one whole-page
    rendering per file is enough (specification §10)."""
    counts = Counter(signatures.values())
    # Fingerprint 0 (no ink detected) is never merged with a real symbol: a
    # genuinely absent symbol is information in itself, not noise from a
    # present symbol.
    ordered = sorted((b for b in counts if b != 0), key=lambda b: -counts[b])
    remap: dict[int, int] = {0: 0}
    if not ordered:
        return dict(signatures), {}

    core_of = {
        b: _cell_ink_grid(gray, origin_px, origin_py, representative_pos[b], 0) for b in ordered
    }
    padded_of = {
        b: _cell_ink_grid(
            gray, origin_px, origin_py, representative_pos[b], _RASTER_SHIFT_TOLERANCE_PX
        )
        for b in ordered
    }
    area_of = {b: sum(sum(row) for row in core_of[b]) for b in ordered}

    canonical: list[int] = []
    for bitmap in ordered:
        merged_into: int | None = None
        for existing in canonical:
            if counts[existing] < counts[bitmap]:
                continue
            area_a, area_b = area_of[bitmap], area_of[existing]
            if area_a == 0 or area_b == 0:
                continue
            area_ratio = min(area_a, area_b) / max(area_a, area_b)
            if area_ratio < _RASTER_MERGE_MIN_AREA_RATIO:
                continue
            distance = _best_shifted_jaccard_distance(
                core_of[bitmap], padded_of[existing], _RASTER_SHIFT_TOLERANCE_PX
            )
            if distance <= _RASTER_MERGE_MAX_JACCARD:
                merged_into = existing
                break
        if merged_into is None:
            canonical.append(bitmap)
            remap[bitmap] = bitmap
        else:
            remap[bitmap] = merged_into

    merged_signatures = {pos: remap[bitmap] for pos, bitmap in signatures.items()}
    merged_bbox = {
        canon: representative_bbox[canon] for canon in canonical if canon in representative_bbox
    }
    return merged_signatures, merged_bbox


def _bucket_object(
    obj: Obj, grid: _GridGeometry, buckets: dict[tuple[int, int], list[Obj]]
) -> None:
    cx = (obj["x0"] + obj["x1"]) / 2
    cy = (obj["top"] + obj["bottom"]) / 2
    row0, col0 = grid.cell_of(cx, cy)
    if 0 <= row0 < grid.rows and 0 <= col0 < grid.columns:
        buckets[(row0, col0)].append(obj)


# --------------------------------------------------------------------------
# Final assembly: palette, cells, uncertainties
# --------------------------------------------------------------------------


def _symbol_key(index0: int) -> str:
    """Identical to `app/type_a.py::_symbol_key` (short key in "spreadsheet
    column" style) — a small pure function deliberately duplicated rather
    than imported from another connector's private module, to keep this
    module self-contained."""
    n = index0
    letters = ""
    while True:
        n, rem = divmod(n, 26)
        letters = chr(65 + rem) + letters
        if n == 0:
            return letters
        n -= 1


def _rgb_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_palette_and_cells(
    grid: _GridGeometry,
    cell_color_id: dict[tuple[int, int], int],
    canonical_colors: list[tuple[float, float, float]],
    cell_signature: dict[tuple[int, int], int],
    representative_bbox: dict[int, Bbox],
    grid_type: Literal["B", "C"],
    symbol_page_number: int | None,
) -> tuple[list[TypeBCPaletteEntry], list[int], list[int], list[DetectionWarning], float]:
    warnings: list[DetectionWarning] = []
    cells = [0] * (grid.columns * grid.rows)

    combo_counts: Counter[tuple[int, int]] = Counter()
    color_clusters: dict[int, Counter[int]] = defaultdict(Counter)
    for pos, color_id in cell_color_id.items():
        cluster_id = cell_signature.get(pos, 0) if grid_type == "C" else 0
        combo_counts[(color_id, cluster_id)] += 1
        color_clusters[color_id][cluster_id] += 1

    palette: list[TypeBCPaletteEntry] = []
    combo_index: dict[tuple[int, int], int] = {}
    dmc_distance: dict[int, float] = {}
    uncertain_color_codes: set[str] = set()

    for (color_id, cluster_id), _count in sorted(
        combo_counts.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        index = len(palette) + 1
        combo_index[(color_id, cluster_id)] = index
        rgb = canonical_colors[color_id]
        match = nearest_dmc(rgb)
        dmc_distance[index] = match.distance
        if match.distance > _UNCERTAIN_COLOR_DISTANCE:
            uncertain_color_codes.add(match.code)
        symbol_glyph = None
        if grid_type == "C" and cluster_id != 0 and symbol_page_number is not None:
            bbox = representative_bbox.get(cluster_id)
            if bbox is not None:
                symbol_glyph = SymbolGlyphLocation(page_number=symbol_page_number, bbox=bbox)
        palette.append(
            TypeBCPaletteEntry(
                code=match.code,
                name=match.name,
                # The colour actually extracted from the PDF is authoritative
                # for display (§1: "exact colour per cell") — far more
                # reliable here than the DMC catalogue's theoretical shade,
                # which only serves to match the code (`nearest_dmc`), never
                # used alone to decide a colour (§8.5: the legend text, when
                # there is one, always takes priority over colour — out of
                # scope for this module, which only has the colour).
                rgb_hex=_rgb_hex(rgb),
                symbol_key=_symbol_key(index - 1),
                symbol_glyph=symbol_glyph,
            )
        )

    uncertain_positions: set[tuple[int, int]] = set()
    for pos, color_id in cell_color_id.items():
        cluster_id = cell_signature.get(pos, 0) if grid_type == "C" else 0
        index = combo_index[(color_id, cluster_id)]
        row0, col0 = pos
        cells[row0 * grid.columns + col0] = index

        if combo_counts[(color_id, cluster_id)] == 1:
            uncertain_positions.add(pos)
        if dmc_distance[index] > _UNCERTAIN_COLOR_DISTANCE:
            uncertain_positions.add(pos)
        if grid_type == "C":
            counter = color_clusters[color_id]
            if len(counter) > 1:
                dominant_cluster, dominant_count = counter.most_common(1)[0]
                dominant_ratio = dominant_count / sum(counter.values())
                if dominant_ratio < 0.6 or cluster_id != dominant_cluster:
                    uncertain_positions.add(pos)

    total_colored = len(cell_color_id)
    fraction_uncertain = len(uncertain_positions) / total_colored if total_colored else 0.0
    penalty = min(0.4, fraction_uncertain)

    if uncertain_color_codes:
        warnings.append(
            DetectionWarning(
                code="type_bc.uncertain_dmc_match",
                params={"count": len(uncertain_color_codes)},
            )
        )
    if uncertain_positions:
        warnings.append(
            DetectionWarning(
                code="type_bc.uncertain_cells",
                params={"count": len(uncertain_positions)},
            )
        )

    uncertain_cells = sorted(row0 * grid.columns + col0 for row0, col0 in uncertain_positions)
    return palette, cells, uncertain_cells, warnings, penalty
