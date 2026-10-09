"""`.cshp` export — documented open format (specification §6.4, Lot 2).

A self-contained ZIP archive, readable without this application: this is the
guarantee that the user is never locked into CrossStitchHelper (the lesson
cited from the Cross Stitch Markup format, §6.4). `grid.bin` and
`progress.bin` are the raw bytes already stored in the database (§6.1) — no
conversion, no loss.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from app.models import Grid, PaletteEntry, Pattern, Progress

FORMAT_VERSION = 2

_README = f"""CrossStitchHelper — .cshp archive (open format, version {FORMAT_VERSION})

This ZIP archive contains a whole cross-stitch pattern: its metadata, its
palette, its grid and your progress. It does not depend on any particular
software to be read back.

Files:

- pattern.json   Metadata, palette and segments (backstitch, knots), as
                  JSON. Also describes the format of the binary files below
                  (width, height, encoding), and which of those files are
                  present in this particular archive.

- grid.bin        The full-stitch grid, one cell per value: an unsigned
                  16-bit integer, little-endian, row by row from top to
                  bottom and left to right. 0 = empty cell; otherwise, the
                  integer is the (1-based) index of the colour in
                  `pattern.json` (palette[index - 1]).

- grid_half.bin, grid_quarter.bin (Lot 8, present only if this pattern has
                  1/2 or 1/4 stitches) — same format as grid.bin.

- progress.bin    Your progress on full stitches, one bit per cell, same
                  traversal order as grid.bin (least significant bit first in
                  each byte). 1 = stitched cell.

- progress_half.bin, progress_quarter.bin (Lot 8, present along with the
                  matching grid_*.bin files) — same format as progress.bin.

- progress_backstitch.bin, progress_knots.bin (Lot 8, present if this
                  pattern has backstitch segments / knots) — one bit per
                  element of `pattern.json` → `segments.backstitch` /
                  `segments.french_knots`, in the same order (never one bit
                  per cell: these are not grids).

To turn a grid*.bin file and pattern.json back into a readable matrix, almost
any language will do: read the integers as little-endian uint16,
`width * height` of them, and reshape them into `height` rows of `width`
values.
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
