"""Automatic detection of type E (closed catalogue of reused bitmap images,
colour + symbol already combined in each image — specification §4.3, §4.4,
Lot 7).

Unlike types A (symbol font, `app/type_a.py`) and B/C (rectangles + vector
paths, `app/type_bc.py`), a type E grid page has **no positioned text, no
colour rectangle, no vector path**: the whole grid is made of small bitmap
images reused hundreds or thousands of times. Identifying a cell is
therefore an *image classification problem over a small closed catalogue*,
never a direct reading of a colour or a glyph.

**Measurements taken on the only fixture of this type
(`river-and-mountains-laserarts/RiverAndMountains-CS.pdf`, 18 pages,
publisher LaserArtsDesigns) before writing a single line of this module** —
see also `fixtures/README.md`:

- The real grid pages (2 to 16 in this file) form a mosaic 5 pages wide x
  3 pages high. Each places images of a single uniform size (64x64 px),
  accounting for 100% of its placements (`dominant_frac`) — never a mix of
  sizes.
- Page 1 (photorealistic preview) mixes TWO image sizes (48x48 and
  64x64 px) for an impasto-style texture rendering: its dominant size covers
  only **69.8%** of its 40,084 placements, far below
  `_MIN_DOMINANT_SIZE_FRACTION` — that is what excludes it, never its
  "page 1" position assumed a priori (cf. `CLAUDE.md`: never assume a fixed
  structure without measuring it).
- Page 18 (assembly map of the 15 grid pages, never a working page) places
  much larger (207x294 pt) and **non-square** images (width/height ratio
  ≈ 0.70) — excluded by `_MAX_ASPECT_DEVIATION`, far below the threshold
  measured here.
- The legend page (17 in this file) reuses the same 64x64 images as the
  grid pages (same symbols, as previews): neither the image size nor the
  reuse rate is enough to exclude it. It is the absence of axis text (see
  `_fit_axes` below) that excludes it: its images are aligned in a single
  vertical column (one legend row per colour), never tiled on a grid with
  two numbered axes.
- **Real number of distinct images used by the grid pages: 20, not ~531 or
  ~41.** Measured by accumulating the distinct `digest`s (content
  fingerprint already computed by PyMuPDF, `page.get_image_info(xrefs=True)`)
  over the grid pages strictly (2 to 16): convergence stabilises from page 5,
  with no new image on the following pages. A higher figure (531, or 41 when
  wrongly accumulating together with the images of the page 1 preview, whose
  catalogue is entirely disjoint: 21 distinct images, zero overlap with the
  20 of the grid pages) came from confusing the number of *placements* on a
  single page (531 is page 2's placement count, not a number of distinct
  images) with the number of genuinely distinct images. See
  `docs/specification.md` §4.3 and `fixtures/README.md`, corrected
  accordingly.
- These 20 images match **exactly** the 20 DMC colours of the legend
  (page 17) — one image per colour, never two variants per colour as one
  might have assumed before rendering and looking at them
  (`doc.extract_image` + Pillow): each image already combines a flat
  background fill (the thread colour) and a small symbol drawn on top in a
  contrasting colour (white on a dark background, black on a light one) —
  confirmed visually on a contact sheet of the 20 images.
- **Matching each image's background colour to the nearest DMC code (even
  restricted to the legend's 20 codes) is unreliable on this file: 12 of the
  20 images are misidentified by this signal alone** (Lab distances from 5 to
  over 20, and 8 of the 20 legend codes did not even exist in
  `app/dmc_catalog.py`, a necessarily partial community catalogue, §3.3).
  The colour actually rendered by this publisher visibly does not match
  exactly the official DMC shades approximated by that catalogue. **A far
  more reliable signal, verified exact on all 20 colours (no error): the
  total number of placements of each image in the grid pages matches exactly
  the number of stitches ("Stitches") declared by the legend for each DMC
  code** — a different value for each of this file's 20 colours (from 332 to
  2935), hence unambiguous here. This module therefore uses this count match
  as the *primary* image -> colour matching signal, perceptual colour
  (restricted to the legend codes, as specification §8.5 suggests) serving as
  an explicit fallback for images that could not be told apart this way
  (duplicate counts, or more images than legend rows) — always flagged as
  less reliable (cells marked uncertain).

Pure module: no FastAPI/SQLAlchemy dependency. The `detect_type_e` entry
point never raises — it returns `None` if the PDF does not look like a type E
export (including for a genuine type A/B/C, cf. non-regression tests)."""

