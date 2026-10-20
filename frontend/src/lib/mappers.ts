/** Conversion of API responses into the pattern core types (`pattern/types.ts`). */

import type {
  ApiGrid,
  ApiImportPaletteEntry,
  ApiImportPreview,
  ApiPartialStitch,
  ApiPatternDetail,
  ApiProgress,
} from "./api";
import { base64ToBytes, decodeUint16Layer, unpackBitmap } from "./codec";
import type {
  PaletteEntry,
  PartialStitch,
  Pattern,
  Progress,
  SpecialProgress,
} from "../pattern/types";

export function paletteFromApi(detail: ApiPatternDetail): PaletteEntry[] {
  return detail.palette.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
    ...(entry.symbol_svg !== null && { symbolSvg: entry.symbol_svg }),
  }));
}

function paletteFromImportEntries(entries: ApiImportPaletteEntry[]): PaletteEntry[] {
  return entries.map((entry) => ({
    code: entry.code,
    name: entry.name,
    hex: entry.rgb_hex,
    symbol: entry.symbol_key,
    ...(entry.symbol_svg !== null &&
      entry.symbol_svg !== undefined && { symbolSvg: entry.symbol_svg }),
  }));
}

/**
 * Builds a `Pattern` from the preview computed by the import wizard (Lot 2) —
 * same compact format as `patternFromApi`, so the area-painting screen and
 * the summary reuse the tracking canvas renderer as is (`pattern/render.ts`).
 */
export function patternFromImportPreview(preview: ApiImportPreview, name: string): Pattern {
  const layer = decodeUint16Layer(base64ToBytes(preview.layer_full));
  const cellCount = preview.width * preview.height;
  return {
    id: "import-preview",
    name,
    width: preview.width,
    height: preview.height,
    cells: Uint8Array.from(layer),
    // The import wizard (Lots 2, 4, 5) only produces full stitches —
    // backstitch/knots/1-2/1-4 remained Lot 9's scope, not built yet at the
    // time: layers always present but empty here, never `undefined` (see
    // `Pattern.cellsHalf`).
    cellsHalf: new Uint8Array(cellCount),
    quarterStitches: [],
    threeQuarterStitches: [],
    backstitch: [],
    frenchKnots: [],
    palette: paletteFromImportEntries(preview.palette),
  };
}

/**
 * Builds a `Pattern` from the metadata and the grid.
 *
 * `layer_full` is a `Uint16Array` on the server (§6.3, to accommodate future
 * palettes of more than 255 colours); canvas rendering works in `Uint8Array`
 * — narrowing is safe as long as a pattern stays under 256 colours, which
 * covers virtually every real cross-stitch pattern.
 */
export function patternFromApi(detail: ApiPatternDetail, grid: ApiGrid): Pattern {
  const layer = decodeUint16Layer(base64ToBytes(grid.layer_full));
  const cellCount = grid.width * grid.height;
  const half = grid.layer_half !== null ? decodeUint16Layer(base64ToBytes(grid.layer_half)) : null;
  return {
    id: detail.id,
    name: detail.name,
    labels: detail.labels,
    width: detail.width,
    height: detail.height,
    cells: Uint8Array.from(layer),
    // Always present (even empty) — see `Pattern.cellsHalf`: rendering and
    // tracking thus never have a "missing layer" special case.
    cellsHalf: half !== null ? Uint8Array.from(half) : new Uint8Array(cellCount),
    quarterStitches: grid.quarter_stitches.map(partialStitchFromApi),
    threeQuarterStitches: grid.three_quarter_stitches.map(partialStitchFromApi),
    backstitch: grid.backstitch.map((segment) => ({
      x1: segment.x1,
      y1: segment.y1,
      x2: segment.x2,
      y2: segment.y2,
      paletteIndex: segment.palette_index,
    })),
    frenchKnots: grid.french_knots.map((knot) => ({
      x: knot.x,
      y: knot.y,
      paletteIndex: knot.palette_index,
    })),
    palette: paletteFromApi(detail),
  };
}

function partialStitchFromApi(item: ApiPartialStitch): PartialStitch {
  return { x: item.x, y: item.y, corner: item.corner, paletteIndex: item.palette_index };
}

export function progressFromApi(progress: ApiProgress): Progress {
  return unpackBitmap(base64ToBytes(progress.bitmap), progress.cell_count);
}

/**
 * Builds the progress of the special stitch categories (Lot 8) from
 * `GET /grid` (sizes) and `GET /progress` (bitmaps) — separate from
 * `progressFromApi` (full stitch) so as not to change its shape, see
 * `SpecialProgress`.
 */
export function specialProgressFromApi(grid: ApiGrid, progress: ApiProgress): SpecialProgress {
  const cellCount = grid.width * grid.height;
  const backstitchCount = grid.backstitch.length;
  const knotCount = grid.french_knots.length;
  const elements = (bitmap: string | null, count: number): Uint8Array =>
    bitmap !== null ? unpackBitmap(base64ToBytes(bitmap), count) : new Uint8Array(count);
  return {
    half:
      progress.bitmap_half !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_half), cellCount)
        : new Uint8Array(cellCount),
    quarter: elements(progress.bitmap_quarter, grid.quarter_stitches.length),
    threeQuarter: elements(progress.bitmap_three_quarter, grid.three_quarter_stitches.length),
    backstitch:
      progress.bitmap_backstitch !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_backstitch), backstitchCount)
        : new Uint8Array(backstitchCount),
    knot:
      progress.bitmap_knots !== null
        ? unpackBitmap(base64ToBytes(progress.bitmap_knots), knotCount)
        : new Uint8Array(knotCount),
  };
}
