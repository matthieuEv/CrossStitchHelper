"""Automatic detection of type A (charting software export, specification
§4.3, §4.4 and §8.1-8.3).

A type A PDF embeds a custom symbol font where **one glyph = one symbol =
one colour**, plus a text legend that is authoritative on the DMC code and
the colour name (§8.5: the legend text is never replaced by a colorimetric
match when it is available).

Nothing here is hard-coded for the `cafe-brasserie-charting-export`
fixture: the symbol font is identified by its geometric regularity (many
glyphs of the same font tiling a regular grid, distinct from every other
font on the page), not by its PDF subset name (`AAAAAC+CROSSSTICH6` here,
arbitrary from one export to another). A different type A exporter, with
another font name and another legend layout, should still produce a usable
result — possibly with a lower confidence and warnings, never a silently
wrong result (mandatory rule of the `pdf-extraction-specialist`).

Pure module: no FastAPI/SQLAlchemy dependency. The `detect_type_a` entry
point never raises for a PDF that does not look like a type A export — it
returns `None`, letting the rest of the import pipeline (types B/C/E,
Lots 5 to 7) or the manual fallback (Lot 2) take over.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
from pdfplumber.page import Page

from app.dmc_catalog import nearest_dmc_among
from app.dmc_colors import FALLBACK_HEX, dmc_hex
from app.grid_lines import is_grid_ruling, line_length

# `app.schemas` only depends on Pydantic — importing it here does not break
# the module's purity (no FastAPI/SQLAlchemy dependency, see docstring).
from app.schemas import BackstitchSegment, DetectionWarning, FrenchKnot

# pdfplumber represents each positioned character/rectangle as a
# heterogeneous dictionary (`T_obj = Dict[str, Any]` in the library) — no
# public TypedDict to reuse here.
Char = dict[str, Any]

# Normalised colour of a small background rectangle (RGB, or grey level
# expanded to a triplet, rounded) — `None` when no rectangle could be
# associated with the glyph. See `_rect_color_under_char` for the details:
# this reference file draws, under each symbol glyph, a small rectangle
# filled with the real DMC colour (both on the legend and on the grid pages)
# — the same glyph is sometimes reused for two different colours (observed:
# the DMC 640 full-stitch glyph is also the DMC 3756 half-stitch glyph in
# this file), whereas the background colour stays reliable. The grid <->
# legend matching key is therefore the (glyph, background colour) pair,
# never the glyph alone.
Color = tuple[float, ...]
CellKey = tuple[str, Color | None]

# Minimum number of glyphs of a font to consider that it tiles a regular
# symbol grid (below that, it is probably just running text or a sparse
# legend).
_MIN_GRID_CHARS = 30
# Minimum number of distinct occupied columns/rows to speak of a "grid"
# rather than a mere alignment of a few characters.
_MIN_GRID_SPAN = 5
# Minimum fill density (observed glyphs / cells of the covered grid) below
# which the tiling is deemed too sparse to be a cross-stitch grid rather than
# a paragraph of text (which, at low tolerance, can also seem to "tile" with
# a fairly regular pitch — but always filling much less of its bounding
# rectangle: ~0.05-0.2 observed on running text versus ~0.9-1.0 on a real
# symbol grid, which fills almost every column/row combination of its
# tiling).
_MIN_GRID_DENSITY = 0.4

_DECLARED_DIMENSIONS_RE = re.compile(r"(\d+)\s*w\s*[Xx]\s*(\d+)\s*h\s*Stitches")
_FABRIC_COUNT_RE = re.compile(r"Fabric:[^\n,]*?(\d+)")
_SECTION_HEADER_RE = re.compile(r"^Floss Used for (.+?)\s*:")
_SECTION_HEADER_PREFIX = "Floss Used for "
_LEGEND_ROW_RE = re.compile(r"^(\S)\s*\d+\s*DMC\s+([A-Za-z0-9]+)\s+(.+)$")
# The "Back Stitches" and "French Knots" sections have no symbol glyph: their
# "Symbol" column is a **vector swatch** (a stroke, a dot) drawn in the exact
# colour used on the grid pages — measured on
# `cafe-brasserie-charting-export`, page 10. Their text lines therefore start
# directly with the number of strands.
_SAMPLE_LEGEND_ROW_RE = re.compile(r"^\d+\s+DMC\s+([A-Za-z0-9]+)\s+(.+)$")

# Stitch categories, in the order the exporter prints them. The keys are the
# normalised section headings (lowercase, compacted spaces): an exporter
# writing "Backstitch" rather than "Back Stitches" is recognised the same
# way, and an unknown heading is simply ignored (never an exception, never a
# section filed at random).
FULL = "full"
HALF = "half"
QUARTER = "quarter"
BACKSTITCH = "backstitch"
FRENCH_KNOT = "french_knot"

_SECTION_ALIASES: dict[str, str] = {
    "full stitches": FULL,
    "full stitch": FULL,
    "half stitches": HALF,
    "half stitch": HALF,
    "quarter stitches": QUARTER,
    "quarter stitch": QUARTER,
    "back stitches": BACKSTITCH,
    "back stitch": BACKSTITCH,
    "backstitches": BACKSTITCH,
    "backstitch": BACKSTITCH,
    "french knots": FRENCH_KNOT,
    "french knot": FRENCH_KNOT,
}

# Categories whose legend rows carry a vector swatch rather than a font
# glyph.
_SAMPLE_SECTIONS = frozenset({BACKSTITCH, FRENCH_KNOT})

# Tolerance, as a fraction of a cell, for considering that a stroke endpoint
# falls on the half-cell lattice (cell corner or cell midpoint). Measured on
# the reference fixture: 5,172 endpoints out of 5,172 fall within 0.02 cell
# of a multiple of 0.5 — the tolerance below is therefore generous without
# being permissive.
_SNAP_TOLERANCE = 0.08

# Fraction of the page's grid footprint an axis-aligned stroke must cover to
# be a ruling rather than a backstitch. A ruling crosses the grid from edge
# to edge; a backstitch, even long and perfectly straight along a cell
# boundary, stays local. Deliberately demanding: a first version filtered at
# 12 cells and removed real straight backstitches from the reference fixture
# (measured: -13% on DMC 310, -24% on DMC 938 compared with the lengths
# declared by the legend).
_RULING_MIN_SPAN_RATIO = 0.8

# Maximum size (in cells) of a knot's small solid shape. Measured: the
# fixture's knots are 0.885 cell, the page landmark arrows (margins, outside
# the pattern) exactly 1.0 cell — this threshold separates them, in addition
# to the colour filter, which remains the main signal.
_KNOT_MAX_CELLS = 0.95

# Lab distance beyond which a fallback colour match (no vector swatch in the
# legend) is deemed too doubtful to attach a stroke to a declared DMC code.
_FALLBACK_MAX_LAB_DISTANCE = 30.0

# Beyond this number of strokes, a page is not a legend page: see
# `_sample_colors_for_row`.
_MAX_LEGEND_PAGE_OBJECTS = 500


@dataclass
class SymbolGlyphLocation:
    """Position of one occurrence of the symbol glyph on the source PDF page
    — never the glyph itself (private font, unreadable outside this file),
    but enough for a caller outside this pure module
    (`app/imports_engine.py`, which already has PyMuPDF) to cut out a
    faithful raster preview from the rendered page. That, and not the raw
    glyph or a synthetic key, is what makes it possible to recover the real
    symbol as printed in the PDF — whatever the file, without depending on a
    list of symbols known in advance (symbols differ from one export to
    another)."""

    page_number: int
    """1-based, like `pdfplumber.page.Page.page_number`."""

    bbox: tuple[float, float, float, float]
    """`(x0, top, x1, bottom)`, same units and origin (top-left) as
    `pdfplumber` rectangles."""


@dataclass
class TypeAPaletteEntry:
    code: str
    """DMC code as printed in the legend, e.g. ``"310"`` or ``"B5200"``."""

    name: str
    """Colour name as printed in the legend."""

    symbol_key: str
    """Short, printable key for the UI — never the raw glyph of the PDF's
    private font (unreadable and not portable outside this file)."""

    rgb_hex: str
    """Approximate display colour — from `dmc_hex`, or `FALLBACK_HEX` if the
    code is missing from the local table."""

    symbol_glyph: SymbolGlyphLocation | None = None
    """Absent for a symbol not matched to a legend row (falls back to
    `symbol_key` when rendering) — see `SymbolGlyphLocation`."""

    categories: tuple[str, ...] = ()
    """Legend sections where this thread appears, among `FULL`, `HALF`,
    `QUARTER`, `BACKSTITCH`, `FRENCH_KNOT` (Lot 9). The same thread is often
    declared in several sections (e.g. DMC 742 as full stitches, backstitch
    *and* knots on the reference fixture): it then remains **a single
    palette entry**, never one per section — the palette is a list of
    threads, not a list of legend rows."""

    count_full: int = 0
    """Cells of `TypeAResult.cells` carrying this entry (full stitches)."""

    count_half: int = 0
    """Same for `TypeAResult.cells_half`."""

    count_quarter: int = 0
    """Same for `TypeAResult.cells_quarter`."""

    count_french_knots: int = 0
    """Knots of `TypeAResult.french_knots` carrying this entry."""

    backstitch_length_cells: float = 0.0
    """Cumulative length of this entry's `TypeAResult.backstitch` segments,
    **in cells** (grid unit) and not in centimetres: the conversion depends
    on the fabric count, exposed separately by `TypeAResult.fabric_count`
    (length in cm = `backstitch_length_cells * 2.54 / fabric_count`). No
    physical length is made up here when the fabric count is not declared by
    the PDF."""


@dataclass
class TypeAResult:
    columns: int
    rows: int
    cells: list[int]
    """Length `columns * rows`, row by row, (0,0) at the top left first.
    0 = empty cell, n = 1-based index into `palette`."""
    palette: list[TypeAPaletteEntry]
    confidence: float
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Never text already composed in French: a message code and its
    parameters, translated on the client (`import.warning.<code>`, Lot 8
    translation audit)."""

    cells_half: list[int] = field(default_factory=list)
    """1/2 stitches, same shape and same palette index space as `cells`
    (Lot 9). An **empty** list — not a grid of zeros — when the pattern has
    no 1/2 stitch, which maps to `Grid.layer_half = NULL`."""

    cells_quarter: list[int] = field(default_factory=list)
    """1/4 stitches, same convention as `cells_half`."""

    backstitch: list[BackstitchSegment] = field(default_factory=list)
    """Backstitch segments in **cell corner** coordinates of the assembled
    grid (0-based, (0,0) = top-left corner of cell (0,0)), see
    `app/schemas.py::BackstitchSegment`. `palette_index` is 1-based, like
    the values of `cells`."""

    french_knots: list[FrenchKnot] = field(default_factory=list)
    """Knots in **cell centre** coordinates ((0.5, 0.5) = centre of cell
    (0,0)), see `app/schemas.py::FrenchKnot`. `palette_index` is 1-based,
    like the values of `cells`."""

    fabric_count: int | None = None
    """Fabric count stated plainly by the PDF ("Fabric: Aida 16"), useful to
    convert `backstitch_length_cells` to centimetres and to pre-fill
    `Pattern.fabric_count`. `None` if the PDF does not declare it — never a
    made-up default value."""