from __future__ import annotations

import io
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf
from pdfplumber.page import Page
from PIL import Image

from app.dmc_catalog import nearest_dmc_among

# `app.schemas` only depends on Pydantic — importing it here does not break
# the module's purity (no FastAPI/SQLAlchemy dependency, see docstring).
from app.schemas import DetectionWarning
from app.type_a import SymbolGlyphLocation

Bbox = tuple[float, float, float, float]

# --------------------------------------------------------------------------
# Thresholds — all measured on the reference fixture, never guessed (see the
# module docstring for the details of the measurements).
# --------------------------------------------------------------------------

# Fraction of a page's image placements that must share the same size
# (width, height) for that page to be a "grid" candidate — measured: 1.0 on
# the grid pages (2-16), the legend (17) and the assembly map (18); only
# 0.698 on the preview page (1), which layers two image sizes (48x48 and
# 64x64) for a photorealistic rendering. A wide margin between the two
# observed regimes.
_MIN_DOMINANT_SIZE_FRACTION = 0.98
# Tolerated relative width/height deviation for a page's dominant size — a
# cross-stitch grid cell is always (nearly) square. Measured: 0.0 on the grid
# pages and the legend (exactly 64x64) versus ~0.296 on the assembly map
# (207x294 pt) — a wide margin between the two regimes.
_MAX_ASPECT_DEVIATION = 0.15
# Minimum total number of image placements (all candidate pages together)
# below which this is probably not a cross-stitch grid but an incidental
# reuse of a small number of images (a logo repeated in a header, for
# example) — measured: 27,984 placements on the reference fixture's grid
# pages, three orders of magnitude above.
_MIN_TOTAL_GRID_PLACEMENTS = 100
# Minimum number of distinct images to speak of a "catalogue" rather than a
# simple background texture repeated once. Measured: 20 on the reference
# fixture.
_MIN_DISTINCT_CATALOG_IMAGES = 2

# Left margin band (in PDF points) where the row axis numbers (row numbers,
# stacked vertically) are printed — measured at x0 ∈ {30.0, 32.6} on all grid
# pages of the reference fixture (the column header number closest to the
# left edge observed is at x0 = 67.8, well above): this band unambiguously
# separates "row number stacked in the left margin" from "column number
# aligned with the grid", without depending on the geometry of that
# particular page's images (unlike a window relative to the images' extent,
# which fails on a page carrying only a handful of painted cells — see the
# task report for the full diagnosis).
_LEFT_AXIS_BAND_MAX_X = 50.0
# A candidate axis text line consists only of digits and spaces
# ("10 20 30 40 50", or a single number "10") — legend text ("DMC 168 Pewter
# very light...") or a copyright line never matches.
_AXIS_LINE_RE = re.compile(r"^\d+(?:\s+\d+)*$")
# Dimensions stated plainly by the legend, e.g. "217x206 Stitches" (repeated
# once per fabric gauge offered — 10/14/16/18 ct — always with the same
# values, so the first occurrence is enough).
_DECLARED_DIMENSIONS_RE = re.compile(r"(\d+)x(\d+)\s+Stitches")
# Legend: "DMC <code>\n<name>\n<strands>\n<n>,<n> Skeins\n<stitches>" — an
# alphabetic code (e.g. BLANC) sometimes shares the same line as "DMC" with no
# line break in between (observed on this particular fixture:
# "DMC BLANC\nWhite\n..." while all the other rows have
# "DMC\n<code>\n...") — `\s+` rather than `\n` absorbs both forms.
_LEGEND_ROW_RE = re.compile(r"DMC\s+(\S+)\n(.+?)\n(\d+)\n[\d.,]+\s*Skeins\n(\d+)")

