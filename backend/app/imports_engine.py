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
from pathlib import Path

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


def apply_fills(
    columns: int, rows: int, fills: list[dict[str, int]], base: list[int] | None = None
) -> list[int]:
    """Assemble a `columns` × `rows` grid from the painted areas.

    Each area is an inclusive rectangle of cell coordinates
    (``x0``, ``y0``, ``x1``, ``y1``) associated with ``palette_index``
    (1-based, 0 = empty cell). Areas are applied in the order received — the
    last one to touch a cell wins, exactly like `fillSelection` on the client
    (`frontend/src/state/useTracker.ts`), so the brush behaves identically
    during import and during tracking.

    `base` (Lot 4): an automatically detected grid (`app/type_a.py`) serves
    as the background rather than an empty cell — areas painted by the user
    remain *corrections* on top of the proposal, with no new painting
    mechanism to write on the client.
    """
    if base is not None:
        if len(base) != columns * rows:
            raise ValueError("`base` must have exactly columns*rows cells")
        cells = list(base)
    else:
        cells = [0] * (columns * rows)
    for fill in fills:
        x0 = max(0, min(fill["x0"], fill["x1"]))
        x1 = min(columns - 1, max(fill["x0"], fill["x1"]))
        y0 = max(0, min(fill["y0"], fill["y1"]))
        y1 = min(rows - 1, max(fill["y0"], fill["y1"]))
        palette_index = fill["palette_index"]
        for y in range(y0, y1 + 1):
            row_offset = y * columns
            for x in range(x0, x1 + 1):
                cells[row_offset + x] = palette_index
    return cells
