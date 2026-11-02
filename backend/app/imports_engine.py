"""Manual engine of the import wizard (Lot 2).

No automatic detection here — that is what distinguishes Lot 2 from Lots 4
to 7 (specification §8, roadmap). This module only: renders a page (PDF or
image) as a raster for the cropping preview, and assembles a grid from the
areas painted by hand by the user ("filling colours by area", roadmap
Lot 2).
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image

MAX_PREVIEW_DIMENSION = 2000
"""Reasonable bound for a preview: sharp enough to crop by hand, without
sending a full scanner-resolution image over a mobile connection."""


class UnsupportedFileError(ValueError):
    """The dropped file is neither a PDF nor a supported image."""


class PageOutOfRangeError(ValueError):
    """Requested page number outside the PDF's real pages.

    Carries `page_number`/`page_count` as typed attributes rather than an
    already formatted message — translated on the client (translation audit,
    Lot 8), see `app/schemas.py::ApiErrorDetail` and `app/api/imports.py`."""

    def __init__(self, page_number: int, page_count: int) -> None:
        self.page_number = page_number
        self.page_count = page_count
        super().__init__(f"Page {page_number} out of range (1..{page_count})")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_page_count(path: Path) -> int:
    # pymupdf is untyped (no py.typed): `int(...)` documents and checks the
    # real type at the boundary rather than returning `Any`.
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        return int(doc.page_count)


def render_pdf_page(
    path: Path, page_number: int, max_dimension: int = MAX_PREVIEW_DIMENSION
) -> bytes:
    """Render page `page_number` (1-based) of a PDF as a raster PNG."""
    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        if page_number < 1 or page_number > doc.page_count:
            raise PageOutOfRangeError(page_number, int(doc.page_count))
        page = doc[page_number - 1]
        # The zoom is computed so the largest page dimension does not exceed
        # `max_dimension`, without ever enlarging a small page.
        zoom = min(max_dimension / page.rect.width, max_dimension / page.rect.height, 3.0)
        matrix = pymupdf.Matrix(zoom, zoom)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return bytes(pixmap.tobytes("png"))


_SYMBOL_GLYPH_PADDING = 0.14
"""Margin around the glyph, as a fraction of its longest side — enough not
to clip the edge antialiasing, without shrinking the symbol too much within
its frame."""

_SYMBOL_GLYPH_TARGET_PX = 64
"""Resolution of the normalised square: sharp at a cell's display size (a
few dozen CSS pixels), without needlessly bloating every pattern of 34+
colours."""


def render_symbol_svg(
    path: Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
    target_px: int = _SYMBOL_GLYPH_TARGET_PX,
) -> str:
    """Cut the real symbol (`bbox`, `pdfplumber` coordinates) out of the
    rendered page and return it as a self-contained `<svg>` (with a
    base64-encoded image inside) ready to be stored and displayed as is.

    Cropping a raster of the already rendered page rather than interpreting
    the embedded font's tables (glyph -> vector outline): the latter approach
    is fragile from one PDF exporter to another (direct CID -> GID or via a
    table, Type3 vs TrueType/CFF font...), whereas rendering the page is
    already the proven mechanism of the cropping preview (`render_pdf_page`)
    — faithful by construction, whatever the PDF.

    Square re-centred on the glyph (not its raw `bbox`): glyph proportions
    vary from one symbol to another within the same file, while a grid cell
    is always square — a normalised square composes predictably whatever the
    original shape."""
    x0, top, x1, bottom = bbox
    width, height = x1 - x0, bottom - top
    side = max(width, height) * (1 + 2 * _SYMBOL_GLYPH_PADDING)
    cx, cy = (x0 + x1) / 2, (top + bottom) / 2
    clip = pymupdf.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)  # type: ignore[no-untyped-call]

    with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]
        if page_number < 1 or page_number > doc.page_count:
            raise ValueError(f"Page {page_number} out of range (1..{doc.page_count})")
        page = doc[page_number - 1]
        zoom = target_px / side if side > 0 else 1.0
        matrix = pymupdf.Matrix(zoom, zoom)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=True)
        png_b64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pixmap.width} {pixmap.height}">'
        f'<image width="{pixmap.width}" height="{pixmap.height}" '
        f'href="data:image/png;base64,{png_b64}"/></svg>'
    )


def render_image_page(path: Path, max_dimension: int = MAX_PREVIEW_DIMENSION) -> bytes:
    """Resize (if needed) a dropped photo and return it as PNG."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.width > max_dimension or image.height > max_dimension:
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


@dataclass(frozen=True)
class PaintedLayers:
    """The three cell layers an import paints (issue #41): full, 1/2 and 1/4
    stitches, same convention as the grid blob (0 = no stitch, n = 1-based
    palette index)."""

    full: list[int]
    half: list[int]
    quarter: list[int]


def _layer(base: list[int] | None, size: int) -> list[int]:
    if base is None:
        return [0] * size
    if len(base) != size:
        raise ValueError("a base layer must have exactly columns*rows cells")
    return list(base)