# Beyond this Lab distance, a colour-based fallback match (see the module
# docstring) is deemed too doubtful to be applied without further caveat —
# same scale as `app/type_bc.py` (`_UNCERTAIN_COLOR_DISTANCE`), the
# theoretical DMC colour being only a last resort here anyway, never the
# primary source of identity.
_UNCERTAIN_COLOR_DISTANCE = 12.0


@dataclass
class TypeEPaletteEntry:
    code: str
    """DMC code as printed in the legend — empty (`""`) for a catalogue image
    that could not be matched to a legend row ("Unrecognised symbol", never a
    silently wrong cell)."""

    name: str
    rgb_hex: str
    """Colour actually extracted from the catalogue image (dominant
    background pixel, see `_dominant_color`) — never the DMC catalogue's
    theoretical shade, which the module docstring shows does not faithfully
    match this publisher's real rendering (specification §8.4: the actually
    extracted colour is always authoritative for display)."""

    symbol_key: str
    symbol_glyph: SymbolGlyphLocation | None = None
    match_method: str = "unmatched"
    """"count" (exact count, reliable), "color" (perceptual fallback, flagged
    uncertain) or "unmatched" (no legend row available: "Unrecognised symbol"
    entry)."""


@dataclass
class TypeEResult:
    columns: int
    rows: int
    cells: list[int]
    """Length `columns * rows`, row by row, (0,0) at the top left first.
    0 = empty cell, n = 1-based index into `palette`."""
    palette: list[TypeEPaletteEntry]
    confidence: float
    uncertain_cells: list[int] = field(default_factory=list)
    """0-based indices into `cells` of the cells whose identification is
    uncertain (colour fallback rather than count, or unrecognised image) —
    never a wrong cell left unflagged."""
    warnings: list[DetectionWarning] = field(default_factory=list)
    """Never text already composed in French: a message code and its
    parameters, translated on the client (`import.warning.<code>`, Lot 8
    translation audit)."""


def detect_type_e(pdf_path: Path) -> TypeEResult | None:
    """Return `None` (never raising) if the PDF does not look like a type E
    export — see the module for the details of the detection."""
    try:
        with pdfplumber.open(pdf_path) as pdf, pymupdf.open(pdf_path) as doc:  # type: ignore[no-untyped-call]
            pages_pl = pdf.pages
            n_pages = min(len(pages_pl), doc.page_count)

            page_infos = [
                _analyze_page(pages_pl[i], doc[i]) for i in range(n_pages)
            ]
            candidates = [info for info in page_infos if _is_candidate_page(info)]
            if not candidates:
                return None

            fitted = [info for info in candidates if info.axis_fit is not None]
            if not fitted:
                return None

            catalog_size = _dominant_catalog_size(fitted)
            total_placements = sum(
                sum(1 for img in info.images if img.size == catalog_size) for info in fitted
            )
            if total_placements < _MIN_TOTAL_GRID_PLACEMENTS:
                return None

            warnings: list[DetectionWarning] = []
            confidence = 1.0

            skipped_pages = [info for info in candidates if info.axis_fit is None]
            if skipped_pages:
                warnings.append(
                    DetectionWarning(
                        code="type_e.pages_without_axis_numbers",
                        params={"count": len(skipped_pages)},
                    )
                )
                confidence -= min(0.3, 0.08 * len(skipped_pages))

            placements, digest_count, digest_sample, collisions = _place_images(
                fitted, catalog_size
            )
            if not placements:
                return None
            if collisions:
                warnings.append(
                    DetectionWarning(
                        code="type_e.overlapping_pages",
                        params={"count": collisions},
                    )
                )
                confidence -= min(0.2, 0.02 * collisions)

            if len(digest_count) < _MIN_DISTINCT_CATALOG_IMAGES:
                return None

            declared = _find_declared_dimensions(pages_pl)
            columns, rows, origin, dims_warning, dims_penalty = _resolve_dimensions(
                declared, placements
            )
            if dims_warning is not None:
                warnings.append(dims_warning)
                confidence -= dims_penalty
            if columns <= 0 or rows <= 0:
                return None

            legend_rows = _parse_legend(doc, n_pages)
            if not legend_rows:
                warnings.append(DetectionWarning(code="type_e.missing_legend"))
                confidence -= 0.5

            catalog = _build_catalog(doc, digest_sample, digest_count)
            palette, digest_to_index, match_warnings, match_penalty = _match_catalog_to_legend(
                catalog, legend_rows
            )
            warnings.extend(match_warnings)
            confidence -= match_penalty

            cells, uncertain_cells = _fill_cells(
                columns, rows, origin, placements, digest_to_index, palette
            )

            fraction_placed = sum(1 for v in cells if v != 0) / (columns * rows)
            if fraction_placed < 0.02:
                # Guard: a "grid" covering almost no cell is probably not a
                # usable real detection — better to refuse cleanly than to
                # offer an almost empty page as a starting point
                # (specification §10: never a dead end, but never a
                # misleading proposal either).
                return None

            confidence = max(0.0, min(1.0, confidence))
            return TypeEResult(
                columns=columns,
                rows=rows,
                cells=cells,
                palette=palette,
                confidence=confidence,
                uncertain_cells=uncertain_cells,
                warnings=warnings,
            )
    except Exception:  # pragma: no cover - safety net, see docstring
        return None