@dataclass
class _GridPage:
    """A detected grid page, with its local symbol font."""

    index: int
    all_chars: list[Char]
    symbol_chars: list[Char]
    rects: list[Char]
    rect_index: dict[tuple[int, int], list[Char]]
    pitch_x: float
    pitch_y: float


@dataclass
class _LegendRow:
    section: str
    symbol_char: str | None
    """`None` for a vector-swatch section (backstitches, knots): these rows
    have no font glyph."""
    code: str
    name: str
    swatch_color: Color | None
    glyph: SymbolGlyphLocation | None
    sample_colors: tuple[Color, ...] = ()
    """Colours of the swatch strokes printed next to the row (see
    `_SAMPLE_LEGEND_ROW_RE`) — this is the colour -> DMC code matching key
    for backstitches and knots, measured in the file itself rather than
    guessed by colorimetric distance."""


@dataclass(frozen=True)
class _CornerLattice:
    """Lattice of the **cell corners** of a grid page, in absolute
    coordinates of the assembled grid.

    Derived from the printed rulings (which do fall exactly on the cell
    boundaries) rather than from the linear fit on the axis numbers
    (`_fit_axes`), which is anchored on the top-left corner of the *glyphs*
    and therefore carries a systematic offset of a few tenths of a cell —
    measured at ~0.27 cell on the reference fixture, enough to round a
    backstitch endpoint into the wrong cell. `_fit_axes` is still used, but
    only to anchor the lattice on the absolute numbering (whole-page offset,
    no sub-multiple involved)."""

    origin_x: float
    pitch_x: float
    offset_col: int
    origin_top: float
    pitch_y: float
    offset_row: int
    span_x: float
    """Width, in PDF points, of the page's grid area — used to recognise a
    ruling by its length (see `_RULING_MIN_SPAN_RATIO`)."""
    span_y: float

    def col(self, x: float) -> float:
        return (x - self.origin_x) / self.pitch_x + self.offset_col

    def row(self, top: float) -> float:
        return (top - self.origin_top) / self.pitch_y + self.offset_row