def apply_fills(
    columns: int,
    rows: int,
    fills: list[dict[str, Any]],
    base: list[int] | None = None,
    base_half: list[int] | None = None,
    base_quarter: list[int] | None = None,
) -> PaintedLayers:
    """Assemble a `columns` × `rows` grid from the painted areas.

    Each area is an inclusive rectangle of cell coordinates
    (``x0``, ``y0``, ``x1``, ``y1``) associated with ``palette_index``
    (1-based, 0 = empty cell). Areas are applied in the order received — the
    last one to touch a cell wins, exactly like `fillSelection` on the client
    (`frontend/src/state/useTracker.ts`), so the brush behaves identically
    during import and during tracking.

    ``stitch`` (issue #41, ``"full"`` when absent) picks the layer an area
    paints. A cell painted by hand holds one stitch type only: painting a
    colour clears the cell's other two layers, and the eraser (index 0)
    clears all three — so repainting an area as 1/2 stitches never leaves the
    full stitches underneath.

    `base`/`base_half`/`base_quarter` (Lots 4 and 9): the automatically
    detected layers serve as the background rather than empty cells — areas
    painted by the user remain *corrections* on top of the proposal.
    """
    size = columns * rows
    layers = {
        "full": _layer(base, size),
        "half": _layer(base_half, size),
        "quarter": _layer(base_quarter, size),
    }
    for fill in fills:
        x0 = max(0, min(fill["x0"], fill["x1"]))
        x1 = min(columns - 1, max(fill["x0"], fill["x1"]))
        y0 = max(0, min(fill["y0"], fill["y1"]))
        y1 = min(rows - 1, max(fill["y0"], fill["y1"]))
        palette_index = fill["palette_index"]
        stitch = fill.get("stitch") or "full"
        for name, cells in layers.items():
            value = palette_index if name == stitch else 0
            for y in range(y0, y1 + 1):
                row_offset = y * columns
                cells[row_offset + x0 : row_offset + x1 + 1] = [value] * (x1 - x0 + 1)
    return PaintedLayers(full=layers["full"], half=layers["half"], quarter=layers["quarter"])


def _same_point(ax: float, ay: float, bx: float, by: float) -> bool:
    return abs(ax - bx) < 1e-6 and abs(ay - by) < 1e-6


def _same_segment(segment: dict[str, Any], edit: dict[str, Any]) -> bool:
    """Same two ends, in either direction."""
    s1, s2 = (segment["x1"], segment["y1"]), (segment["x2"], segment["y2"])
    e1, e2 = (edit["x1"], edit["y1"]), (edit["x2"], edit["y2"])
    return (_same_point(*s1, *e1) and _same_point(*s2, *e2)) or (
        _same_point(*s1, *e2) and _same_point(*s2, *e1)
    )


def apply_stitch_edits(
    columns: int,
    rows: int,
    backstitch: list[dict[str, Any]],
    french_knots: list[dict[str, Any]],
    edits: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Backstitch segments and knots drawn or erased by hand in the import
    wizard (issue #82), applied in order on top of the detected ones — the
    counterpart of `apply_fills` for the two stitch kinds that are not cells.

    - A drawn segment replaces any segment with the same two ends (whatever
      their order), so drawing it again in another colour recolours it; an
      erased one removes every segment with those ends.
    - A knot belongs to a cell and is stored at its centre (`FrenchKnot`):
      placing one replaces the cell's knot, erasing removes it.
    - Drawn items outside the grid (dimensions changed since) are dropped, so
      the created pattern never references a cell that does not exist.

    Mirror: `frontend/src/lib/importFills.ts::applyStitchEditsLocal`.
    """
    segments = [dict(segment) for segment in backstitch]
    knots = [dict(knot) for knot in french_knots]
    for edit in edits:
        if edit.get("kind") == "knot":
            x, y = edit["x"], edit["y"]
            knots = [
                knot
                for knot in knots
                if not (int(knot["x"] // 1) == x and int(knot["y"] // 1) == y)
            ]
            if edit["op"] == "add" and x < columns and y < rows:
                knots.append({"x": x + 0.5, "y": y + 0.5, "palette_index": edit["palette_index"]})
        else:
            segments = [segment for segment in segments if not _same_segment(segment, edit)]
            inside = all(
                0 <= edit[x] <= columns and 0 <= edit[y] <= rows
                for x, y in (("x1", "y1"), ("x2", "y2"))
            )
            if (
                edit["op"] == "add"
                and inside
                and not _same_point(edit["x1"], edit["y1"], edit["x2"], edit["y2"])
            ):
                segments.append(
                    {
                        "x1": edit["x1"],
                        "y1": edit["y1"],
                        "x2": edit["x2"],
                        "y2": edit["y2"],
                        "palette_index": edit["palette_index"],
                    }
                )
    return segments, knots