# --------------------------------------------------------------------------
# Per-page structural analysis: identify the candidate grid pages
# --------------------------------------------------------------------------


@dataclass
class _ImagePlacement:
    digest: bytes
    size: tuple[int, int]
    bbox: Bbox
    xref: int


@dataclass
class _AxisFit:
    a_col: float
    b_col: float
    a_row: float
    b_row: float


@dataclass
class _PageInfo:
    index: int
    """0-based, index PDF."""
    images: list[_ImagePlacement]
    axis_fit: _AxisFit | None


def _analyze_page(page_pl: Page, page_mu: Any) -> _PageInfo:
    infos = page_mu.get_image_info(xrefs=True)
    images = [
        _ImagePlacement(
            digest=info["digest"],
            size=(info["width"], info["height"]),
            bbox=(
                float(info["bbox"][0]),
                float(info["bbox"][1]),
                float(info["bbox"][2]),
                float(info["bbox"][3]),
            ),
            xref=int(info["xref"]),
        )
        for info in infos
    ]
    axis_fit = _fit_axes(page_pl) if images else None
    return _PageInfo(index=page_pl.page_number - 1, images=images, axis_fit=axis_fit)


def _is_candidate_page(info: _PageInfo) -> bool:
    """Structural signal alone (independent of axis numbers, see
    `_fit_axes`): a page where the overwhelming majority of image placements
    share the same (nearly) square size — see the constants at the top of
    the module for the measured values that justify the thresholds."""
    if not info.images:
        return False
    sizes = Counter(img.size for img in info.images)
    dominant_size, dominant_count = sizes.most_common(1)[0]
    fraction = dominant_count / len(info.images)
    if fraction < _MIN_DOMINANT_SIZE_FRACTION:
        return False
    width, height = dominant_size
    if height == 0:
        return False
    deviation = abs(width - height) / max(width, height)
    return deviation <= _MAX_ASPECT_DEVIATION


def _dominant_catalog_size(fitted: list[_PageInfo]) -> tuple[int, int]:
    """Dominant image size across all retained pages, weighted by the number
    of placements — used to ignore a possible isolated image of another size
    within an otherwise conforming page (defence in depth, not observed on
    the reference fixture but cheap to check)."""
    sizes: Counter[tuple[int, int]] = Counter()
    for info in fitted:
        for img in info.images:
            sizes[img.size] += 1
    return sizes.most_common(1)[0][0]