def detect_type_a(pdf_path: Path) -> TypeAResult | None:
    """Return `None` (never raising) if the PDF does not look like a type A
    export — see the module for the details of the detection."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        page_font_groups = [_group_by_font(page.chars) for page in pages]

        symbol_font = _pick_symbol_font(page_font_groups)
        if symbol_font is None:
            return None

        grid_pages = _collect_grid_pages(pages, page_font_groups, symbol_font)
        if not grid_pages:
            return None

        warnings: list[DetectionWarning] = []
        confidence = 1.0

        legend_rows = _parse_legend_rows(pages)
        if not any(row.section == FULL for row in legend_rows):
            warnings.append(DetectionWarning(code="type_a.missing_full_stitches_legend"))
            confidence -= 0.5

        legend = _build_palette(legend_rows)
        palette = legend.palette
        if legend.unknown_codes:
            warnings.append(
                DetectionWarning(
                    code="type_a.unknown_dmc_codes",
                    params={
                        "count": len(legend.unknown_codes),
                        "codes": ", ".join(legend.unknown_codes),
                    },
                )
            )
            confidence -= min(0.1, 0.02 * len(legend.unknown_codes))
        if legend.ambiguous_codes:
            warnings.append(
                DetectionWarning(
                    code="type_a.ambiguous_dmc_codes",
                    params={
                        "count": len(legend.ambiguous_codes),
                        "codes": ", ".join(legend.ambiguous_codes),
                    },
                )
            )
            confidence -= min(0.2, 0.05 * len(legend.ambiguous_codes))

        fits = _fit_all_axes(grid_pages, symbol_font)
        lattices = _build_all_lattices(pages, grid_pages, fits)
        placements, offset_placements, page_warnings, page_penalty = _place_grid_pages(
            grid_pages, legend.key_to_target, fits, lattices
        )
        warnings.extend(page_warnings)
        confidence -= page_penalty

        declared = _find_declared_dimensions(pages)
        columns, rows, dims_warning, dims_penalty = _resolve_dimensions(declared, placements)
        if dims_warning is not None:
            warnings.append(dims_warning)
            confidence -= dims_penalty

        if columns <= 0 or rows <= 0:
            return None

        layers = _fill_cells(columns, rows, placements, offset_placements, legend, palette)
        if layers.warning is not None:
            warnings.append(layers.warning)
        warnings.extend(layers.extra_warnings)
        confidence -= layers.penalty

        specials = _collect_special_stitches(pages, lattices, legend, columns, rows)
        warnings.extend(specials.warnings)
        confidence -= specials.penalty

        confidence = max(0.0, min(1.0, confidence))
        result = TypeAResult(
            columns=columns,
            rows=rows,
            cells=layers.full,
            palette=palette,
            confidence=confidence,
            warnings=warnings,
            cells_half=layers.half,
            cells_quarter=layers.quarter,
            backstitch=specials.backstitch,
            french_knots=specials.french_knots,
            fabric_count=_find_fabric_count(pages),
        )
        _count_palette_usage(result)
        result.warnings.extend(_cross_check_sections(legend, result))
        return result


# --------------------------------------------------------------------------
# Symbol font detection (main signal: regular tiling)
# --------------------------------------------------------------------------


def _group_by_font(chars: list[Char]) -> dict[str, list[Char]]:
    groups: dict[str, list[Char]] = {}
    for ch in chars:
        groups.setdefault(str(ch["fontname"]), []).append(ch)
    return groups


def _estimate_pitch(distinct_sorted: list[float]) -> float | None:
    """Median pitch between neighbouring distinct positions, ignoring the
    micro-gaps (< 1pt) caused by floating-point accumulation on glyphs meant
    to be at the same position (observed in practice: two positions
    0.2-0.3pt apart for the same real column/row)."""
    if len(distinct_sorted) < 2:
        return None
    diffs = [b - a for a, b in zip(distinct_sorted, distinct_sorted[1:], strict=False)]
    plausible = [d for d in diffs if d > 1.0]
    if not plausible:
        return None
    return statistics.median(plausible)


def _is_grid_like(chars: list[Char]) -> tuple[float, float] | None:
    """`(pitch_x, pitch_y)` if `chars` tile a sufficiently regular 2D grid,
    otherwise `None`. This is the main signal for spotting the symbol font —
    never a hard-coded font name (see the module docstring)."""
    if len(chars) < _MIN_GRID_CHARS:
        return None
    xs_distinct = sorted({round(float(c["x0"]), 1) for c in chars})
    tops_distinct = sorted({round(float(c["top"]), 1) for c in chars})
    pitch_x = _estimate_pitch(xs_distinct)
    pitch_y = _estimate_pitch(tops_distinct)
    if pitch_x is None or pitch_y is None:
        return None
    # A cross-stitch grid has roughly square cells; a paragraph of text
    # generally has a line spacing (vertical pitch) much larger than the
    # character advance (horizontal pitch) — too marked a pitch difference
    # between the two axes betrays running text, not a symbol grid.
    if not (0.4 <= pitch_x / pitch_y <= 2.5):
        return None
    min_x = min(float(c["x0"]) for c in chars)
    min_top = min(float(c["top"]) for c in chars)
    n_cols = len({round((float(c["x0"]) - min_x) / pitch_x) for c in chars})
    n_rows = len({round((float(c["top"]) - min_top) / pitch_y) for c in chars})
    if n_cols < _MIN_GRID_SPAN or n_rows < _MIN_GRID_SPAN:
        return None
    density = len(chars) / (n_cols * n_rows)
    if density < _MIN_GRID_DENSITY:
        return None
    return pitch_x, pitch_y


def _best_grid_font_on_page(font_groups: dict[str, list[Char]]) -> str | None:
    """The font most likely to be the symbol font on *this* page: the one
    that tiles a regular grid with the most glyphs."""
    best_font: str | None = None
    best_count = -1
    for fontname, chars in font_groups.items():
        if _is_grid_like(chars) is None:
            continue
        if len(chars) > best_count:
            best_count = len(chars)
            best_font = fontname
    return best_font


def _pick_symbol_font(page_font_groups: list[dict[str, list[Char]]]) -> str | None:
    """The PDF's global symbol font: the one that tiles a regular grid on
    the largest number of pages (a type A export repeats the same symbol
    font on all its grid pages)."""
    candidates: Counter[str] = Counter()
    for font_groups in page_font_groups:
        best = _best_grid_font_on_page(font_groups)
        if best is not None:
            candidates[best] += 1
    if not candidates:
        return None
    return candidates.most_common(1)[0][0]


def _collect_grid_pages(
    pages: list[Page],
    page_font_groups: list[dict[str, list[Char]]],
    symbol_font: str,
) -> list[_GridPage]:
    grid_pages: list[_GridPage] = []
    for index, (page, font_groups) in enumerate(zip(pages, page_font_groups, strict=True)):
        symbol_chars = font_groups.get(symbol_font)
        if not symbol_chars:
            continue
        metrics = _is_grid_like(symbol_chars)
        if metrics is None:
            continue
        pitch_x, pitch_y = metrics
        rects = list(page.rects)
        grid_pages.append(
            _GridPage(
                index=index,
                all_chars=list(page.chars),
                symbol_chars=symbol_chars,
                rects=rects,
                rect_index=_build_rect_index(rects, pitch_x, pitch_y),
                pitch_x=pitch_x,
                pitch_y=pitch_y,
            )
        )
    return grid_pages


# --------------------------------------------------------------------------
# Background colour associated with a glyph (glyph -> colour disambiguation)
# --------------------------------------------------------------------------


def _normalize_color(raw: Any) -> Color:
    """pdfplumber's `non_stroking_color` can be a scalar (grey level), an RGB
    triplet or a CMYK quadruplet depending on the PDF's colour space —
    always reduced to a comparable rounded tuple."""
    if isinstance(raw, int | float):
        value = round(float(raw), 4)
        return (value, value, value)
    if isinstance(raw, list | tuple):
        return tuple(round(float(v), 4) for v in raw)
    return ()


def _rect_color_under_char(char: Char, rects: list[Char]) -> Color | None:
    """Fill colour of the smallest rectangle covering the centre of glyph
    `char`. This reference file draws a small square of the real DMC colour
    under each glyph (legend and grid alike) — a more reliable signal than
    the glyph alone when the same glyph is reused for two different colours
    (see the `CellKey` docstring).

    Full scan of `rects` — only used for the legend (a handful of calls).
    Grid pages use `_rect_color_indexed` below: a full scan per glyph there
    would be O(glyphs × rectangles), i.e. several hundred million iterations
    on the reference fixture (measured while profiling — ~80% of the total
    time)."""
    cx = (float(char["x0"]) + float(char["x1"])) / 2
    ctop = (float(char["top"]) + float(char["bottom"])) / 2
    best: Char | None = None
    best_area = float("inf")
    for rect in rects:
        if not rect.get("fill"):
            continue
        x0, x1 = float(rect["x0"]), float(rect["x1"])
        top, bottom = float(rect["top"]), float(rect["bottom"])
        if not (x0 <= cx <= x1 and top <= ctop <= bottom):
            continue
        area = (x1 - x0) * (bottom - top)
        if area < best_area:
            best_area = area
            best = rect
    if best is None:
        return None
    return _normalize_color(best["non_stroking_color"])


def _build_rect_index(
    rects: list[Char], pitch_x: float, pitch_y: float
) -> dict[tuple[int, int], list[Char]]:
    """Group the filled rectangles per grid cell (same pitch as the symbol
    glyphs): a cell almost always contains a single small colour rectangle,
    so searching only a glyph's bucket (and its immediate neighbours, for
    edge rounding noise) replaces a scan of all the page's rectangles with a
    handful of candidates."""
    index: dict[tuple[int, int], list[Char]] = {}
    for rect in rects:
        if not rect.get("fill"):
            continue
        cx = (float(rect["x0"]) + float(rect["x1"])) / 2
        cy = (float(rect["top"]) + float(rect["bottom"])) / 2
        key = (round(cx / pitch_x), round(cy / pitch_y))
        index.setdefault(key, []).append(rect)
    return index


def _rect_color_indexed(
    char: Char,
    rect_index: dict[tuple[int, int], list[Char]],
    pitch_x: float,
    pitch_y: float,
) -> Color | None:
    """Equivalent of `_rect_color_under_char`, but via `rect_index`
    (`_build_rect_index`) rather than a full scan — see the latter for the
    details of the performance gain."""
    cx = (float(char["x0"]) + float(char["x1"])) / 2
    ctop = (float(char["top"]) + float(char["bottom"])) / 2
    base_key = (round(cx / pitch_x), round(ctop / pitch_y))
    best: Char | None = None
    best_area = float("inf")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for rect in rect_index.get((base_key[0] + dx, base_key[1] + dy), ()):
                x0, x1 = float(rect["x0"]), float(rect["x1"])
                top, bottom = float(rect["top"]), float(rect["bottom"])
                if not (x0 <= cx <= x1 and top <= ctop <= bottom):
                    continue
                area = (x1 - x0) * (bottom - top)
                if area < best_area:
                    best_area = area
                    best = rect
    if best is None:
        return None
    return _normalize_color(best["non_stroking_color"])


# --------------------------------------------------------------------------
# Text legend ("Floss Used for Full Stitches")
# --------------------------------------------------------------------------


def _section_of(text: str) -> str | None:
    """Stitch category of a "Floss Used for ... :" header, or `None` if the
    line is not a section header."""
    match = _SECTION_HEADER_RE.match(text)
    if match is None:
        return None
    label = " ".join(match.group(1).split()).lower()
    return _SECTION_ALIASES.get(label, "")


def _sample_colors_for_row(
    page: Page, top: float, bottom: float, text_x0: float
) -> tuple[Color, ...]:
    """Colours of the swatch strokes printed in the "Symbol" column of a
    legend row without a glyph: segments (backstitches) and small solid
    shapes (knots) located to the left of the text and at its height.

    Both colours of the same swatch are kept: the reference exporter draws
    each backstitch twice, a dark pass then a lighter pass on top (shadow +
    highlight), exactly as on the grid pages — both values must therefore be
    able to attach a grid stroke to this code."""
    colors: list[Color] = []
    middle = (top + bottom) / 2
    height = max(bottom - top, 1.0)
    candidates = [*page.lines, *page.curves]
    if len(candidates) > _MAX_LEGEND_PAGE_OBJECTS:
        # A legend page carries only a handful of strokes; beyond that, it is
        # a grid page (thousands of objects) where this per-row scan would be
        # expensive for nothing.
        return ()
    for obj in candidates:
        obj_middle = (float(obj["top"]) + float(obj["bottom"])) / 2
        if abs(obj_middle - middle) > height:
            continue
        if float(obj["x1"]) > text_x0:
            continue
        for key in ("stroking_color", "non_stroking_color"):
            color = _normalize_color(obj.get(key))
            if color and color not in colors:
                colors.append(color)
    return tuple(colors)


def _parse_legend_rows(pages: list[Page]) -> list[_LegendRow]:
    """All of the PDF's legend rows, each labelled with its section ("Full
    Stitches", "Half Stitches", ... — see `_SECTION_ALIASES`).

    Up to Lot 8 this reading stopped at the end of the full-stitch section;
    Lot 9 needs the following ones (1/2, 1/4, backstitch, knot). A section
    with an unknown heading interrupts the current section without filing
    anything into it by default: better to ignore rows than to attribute
    them to the wrong category."""
    rows: list[_LegendRow] = []
    for page in pages:
        rects = page.rects
        section: str | None = None
        for line in page.extract_text_lines():
            text = str(line["text"])
            if text.startswith(_SECTION_HEADER_PREFIX):
                section = _section_of(text) or None
                continue
            if section is None:
                continue
            if text.startswith("Symbol Strands"):
                continue

            if section in _SAMPLE_SECTIONS:
                sample_match = _SAMPLE_LEGEND_ROW_RE.match(text)
                if sample_match is None:
                    continue
                rows.append(
                    _LegendRow(
                        section=section,
                        symbol_char=None,
                        code=sample_match.group(1),
                        name=sample_match.group(2).strip(),
                        swatch_color=None,
                        glyph=None,
                        sample_colors=_sample_colors_for_row(
                            page,
                            float(line["top"]),
                            float(line["bottom"]),
                            float(line["x0"]),
                        ),
                    )
                )
                continue

            match = _LEGEND_ROW_RE.match(text)
            if match is None:
                continue
            row_chars = line.get("chars") or []
            first_char = row_chars[0] if row_chars else None
            swatch_color = _rect_color_under_char(first_char, rects) if first_char else None
            glyph = (
                SymbolGlyphLocation(
                    page_number=page.page_number,
                    bbox=(
                        float(first_char["x0"]),
                        float(first_char["top"]),
                        float(first_char["x1"]),
                        float(first_char["bottom"]),
                    ),
                )
                if first_char is not None
                else None
            )
            rows.append(
                _LegendRow(
                    section=section,
                    symbol_char=match.group(1),
                    code=match.group(2),
                    name=match.group(3).strip(),
                    swatch_color=swatch_color,
                    glyph=glyph,
                )
            )
    return rows


def _symbol_key(index0: int) -> str:
    """Short key in "spreadsheet column" style (A, B, ..., Z, AA, AB, ...) —
    stable, readable, and never the raw glyph of the private font."""
    n = index0
    letters = ""
    while True:
        n, rem = divmod(n, 26)
        letters = chr(65 + rem) + letters
        if n == 0:
            return letters
        n -= 1


@dataclass
class _Legend:
    """Everything the text legend tells us about the pattern's threads."""

    palette: list[TypeAPaletteEntry]
    key_to_target: dict[CellKey, tuple[int, str]]
    """(glyph, background colour) -> (1-based palette index, category) — the
    category decides which layer the cell is written to (`cells`,
    `cells_half` or `cells_quarter`), never the glyph alone."""
    sample_color_to_index: dict[Color, int]
    """Colour of a legend vector swatch -> 1-based palette index
    (backstitches and knots)."""
    fractional_glyph_to_target: dict[str, tuple[int, str]]
    """Glyph **alone** -> (palette index, category), for the fractional
    stitch sections. Used for glyphs placed in a cell corner rather than at
    its centre: the background colour under such a glyph is that of the
    stitch *already* occupying the cell, not its own — measured on the
    reference fixture, where DMC 3031's 4 quarter stitches are drawn on top
    of a DMC 3756 half-stitch cell. The usual (glyph, background colour) key
    would therefore designate the wrong thread there."""
    codes_by_section: dict[str, list[int]]
    """1-based palette indices declared in each section — used to
    cross-check what is *declared* against what is *extracted* (§7.3)."""
    unknown_codes: list[str]
    ambiguous_codes: list[str]