# --------------------------------------------------------------------------
# Axis numbers: absolute position of each page in the global mosaic
# --------------------------------------------------------------------------


def _cluster_header_numbers(line_chars: list[dict[str, Any]]) -> list[tuple[float, int]]:
    """A header line carries several horizontally spaced numbers
    ("10 20 30 40 50"): regroup them by large position gaps rather than
    relying on the spaces in the extracted text (unreliable from one
    exporter to another, cf. `app/type_a.py::_chain_clusters`)."""
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for ch in line_chars:
        if current and float(ch["x0"]) - float(current[-1]["x1"]) > 3.0:
            clusters.append(current)
            current = []
        current.append(ch)
    if current:
        clusters.append(current)
    points: list[tuple[float, int]] = []
    for cluster in clusters:
        text = "".join(str(c["text"]) for c in cluster)
        if text.isdigit():
            points.append((float(cluster[0]["x0"]), int(text)))
    return points


def _fit_axes(page: Page) -> _AxisFit | None:
    """`_AxisFit` such that the absolute (1-based) column number of a point
    at `x0` is `a_col + b_col*x0`, and likewise for the row via `top`. `None`
    if fewer than 2 usable axis numbers on either axis.

    Unlike `app/type_a.py::_fit_axes`, the search window for the numbers is
    **never** derived from the extent of that particular page's images: a
    page carrying only a handful of painted cells (measured: a single one on
    `RiverAndMountains-CS.pdf` page 6) has an image extent far too narrow to
    frame the full axis ruler, which is always printed in full whatever the
    page's content (same margin ruler on all grid pages of this file). The
    position in the margin alone is enough to tell a row number (stacked on
    the left, `x0 < _LEFT_AXIS_BAND_MAX_X`) from a column number (aligned
    with the grid, variable `x0`) — see the constant for the measured values
    that justify it."""
    col_points: list[tuple[float, int]] = []
    row_points: list[tuple[float, int]] = []
    for line in page.extract_text_lines():
        text = str(line["text"]).strip()
        if not _AXIS_LINE_RE.match(text):
            continue
        chars = line.get("chars") or []
        if not chars:
            continue
        numbers = text.split()
        x0 = float(chars[0]["x0"])
        top = float(line["top"])
        if len(numbers) >= 2:
            col_points.extend(_cluster_header_numbers(chars))
        elif x0 < _LEFT_AXIS_BAND_MAX_X:
            row_points.append((top, int(numbers[0])))
        else:
            col_points.append((x0, int(numbers[0])))

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
    return _AxisFit(a_col=a_col, b_col=b_col, a_row=a_row, b_row=b_row)


# --------------------------------------------------------------------------
# Placing images in the absolute grid
# --------------------------------------------------------------------------


def _place_images(
    fitted: list[_PageInfo], catalog_size: tuple[int, int]
) -> tuple[dict[tuple[int, int], bytes], Counter[bytes], dict[bytes, tuple[int, Bbox]], int]:
    """Place each image of size `catalog_size` at **non-normalised** absolute
    coordinates `(row1, col1)` (the origin is not guaranteed to be 0 — see
    `_resolve_dimensions`, which renormalises on the actually observed extent
    rather than assuming the axis numbering starts at 1 at the edge of the
    stitched pattern)."""
    placements: dict[tuple[int, int], bytes] = {}
    digest_count: Counter[bytes] = Counter()
    digest_sample: dict[bytes, tuple[int, Bbox]] = {}
    collisions = 0

    for info in fitted:
        assert info.axis_fit is not None
        fit = info.axis_fit
        for img in info.images:
            if img.size != catalog_size:
                continue
            cx, cy = img.bbox[0], img.bbox[1]
            col1 = round(fit.a_col + fit.b_col * cx)
            row1 = round(fit.a_row + fit.b_row * cy)
            digest_count[img.digest] += 1
            if img.digest not in digest_sample:
                digest_sample[img.digest] = (info.index + 1, img.bbox)
            key = (row1, col1)
            if key in placements and placements[key] != img.digest:
                collisions += 1
            placements[key] = img.digest

    return placements, digest_count, digest_sample, collisions