def _build_palette(legend_rows: list[_LegendRow]) -> _Legend:
    """One palette entry **per thread**, in legend order.

    Sections other than "Full Stitches" reuse the entry already created for
    the same DMC code when there is one (the general case: a thread stitched
    as full stitches is also used for backstitch) — the palette therefore
    remains the list of threads declared by the PDF ("Colours: 34" on the
    reference fixture), not a list of legend rows. A code repeated *within*
    the full-stitch section, however, remains two distinct entries: they are
    two different symbols, with two different counts (DMC 3776 on the
    fixture)."""
    palette: list[TypeAPaletteEntry] = []
    key_to_target: dict[CellKey, tuple[int, str]] = {}
    sample_color_to_index: dict[Color, int] = {}
    fractional: dict[str, tuple[int, str]] = {}
    codes_by_section: dict[str, list[int]] = {}
    index_by_code: dict[str, int] = {}
    unknown_codes: list[str] = []
    ambiguous_codes: list[str] = []

    for row in legend_rows:
        index = index_by_code.get(row.code) if row.section != FULL else None
        if index is None:
            hex_value = dmc_hex(row.code)
            if hex_value is None:
                unknown_codes.append(row.code)
                hex_value = FALLBACK_HEX
            index = len(palette) + 1
            palette.append(
                TypeAPaletteEntry(
                    code=row.code,
                    name=row.name,
                    symbol_key=_symbol_key(index - 1),
                    rgb_hex=hex_value,
                    symbol_glyph=row.glyph,
                )
            )
            index_by_code.setdefault(row.code, index)
        entry = palette[index - 1]
        if row.section not in entry.categories:
            entry.categories = (*entry.categories, row.section)
        codes_by_section.setdefault(row.section, []).append(index)

        for color in row.sample_colors:
            sample_color_to_index.setdefault(color, index)

        if row.symbol_char is None:
            continue
        if row.section == QUARTER or (row.section == HALF and row.symbol_char not in fractional):
            fractional[row.symbol_char] = (index, row.section)
        key: CellKey = (row.symbol_char, row.swatch_color)
        if key in key_to_target:
            # Two legend rows share the same glyph AND the same background
            # colour: their cells structurally cannot be told apart in the
            # grid — keep the first association (conservative behaviour) and
            # flag it clearly rather than silently overwriting.
            ambiguous_codes.append(row.code)
            continue
        key_to_target[key] = (index, row.section)

    return _Legend(
        palette=palette,
        key_to_target=key_to_target,
        sample_color_to_index=sample_color_to_index,
        fractional_glyph_to_target=fractional,
        codes_by_section=codes_by_section,
        unknown_codes=unknown_codes,
        ambiguous_codes=ambiguous_codes,
    )