def _find_declared_dimensions(pages: list[Page]) -> tuple[int, int] | None:
    """Dimensions stated plainly by the legend (e.g. "217x206 Stitches") —
    preferred over the extent inferred from the placed images when
    available, as for type A (§7.2 step 6)."""
    for page in pages:
        match = _DECLARED_DIMENSIONS_RE.search(page.extract_text())
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None


def _resolve_dimensions(
    declared: tuple[int, int] | None,
    placements: dict[tuple[int, int], bytes],
) -> tuple[int, int, tuple[int, int], DetectionWarning | None, float]:
    """`(columns, rows, origin, warning, confidence_penalty)` — `origin` is
    the absolute `(row1, col1)` to subtract from each placement to get
    0-based coordinates.

    Unlike `app/type_a.py` (where column number 1 always matches the
    pattern's first cell), the axis numbers printed here do not necessarily
    start at 1 at the edge of the actually stitched pattern (a margin not
    numbered 1 observed on the reference fixture): the origin is therefore
    always aligned on the placement closest to the edge (`min`), never on the
    ruler's value 1 itself — measured: this makes the resulting extent match
    exactly the dimensions declared by the legend (217x206) on the reference
    fixture."""
    min_row1 = min(row1 for row1, _ in placements)
    min_col1 = min(col1 for _, col1 in placements)
    max_row1 = max(row1 for row1, _ in placements)
    max_col1 = max(col1 for _, col1 in placements)
    seen_columns = max_col1 - min_col1 + 1
    seen_rows = max_row1 - min_row1 + 1
    origin = (min_row1, min_col1)

    if declared is None:
        return (
            seen_columns,
            seen_rows,
            origin,
            DetectionWarning(code="type_e.dimensions_inferred"),
            0.05,
        )

    columns, rows = declared
    if columns != seen_columns or rows != seen_rows:
        warning = DetectionWarning(
            code="type_e.dimensions_mismatch",
            params={
                "declared_columns": columns,
                "declared_rows": rows,
                "seen_columns": seen_columns,
                "seen_rows": seen_rows,
            },
        )
        return columns, rows, origin, warning, 0.1
    return columns, rows, origin, None, 0.0


# --------------------------------------------------------------------------
# Text legend (exact DMC counts per colour)
# --------------------------------------------------------------------------


@dataclass
class _LegendRow:
    code: str
    name: str
    declared_count: int


def _parse_legend(doc: Any, n_pages: int) -> list[_LegendRow]:
    """Parsed from PyMuPDF's raw text (`page.get_text()`), not `pdfplumber`:
    each legend field is on its own line
    ("DMC\\n168\\nPewter very light\\n2\\n0,9 Skeins\\n1238\\n..."), faithfully
    rebuilt by PyMuPDF with no extra layout step. Returns the rows in printed
    order (authoritative for the exposed palette order — see
    `_match_catalog_to_legend`)."""
    for i in range(n_pages):
        text = doc[i].get_text()
        matches = _LEGEND_ROW_RE.findall(text)
        if not matches:
            continue
        return [
            _LegendRow(code=code, name=name.strip(), declared_count=int(count))
            for code, name, _strands, count in matches
        ]
    return []


# --------------------------------------------------------------------------
# Image catalogue: real dominant colour per image
# --------------------------------------------------------------------------


@dataclass
class _CatalogImage:
    digest: bytes
    count: int
    rgb: tuple[float, float, float]
    """0-1 components, the actually rendered dominant background colour."""
    page_number: int
    bbox: Bbox