# --------------------------------------------------------------------------
# Axis numbers (absolute column/row location of each grid page)
# --------------------------------------------------------------------------


def _most_common_font(chars: list[Char]) -> str:
    return Counter(str(c["fontname"]) for c in chars).most_common(1)[0][0]


def _chain_clusters(chars: list[Char], gap_limit: float) -> list[list[Char]]:
    """Group consecutive characters (in the PDF stream's original order)
    into multi-digit numbers, splitting as soon as a position gap exceeds
    `gap_limit`. Works equally for a regular horizontal number and for a
    rotated/vertically stacked one (observed on the reference fixture's row
    numbers) — the PDF stream order always gives the correct reading order,
    unlike a naive geometric sort by position."""
    clusters: list[list[Char]] = []
    current: list[Char] = []
    for c in chars:
        if current:
            prev = current[-1]
            dx = abs(float(c["x0"]) - float(prev["x0"]))
            dy = abs(float(c["top"]) - float(prev["top"]))
            if max(dx, dy) > gap_limit:
                clusters.append(current)
                current = []
        current.append(c)
    if current:
        clusters.append(current)
    return clusters


def _axis_points(candidates: list[Char], anchor: str) -> list[tuple[float, int]]:
    """`(position, value)` points for a linear position -> axis number fit.
    `anchor` is `"x"` for column numbers (position = smallest `x0` of the
    digit group) or `"top"` for row numbers (position = smallest `top`) —
    this "minimal starting edge" convention aligns the number's anchor with
    that of the grid's glyphs themselves (positioned by their top-left
    corner), whatever the visual stacking order of the digits."""
    if not candidates:
        return []
    # Keep only the margin area's majority font: filters out the noise of
    # other texts (page number, etc.) that would happen to fall in the same
    # geometric area.
    dominant_font = _most_common_font(candidates)
    filtered = [c for c in candidates if c["fontname"] == dominant_font]
    widths = [float(c["x1"]) - float(c["x0"]) for c in filtered]
    heights = [float(c["bottom"]) - float(c["top"]) for c in filtered]
    if not widths or not heights:
        return []
    unit = statistics.median(widths + heights)
    gap_limit = unit * 3.0
    points: list[tuple[float, int]] = []
    for cluster in _chain_clusters(filtered, gap_limit):
        text = "".join(str(c["text"]) for c in cluster)
        if not text.isdigit():
            continue
        if anchor == "x":
            position = min(float(c["x0"]) for c in cluster)
        else:
            position = min(float(c["top"]) for c in cluster)
        points.append((position, int(text)))
    return points


def _fit_axes(grid_page: _GridPage, symbol_font: str) -> tuple[float, float, float, float] | None:
    """`(a_col, b_col, a_row, b_row)` such that the absolute (1-based) column
    number of a symbol glyph at `x0` is `round(a_col + b_col*x0)`, and
    likewise for the row via `top`. `None` if there are not enough usable
    axis numbers on this page."""
    symbol_chars = grid_page.symbol_chars
    pitch_x, pitch_y = grid_page.pitch_x, grid_page.pitch_y
    min_sym_x = min(float(c["x0"]) for c in symbol_chars)
    max_sym_x = max(float(c["x1"]) for c in symbol_chars)
    min_sym_top = min(float(c["top"]) for c in symbol_chars)
    max_sym_top = max(float(c["bottom"]) for c in symbol_chars)

    digit_chars = [
        c
        for c in grid_page.all_chars
        if c["fontname"] != symbol_font
        and isinstance(c.get("text"), str)
        and str(c["text"]).isdigit()
    ]
    top_region = [
        c
        for c in digit_chars
        if float(c["top"]) < min_sym_top - pitch_y * 0.5
        and min_sym_x - 2 * pitch_x <= float(c["x0"]) <= max_sym_x + 2 * pitch_x
    ]
    left_region = [
        c
        for c in digit_chars
        if float(c["x0"]) < min_sym_x - pitch_x * 0.5
        and min_sym_top - 2 * pitch_y <= float(c["top"]) <= max_sym_top + 2 * pitch_y
    ]

    col_points = _axis_points(top_region, anchor="x")
    row_points = _axis_points(left_region, anchor="top")
    if len(col_points) < 2 or len(row_points) < 2:
        return None

    try:
        b_col, a_col = statistics.linear_regression(
            [p[0] for p in col_points], [p[1] for p in col_points]
        )
        b_row, a_row = statistics.linear_regression(
            [p[0] for p in row_points], [p[1] for p in row_points]
        )
    except statistics.StatisticsError:
        return None
    return a_col, b_col, a_row, b_row


# --------------------------------------------------------------------------
# Placing each page's glyphs in the absolute grid
# --------------------------------------------------------------------------


def _cell_key(char: Char, grid_page: _GridPage) -> CellKey:
    color = _rect_color_indexed(char, grid_page.rect_index, grid_page.pitch_x, grid_page.pitch_y)
    return (str(char["text"]), color)


def _set_placement(
    placements: dict[tuple[int, int], CellKey],
    position: tuple[int, int],
    key: CellKey,
    key_to_index: dict[CellKey, tuple[int, str]],
) -> None:
    """Write `key` at `position`, unless a value already recognised by the
    legend is present there and `key` is not. Needed because neighbouring
    grid pages sometimes overlap on a few edge columns/rows, and the observed
    type A export draws a greyed-out preview there (preview colour, not the
    thread's real colour) rather than an identical repetition — without this
    preference, the page processing order could let the greyed-out preview
    win over the neighbouring page's correct value (observed on the reference
    fixture). A real conflict between two values that are both recognised,
    or both unrecognised, is still settled by the last page processed, as
    intended."""
    existing = placements.get(position)
    conflict = existing is not None and existing != key
    if conflict and existing in key_to_index and key not in key_to_index:
        return
    placements[position] = key


def _fit_all_axes(
    grid_pages: list[_GridPage], symbol_font: str
) -> dict[int, tuple[float, float, float, float] | None]:
    """Each page's position -> axis number fit, computed only once: glyph
    placement (`_place_grid_pages`) and special stitch placement
    (`_collect_special_stitches`, Lot 9) must share exactly the same absolute
    frame, never two fits redone separately."""
    return {gp.index: _fit_axes(gp, symbol_font) for gp in grid_pages}


def _is_offset_in_cell(char: Char, lattice: _CornerLattice) -> bool:
    """True if the glyph is not centred in its cell but placed in one of its
    quadrants — the way this exporter draws a fractional stitch **on top
    of** a cell already occupied by another stitch.

    Measured on the reference fixture: 48,310 glyphs out of 48,314 are
    exactly at the centre of their cell, the other 4 at (0.25, 0.27) — they
    are precisely the 4 quarter stitches declared by the legend."""
    col_fraction = lattice.col((float(char["x0"]) + float(char["x1"])) / 2) % 1.0
    row_fraction = lattice.row((float(char["top"]) + float(char["bottom"])) / 2) % 1.0
    return abs(col_fraction - 0.5) > 0.15 or abs(row_fraction - 0.5) > 0.15


def _place_grid_pages(
    grid_pages: list[_GridPage],
    key_to_index: dict[CellKey, tuple[int, str]],
    fits: dict[int, tuple[float, float, float, float] | None],
    lattices: dict[int, _CornerLattice | None],
) -> tuple[
    dict[tuple[int, int], CellKey], dict[tuple[int, int], str], list[DetectionWarning], float
]:
    """Place each symbol glyph in absolute 0-based coordinates
    `(row0, col0) -> (glyph, background colour)`.

    Second return value (Lot 9): the glyphs **offset within their cell**
    (see `_is_offset_in_cell`), kept apart from normal placement. Mixing them
    in would lose a full or half stitch in favour of the fractional stitch
    drawn on top — exactly the regression Lot 9 must never introduce."""
    placements: dict[tuple[int, int], CellKey] = {}
    offset_placements: dict[tuple[int, int], str] = {}
    warnings: list[DetectionWarning] = []
    penalty = 0.0
    fallback_col_offset = 0

    for grid_page in grid_pages:
        fit = fits.get(grid_page.index)
        lattice = lattices.get(grid_page.index)
        if fit is None:
            page_number = grid_page.index + 1
            warnings.append(
                DetectionWarning(
                    code="type_a.axis_numbers_missing_on_page",
                    params={"page": page_number},
                )
            )
            penalty += 0.15
            min_x = min(float(c["x0"]) for c in grid_page.symbol_chars)
            min_top = min(float(c["top"]) for c in grid_page.symbol_chars)
            local_cols = {
                round((float(c["x0"]) - min_x) / grid_page.pitch_x) for c in grid_page.symbol_chars
            }
            col_span = max(local_cols) + 1 if local_cols else 0
            for c in grid_page.symbol_chars:
                col0 = fallback_col_offset + round((float(c["x0"]) - min_x) / grid_page.pitch_x)
                row0 = round((float(c["top"]) - min_top) / grid_page.pitch_y)
                cell_key = _cell_key(c, grid_page)
                _set_placement(placements, (row0, col0), cell_key, key_to_index)
            fallback_col_offset += col_span
            continue

        a_col, b_col, a_row, b_row = fit
        for c in grid_page.symbol_chars:
            abs_col = round(a_col + b_col * float(c["x0"]))
            abs_row = round(a_row + b_row * float(c["top"]))
            col0 = abs_col - 1
            row0 = abs_row - 1
            if col0 < 0 or row0 < 0:
                continue
            if lattice is not None and _is_offset_in_cell(c, lattice):
                offset_col = math.floor(lattice.col((float(c["x0"]) + float(c["x1"])) / 2))
                offset_row = math.floor(lattice.row((float(c["top"]) + float(c["bottom"])) / 2))
                if offset_col >= 0 and offset_row >= 0:
                    offset_placements[(offset_row, offset_col)] = str(c["text"])
                continue
            _set_placement(placements, (row0, col0), _cell_key(c, grid_page), key_to_index)

    return placements, offset_placements, warnings, penalty


# --------------------------------------------------------------------------
# Special stitches: backstitches and knots (Lot 9)
# --------------------------------------------------------------------------


def _line_points(line: Char) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """A segment's real endpoints `((x, top), (x, top))`, read from `pts`
    (top-down coordinates, like `top`) rather than from the bbox.

    Essential: a segment's bbox loses its diagonal's direction — an
    ascending and a descending diagonal have exactly the same bbox. Measured
    on the reference fixture: 36 of the 56 backstitch diagonals on its page 1
    are descending and would all be drawn the wrong way round if
    `(x0, top) -> (x1, bottom)` were read."""
    pts = line.get("pts")
    if not isinstance(pts, list | tuple) or len(pts) != 2:
        return None
    (ax, ay), (bx, by) = pts[0], pts[1]
    return (float(ax), float(ay)), (float(bx), float(by))


def _lattice_axis(positions: list[float]) -> tuple[float, float] | None:
    """`(origin, pitch)` of the regular lattice that best fits `positions`
    (the x coordinates of the vertical rulings, or the y coordinates of the
    horizontal ones). Regression on lattice indices rather than on rank: a
    cell boundary with no printed ruling (replaced by the decimal ruling, or
    hidden by the border) does not shift everything after it."""
    uniq = sorted({round(p, 2) for p in positions})
    if len(uniq) < 3:
        return None
    diffs = [b - a for a, b in zip(uniq, uniq[1:], strict=False) if b - a > 1.0]
    if len(diffs) < 2:
        return None
    pitch = statistics.median(diffs)
    if pitch <= 0:
        return None
    indices = [round((p - uniq[0]) / pitch) for p in uniq]
    if len(set(indices)) < 3:
        return None
    try:
        slope, intercept = statistics.linear_regression(indices, uniq)
    except statistics.StatisticsError:
        return None
    if slope <= 0:
        return None
    return intercept, slope


def _majority_offset(counts: Counter[int], total: int) -> int | None:
    """Majority integer offset, only if there is consensus (at least 80% of
    the glyphs) — otherwise the ruling lattice does not describe the same
    grid as the symbols, and it is better to give up this page's special
    stitches than to misplace them."""
    if not counts or total <= 0:
        return None
    offset, hits = counts.most_common(1)[0]
    if hits / total < 0.8:
        return None
    return offset


def _build_corner_lattice(
    page: Page,
    grid_page: _GridPage,
    fit: tuple[float, float, float, float],
) -> _CornerLattice | None:
    """Lattice of `page`'s cell corners, in absolute coordinates — see
    `_CornerLattice` for why the axis number fit is not reused directly."""
    chars = grid_page.symbol_chars
    min_x = min(float(c["x0"]) for c in chars)
    max_x = max(float(c["x1"]) for c in chars)
    min_top = min(float(c["top"]) for c in chars)
    max_top = max(float(c["bottom"]) for c in chars)
    span_x = max_x - min_x
    span_y = max_top - min_top
    if span_x <= 0 or span_y <= 0:
        return None

    verticals: list[float] = []
    horizontals: list[float] = []
    for line in page.lines:
        points = _line_points(line)
        if points is None:
            continue
        (ax, ay), (bx, by) = points
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx < 0.5 and dy >= 0.8 * span_y:
            verticals.append(ax)
        elif dy < 0.5 and dx >= 0.8 * span_x:
            horizontals.append(ay)

    lattice_x = _lattice_axis(verticals)
    lattice_y = _lattice_axis(horizontals)
    if lattice_x is None or lattice_y is None:
        return None
    origin_x, pitch_x = lattice_x
    origin_top, pitch_y = lattice_y

    a_col, b_col, a_row, b_row = fit
    col_offsets: Counter[int] = Counter()
    row_offsets: Counter[int] = Counter()
    for char in chars:
        x0 = float(char["x0"])
        top = float(char["top"])
        col_offsets[round(a_col + b_col * x0) - 1 - math.floor((x0 - origin_x) / pitch_x)] += 1
        row_offsets[round(a_row + b_row * top) - 1 - math.floor((top - origin_top) / pitch_y)] += 1
    offset_col = _majority_offset(col_offsets, len(chars))
    offset_row = _majority_offset(row_offsets, len(chars))
    if offset_col is None or offset_row is None:
        return None

    return _CornerLattice(
        origin_x=origin_x,
        pitch_x=pitch_x,
        offset_col=offset_col,
        origin_top=origin_top,
        pitch_y=pitch_y,
        offset_row=offset_row,
        span_x=span_x,
        span_y=span_y,
    )


def _build_all_lattices(
    pages: list[Page],
    grid_pages: list[_GridPage],
    fits: dict[int, tuple[float, float, float, float] | None],
) -> dict[int, _CornerLattice | None]:
    """Corner lattice of each grid page, computed only once and shared by
    glyph placement and special stitch placement."""
    lattices: dict[int, _CornerLattice | None] = {}
    for grid_page in grid_pages:
        fit = fits.get(grid_page.index)
        lattices[grid_page.index] = (
            _build_corner_lattice(pages[grid_page.index], grid_page, fit)
            if fit is not None
            else None
        )
    return lattices


def _snap_half(value: float) -> tuple[float, bool]:
    """Value snapped to the nearest half-multiple (cell corner or cell
    midpoint) and a flag saying whether it really fell there. An exporter
    that placed its backstitches elsewhere is never forcibly distorted: the
    raw value is kept and flagged."""
    snapped = round(value * 2) / 2
    return (snapped, True) if abs(value - snapped) <= _SNAP_TOLERANCE else (round(value, 3), False)


@dataclass
class _SpecialStitches:
    backstitch: list[BackstitchSegment] = field(default_factory=list)
    french_knots: list[FrenchKnot] = field(default_factory=list)
    warnings: list[DetectionWarning] = field(default_factory=list)
    penalty: float = 0.0


def _color_resolver(
    legend: _Legend, section: str
) -> tuple[dict[Color, int], dict[str, int], bool]:
    """`(exact colours, declared codes, colorimetric fallback)` for a
    swatch section.

    The main signal is the **exact equality** between a grid stroke's colour
    and that of the swatch printed in the legend: a correspondence measured
    in the file, not a resemblance. It is essential here — on the reference
    fixture, the exporter draws the DMC 310 "Black" backstitch in
    (35, 40, 29) and DMC 938 in (64, 54, 34), two values a simple Lab nearest
    neighbour would assign to the wrong code (verified: 938 and 3031 are
    swapped). Perceptual matching is only a fallback, flagged as such."""
    indices = set(legend.codes_by_section.get(section, ()))
    colors = {
        color: index for color, index in legend.sample_color_to_index.items() if index in indices
    }
    codes = {
        legend.palette[index - 1].code: index
        for index in indices
        if legend.palette[index - 1].code
    }
    return colors, codes, not colors and bool(codes)