def _dominant_color(png_or_jpeg_bytes: bytes) -> tuple[float, float, float]:
    """The image's most frequent pixel colour (statistical mode, not the
    mean): each catalogue icon's background is a flat fill (see the module
    docstring) and always covers the majority of pixels — the mean, on the
    other hand, is biased by the ink of the symbol drawn on top (measured:
    mean visibly closer to neutral grey than the real background on the
    reference fixture's dark/saturated icons, while the mode stays identical
    to the corner pixel, outside the symbol)."""
    with Image.open(io.BytesIO(png_or_jpeg_bytes)) as source:
        image = source.convert("RGB")
        # `maxcolors` is generous (well beyond the pixel count of a 64x64
        # icon): `getcolors` returns `None`, never a silently truncated list,
        # beyond this bound.
        raw_colors = image.getcolors(maxcolors=image.width * image.height)
    if not raw_colors:  # pragma: no cover - defensive, not observed on our fixtures
        return 0.0, 0.0, 0.0
    # PIL's stubs type `getcolors` very broadly (RGB, palette or greyscale
    # image); `image` is guaranteed RGB here (`.convert("RGB")` above) so
    # each pixel is indeed a triplet at runtime.
    _count, dominant_rgb = max(raw_colors, key=lambda item: item[0])
    r, g, b = (int(v) for v in dominant_rgb)  # type: ignore[attr-defined]
    return r / 255, g / 255, b / 255


def _build_catalog(
    doc: Any, digest_sample: dict[bytes, tuple[int, Bbox]], digest_count: Counter[bytes]
) -> list[_CatalogImage]:
    catalog: list[_CatalogImage] = []
    for digest, (page_number, bbox) in digest_sample.items():
        xref = _xref_for_bbox(doc, page_number, bbox)
        if xref is None:
            continue
        try:
            raw = doc.extract_image(xref)
            rgb = _dominant_color(raw["image"])
        except Exception:  # pragma: no cover - corrupt image, defensive path
            continue
        catalog.append(
            _CatalogImage(
                digest=digest,
                count=digest_count[digest],
                rgb=rgb,
                page_number=page_number,
                bbox=bbox,
            )
        )
    return catalog


def _xref_for_bbox(doc: Any, page_number: int, bbox: Bbox) -> int | None:
    page = doc[page_number - 1]
    for info in page.get_image_info(xrefs=True):
        if (
            abs(float(info["bbox"][0]) - bbox[0]) < 0.5
            and abs(float(info["bbox"][1]) - bbox[1]) < 0.5
        ):
            return int(info["xref"])
    return None


# --------------------------------------------------------------------------
# Catalogue -> legend matching (exact count, then colour fallback)
# --------------------------------------------------------------------------


def _symbol_key(index0: int) -> str:
    """Identical to `app/type_a.py::_symbol_key` — a small pure function
    deliberately duplicated rather than imported from another connector's
    private module, to keep this module self-contained (same convention as
    `app/type_bc.py::_symbol_key`)."""
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