def _index_for_color(
    color: Color,
    exact: dict[Color, int],
    codes: dict[str, int],
    fallback: bool,
    cache: dict[Color, int | None],
) -> int | None:
    """Palette index of a stroke, by exact colour then (only if the legend
    has no swatch) by Lab nearest neighbour among the section's declared
    codes."""
    index = exact.get(color)
    if index is not None:
        return index
    if not fallback or len(color) < 3:
        return None
    if color in cache:
        return cache[color]
    rgb = (color[0], color[1], color[2])
    match = nearest_dmc_among(rgb, codes)
    resolved: int | None = None
    if match is not None and match.distance <= _FALLBACK_MAX_LAB_DISTANCE:
        resolved = codes.get(match.code)
    cache[color] = resolved
    return resolved


def _object_colors(obj: Char) -> tuple[Color, ...]:
    stroking = _normalize_color(obj.get("stroking_color"))
    non_stroking = _normalize_color(obj.get("non_stroking_color"))
    return tuple(color for color in (stroking, non_stroking) if color)


@dataclass(frozen=True)
class _ColorMatcher:
    """Stroke colour -> palette entry matching, for a swatch section (see
    `_color_resolver`)."""

    exact: dict[Color, int]
    codes: dict[str, int]
    fallback: bool
    cache: dict[Color, int | None]

    def index_of(self, obj: Char) -> int | None:
        for color in _object_colors(obj):
            index = _index_for_color(color, self.exact, self.codes, self.fallback, self.cache)
            if index is not None:
                return index
        return None

    def __bool__(self) -> bool:
        return bool(self.codes)


def _collect_special_stitches(
    pages: list[Page],
    lattices: dict[int, _CornerLattice | None],
    legend: _Legend,
    columns: int,
    rows: int,
) -> _SpecialStitches:
    """Backstitches and knots from all grid pages, brought into the absolute
    frame of the assembled grid.

    Three filters, in this order (backed by measurements, see the Lot 9
    report):

    1. **colour** — only a stroke whose colour is that of a legend swatch is
       kept. This filter is what discards in one go the rulings, the page
       landmark arrows, the manual annotations left in the PDF (system-blue
       strokes on two of the fixture's pages) and above all the **greyed-out
       preview copies** each page draws in its overlap strip with the
       neighbouring page (measured: 8 extra washed-out shades, never present
       anywhere other than on top of an already counted stroke);
    2. **shape** — an axis-aligned stroke lying on a cell boundary *and*
       long enough to cross the grid remains a ruling, even if its colour
       matches (the case of a pattern whose backstitch would be black like
       the grid); a knot must be a small solid shape smaller than a cell;
    3. **footprint** — anything falling outside the bounds of the assembled
       grid is discarded (roadmap Lot 9 §3: a decorative cover-page
       backstitch must never be imported as something to stitch). Legend
       pages are never scanned here anyway.
    """
    result = _SpecialStitches()
    cache: dict[Color, int | None] = {}
    back = _ColorMatcher(*_color_resolver(legend, BACKSTITCH), cache=cache)
    knot = _ColorMatcher(*_color_resolver(legend, FRENCH_KNOT), cache=cache)
    if not back and not knot:
        return result

    segments: dict[tuple[float, float, float, float, int], BackstitchSegment] = {}
    knots: dict[tuple[float, float, int], FrenchKnot] = {}
    skipped_pages: list[int] = []
    off_grid = 0
    unsnapped = 0

    for page_index, lattice in sorted(lattices.items()):
        page = pages[page_index]
        if lattice is None:
            skipped_pages.append(page_index + 1)
            continue

        ruling_min_length = _RULING_MIN_SPAN_RATIO * min(lattice.span_x, lattice.span_y)
        for line in page.lines:
            index = back.index_of(line)
            if index is None:
                continue
            points = _line_points(line)
            if points is None:
                continue
            (ax, ay), (bx, by) = points
            if is_grid_ruling(
                ax,
                ay,
                bx,
                by,
                origin_x=lattice.origin_x,
                origin_top=lattice.origin_top,
                pitch_x=lattice.pitch_x,
                pitch_y=lattice.pitch_y,
                min_length=ruling_min_length,
            ):
                continue
            if line_length(ax, ay, bx, by) < 0.5:
                continue
            x1, ok_x1 = _snap_half(lattice.col(ax))
            y1, ok_y1 = _snap_half(lattice.row(ay))
            x2, ok_x2 = _snap_half(lattice.col(bx))
            y2, ok_y2 = _snap_half(lattice.row(by))
            unsnapped += sum(1 for ok in (ok_x1, ok_y1, ok_x2, ok_y2) if not ok)
            if not _within_grid(x1, y1, columns, rows) or not _within_grid(x2, y2, columns, rows):
                off_grid += 1
                continue
            # Canonical order of the two endpoints: the same segment drawn in
            # one direction on one page and in the other on the neighbouring
            # page (overlap strip) must only count once.
            (ux, uy), (vx, vy) = sorted([(x1, y1), (x2, y2)])
            segments.setdefault(
                (ux, uy, vx, vy, index),
                BackstitchSegment(x1=ux, y1=uy, x2=vx, y2=vy, palette_index=index),
            )

        for curve in page.curves:
            if not curve.get("fill"):
                continue
            width = float(curve["x1"]) - float(curve["x0"])
            height = float(curve["bottom"]) - float(curve["top"])
            if width > _KNOT_MAX_CELLS * lattice.pitch_x:
                continue
            if height > _KNOT_MAX_CELLS * lattice.pitch_y:
                continue
            index = knot.index_of(curve)
            if index is None:
                continue
            x, _ok_x = _snap_half(lattice.col((float(curve["x0"]) + float(curve["x1"])) / 2))
            y, _ok_y = _snap_half(lattice.row((float(curve["top"]) + float(curve["bottom"])) / 2))
            if not _within_grid(x, y, columns, rows):
                off_grid += 1
                continue
            knots.setdefault((x, y, index), FrenchKnot(x=x, y=y, palette_index=index))

    result.backstitch = sorted(
        segments.values(), key=lambda s: (s.y1, s.x1, s.y2, s.x2, s.palette_index)
    )
    result.french_knots = sorted(knots.values(), key=lambda k: (k.y, k.x, k.palette_index))

    if skipped_pages:
        result.warnings.append(
            DetectionWarning(
                code="type_a.special_stitches_page_skipped",
                params={
                    "count": len(skipped_pages),
                    "pages": ", ".join(str(page) for page in skipped_pages),
                },
            )
        )
        result.penalty += min(0.2, 0.05 * len(skipped_pages))
    if back.fallback or knot.fallback:
        result.warnings.append(
            DetectionWarning(
                code="type_a.special_stitches_colour_fallback",
                params={
                    "backstitch": len(result.backstitch),
                    "french_knots": len(result.french_knots),
                },
            )
        )
        result.penalty += 0.1
    if off_grid:
        result.warnings.append(
            DetectionWarning(code="type_a.special_stitches_off_grid", params={"count": off_grid})
        )
    if unsnapped:
        result.warnings.append(
            DetectionWarning(
                code="type_a.backstitch_endpoints_unsnapped", params={"count": unsnapped}
            )
        )
        result.penalty += 0.05

    return result


def _within_grid(x: float, y: float, columns: int, rows: int) -> bool:
    epsilon = 0.01
    return -epsilon <= x <= columns + epsilon and -epsilon <= y <= rows + epsilon