def _match_catalog_to_legend(
    catalog: list[_CatalogImage], legend_rows: list[_LegendRow]
) -> tuple[list[TypeEPaletteEntry], dict[bytes, int], list[DetectionWarning], float]:
    """Associate each catalogue image with a legend row. Primary signal:
    exact count (see the module docstring — far more reliable here than
    colour). Fallback: perceptual colour nearest neighbour, restricted to the
    legend codes not yet assigned (specification §8.5), for images the count
    cannot tell apart unambiguously (duplicate counts, or more images than
    legend rows)."""
    warnings: list[DetectionWarning] = []
    penalty = 0.0

    count_to_codes: dict[int, list[str]] = defaultdict(list)
    for row in legend_rows:
        count_to_codes[row.declared_count].append(row.code)
    count_to_digests: dict[int, list[bytes]] = defaultdict(list)
    for img in catalog:
        count_to_digests[img.count].append(img.digest)

    matched_code: dict[bytes, str] = {}
    match_method: dict[bytes, str] = {}
    used_codes: set[str] = set()

    for count, codes in count_to_codes.items():
        digests = count_to_digests.get(count, [])
        if len(codes) == 1 and len(digests) == 1:
            matched_code[digests[0]] = codes[0]
            match_method[digests[0]] = "count"
            used_codes.add(codes[0])

    remaining_images = [img for img in catalog if img.digest not in matched_code]
    remaining_codes = {row.code for row in legend_rows if row.code not in used_codes}

    if remaining_images and remaining_codes:
        warnings.append(
            DetectionWarning(
                code="type_e.count_match_ambiguous",
                params={"count": len(remaining_images)},
            )
        )
        penalty += min(0.3, 0.05 * len(remaining_images))
        # Greedy pairing by increasing Lab distance, never an arbitrary
        # order — the most reliable pair is fixed first.
        pending_codes = set(remaining_codes)
        candidates: list[tuple[float, bytes, str]] = []
        for img in remaining_images:
            match = nearest_dmc_among(img.rgb, pending_codes)
            if match is not None:
                candidates.append((match.distance, img.digest, match.code))
        for _distance, digest, code in sorted(candidates, key=lambda c: c[0]):
            if digest in matched_code or code not in pending_codes:
                continue
            matched_code[digest] = code
            match_method[digest] = "color"
            pending_codes.discard(code)

    palette: list[TypeEPaletteEntry] = []
    digest_to_index: dict[bytes, int] = {}
    images_by_digest = {img.digest: img for img in catalog}

    for row in legend_rows:
        matched_digest = next((d for d, c in matched_code.items() if c == row.code), None)
        if matched_digest is None:
            continue
        img = images_by_digest[matched_digest]
        index = len(palette) + 1
        digest_to_index[matched_digest] = index
        palette.append(
            TypeEPaletteEntry(
                code=row.code,
                name=row.name,
                rgb_hex=_rgb_hex(img.rgb),
                symbol_key=_symbol_key(index - 1),
                symbol_glyph=SymbolGlyphLocation(page_number=img.page_number, bbox=img.bbox),
                match_method=match_method.get(matched_digest, "count"),
            )
        )

    unmatched = [img for img in catalog if img.digest not in digest_to_index]
    if unmatched:
        warnings.append(
            DetectionWarning(
                code="type_e.unmatched_catalog_images",
                params={"count": len(unmatched)},
            )
        )
        penalty += min(0.3, 0.05 * len(unmatched))
        for img in unmatched:
            index = len(palette) + 1
            digest_to_index[img.digest] = index
            palette.append(
                TypeEPaletteEntry(
                    code="",
                    name="Symbole non reconnu",
                    rgb_hex=_rgb_hex(img.rgb),
                    symbol_key=_symbol_key(index - 1),
                    symbol_glyph=SymbolGlyphLocation(page_number=img.page_number, bbox=img.bbox),
                    match_method="unmatched",
                )
            )

    return palette, digest_to_index, warnings, penalty


# --------------------------------------------------------------------------
# Assemblage final
# --------------------------------------------------------------------------


def _fill_cells(
    columns: int,
    rows: int,
    origin: tuple[int, int],
    placements: dict[tuple[int, int], bytes],
    digest_to_index: dict[bytes, int],
    palette: list[TypeEPaletteEntry],
) -> tuple[list[int], list[int]]:
    origin_row, origin_col = origin
    cells = [0] * (columns * rows)
    uncertain_positions: set[int] = set()
    uncertain_methods = {"color", "unmatched"}
    # 1-based index (like `cells`) -> matching method of the corresponding
    # palette entry, to mark uncertain cells without depending on a dict's
    # iteration order (never guaranteed stable here).
    index_to_method = {i + 1: entry.match_method for i, entry in enumerate(palette)}

    for (row1, col1), digest in placements.items():
        row0 = row1 - origin_row
        col0 = col1 - origin_col
        if row0 < 0 or col0 < 0 or row0 >= rows or col0 >= columns:
            continue
        index = digest_to_index.get(digest)
        if index is None:
            continue
        flat = row0 * columns + col0
        cells[flat] = index
        if index_to_method.get(index) in uncertain_methods:
            uncertain_positions.add(flat)

    return cells, sorted(uncertain_positions)