def _cross_check_sections(legend: _Legend, result: TypeAResult) -> list[DetectionWarning]:
    """Cross-check between what the legend **declares** and what was
    **extracted** (roadmap Lot 9 §4, specification §7.3): a thread declared
    as 1/2, 1/4, backstitch or knot of which nothing was found in the grid is
    flagged, rather than letting it seem that the pattern has none.

    Only the legend on the text pages is used here. The reference file's
    "Usage Summary" page, for its part, remains **exclusively** the tests'
    independent ground truth (`backend/tests/test_type_a.py`): consuming it
    in the engine as well would amount to validating the extraction against
    its own source and would no longer prove anything."""
    warnings: list[DetectionWarning] = []
    found: dict[str, set[int]] = {
        BACKSTITCH: {segment.palette_index for segment in result.backstitch},
        FRENCH_KNOT: {knot.palette_index for knot in result.french_knots},
        HALF: {value for value in result.cells_half if value},
        QUARTER: {value for value in result.cells_quarter if value},
    }
    for section in (HALF, QUARTER, BACKSTITCH, FRENCH_KNOT):
        declared = set(legend.codes_by_section.get(section, ()))
        missing = sorted(declared - found[section])
        if not missing:
            continue
        warnings.append(
            DetectionWarning(
                code=f"type_a.{section}_codes_missing",
                params={
                    "count": len(missing),
                    "codes": ", ".join(legend.palette[index - 1].code for index in missing),
                },
            )
        )
    return warnings


# --------------------------------------------------------------------------
# Dimensions et assemblage final
# --------------------------------------------------------------------------


def _find_declared_dimensions(pages: list[Page]) -> tuple[int, int] | None:
    """Dimensions stated plainly by the PDF itself (e.g. `"255w X 180h
    Stitches"`) — preferred over the extent inferred from the assembled grid
    when available (specification §7.2 step 6)."""
    for page in pages:
        match = _DECLARED_DIMENSIONS_RE.search(page.extract_text())
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None


def _find_fabric_count(pages: list[Page]) -> int | None:
    """Fabric count stated plainly ("Fabric: Aida 16, White"), useful to
    convert a backstitch length measured in cells into centimetres. `None` if
    the PDF does not declare it: no default value is made up (a wrong
    physical length would be worse than none)."""
    for page in pages:
        match = _FABRIC_COUNT_RE.search(page.extract_text())
        if match is None:
            continue
        count = int(match.group(1))
        if 6 <= count <= 40:
            return count
    return None


def _resolve_dimensions(
    declared: tuple[int, int] | None,
    placements: dict[tuple[int, int], CellKey],
) -> tuple[int, int, DetectionWarning | None, float]:
    max_col_seen = max((col0 for _row0, col0 in placements), default=-1) + 1
    max_row_seen = max((row0 for row0, _col0 in placements), default=-1) + 1

    if declared is None:
        return (
            max_col_seen,
            max_row_seen,
            DetectionWarning(code="type_a.dimensions_inferred"),
            0.05,
        )

    columns, rows = declared
    if columns != max_col_seen or rows != max_row_seen:
        warning = DetectionWarning(
            code="type_a.dimensions_mismatch",
            params={
                "declared_columns": columns,
                "declared_rows": rows,
                "seen_columns": max_col_seen,
                "seen_rows": max_row_seen,
            },
        )
        return columns, rows, warning, 0.1
    return columns, rows, None, 0.0


def _unmapped_symbol_key(symbol_char: str, used: set[str]) -> str:
    """Stable key derived from the glyph's code point (never the raw glyph —
    see `TypeAPaletteEntry.symbol_key`), with a suffix if the same glyph
    already appears under another unrecognised colour."""
    base = f"U+{ord(symbol_char):04X}"
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    key = f"{base}-{suffix}"
    used.add(key)
    return key


@dataclass
class _Layers:
    """The three cell layers of a type A pattern. `half`/`quarter` are empty
    when the legend declares no stitch in that category — never a grid of
    zeros (see `TypeAResult.cells_half`)."""

    full: list[int]
    half: list[int] = field(default_factory=list)
    quarter: list[int] = field(default_factory=list)
    warning: DetectionWarning | None = None
    extra_warnings: list[DetectionWarning] = field(default_factory=list)
    penalty: float = 0.0


def _fill_cells(
    columns: int,
    rows: int,
    placements: dict[tuple[int, int], CellKey],
    offset_placements: dict[tuple[int, int], str],
    legend: _Legend,
    palette: list[TypeAPaletteEntry],
) -> _Layers:
    """Distribute the placed glyphs into the layer of their **category**.

    A given symbol belongs to a single legend section only (full, 1/2 or
    1/4): it is that section, and not a guess about the glyph's shape, that
    decides the layer. A symbol not matched to the legend is still handled as
    before Lot 9 — an explicit "Unrecognised symbol" entry in the full-stitch
    layer, never a silently empty cell."""
    key_to_target = legend.key_to_target
    layers = {
        FULL: [0] * (columns * rows),
        HALF: [0] * (columns * rows),
        QUARTER: [0] * (columns * rows),
    }
    used: dict[str, int] = {FULL: 0, HALF: 0, QUARTER: 0}
    unmapped_index: dict[CellKey, int] = {}
    used_symbol_keys = {entry.symbol_key for entry in palette}
    affected_cells = 0
    total_placed = 0
    unmatched_offsets = 0

    for (row0, col0), glyph in offset_placements.items():
        if row0 >= rows or col0 >= columns:
            continue
        target = legend.fractional_glyph_to_target.get(glyph)
        if target is None:
            # Offset glyph the legend attaches to no fractional section:
            # better to flag and ignore it than to write it into the
            # full-stitch layer, where it would skew an already correct
            # count.
            unmatched_offsets += 1
            continue
        index, category = target
        if category in layers:
            layers[category][row0 * columns + col0] = index
            used[category] += 1

    for (row0, col0), key in placements.items():
        if row0 >= rows or col0 >= columns:
            continue
        total_placed += 1
        target = key_to_target.get(key)
        if target is None:
            if key not in unmapped_index:
                symbol_char = key[0]
                palette.append(
                    TypeAPaletteEntry(
                        code="",
                        name="Symbole non reconnu",
                        symbol_key=_unmapped_symbol_key(symbol_char, used_symbol_keys),
                        rgb_hex=FALLBACK_HEX,
                    )
                )
                unmapped_index[key] = len(palette)
            target = (unmapped_index[key], FULL)
            affected_cells += 1
        index, category = target
        if category not in layers:
            # Legend section without a cell layer (backstitches, knots): a
            # glyph should never be attached to it, but better to ignore it
            # than to write it into the wrong layer.
            continue
        layers[category][row0 * columns + col0] = index
        used[category] += 1

    result = _Layers(
        full=layers[FULL],
        half=layers[HALF] if used[HALF] else [],
        quarter=layers[QUARTER] if used[QUARTER] else [],
    )
    if unmapped_index:
        result.warning = DetectionWarning(
            code="type_a.unmapped_symbols",
            params={"count": len(unmapped_index), "cells": affected_cells},
        )
        fraction = affected_cells / total_placed if total_placed else 0.0
        result.penalty = min(0.4, fraction)
    if unmatched_offsets:
        result.extra_warnings.append(
            DetectionWarning(
                code="type_a.fractional_glyphs_unmatched",
                params={"count": unmatched_offsets},
            )
        )
        result.penalty += 0.05
    return result


def _count_palette_usage(result: TypeAResult) -> None:
    """Record on each palette entry what actually references it in the
    assembled grid — counts per category and cumulative backstitch length.
    Computed here, only once, rather than left to the caller: it is the same
    data a printed legend table shows, and it must exist in a single place
    only."""
    for entry in result.palette:
        entry.count_full = 0
        entry.count_half = 0
        entry.count_quarter = 0
        entry.count_french_knots = 0
        entry.backstitch_length_cells = 0.0

    def tally(cells: list[int], attribute: str) -> None:
        for index, count in Counter(cells).items():
            if index <= 0 or index > len(result.palette):
                continue
            entry = result.palette[index - 1]
            setattr(entry, attribute, getattr(entry, attribute) + count)

    tally(result.cells, "count_full")
    tally(result.cells_half, "count_half")
    tally(result.cells_quarter, "count_quarter")
    for knot in result.french_knots:
        if 0 < knot.palette_index <= len(result.palette):
            result.palette[knot.palette_index - 1].count_french_knots += 1
    for segment in result.backstitch:
        if 0 < segment.palette_index <= len(result.palette):
            entry = result.palette[segment.palette_index - 1]
            entry.backstitch_length_cells += math.hypot(
                segment.x2 - segment.x1, segment.y2 - segment.y1
            )
