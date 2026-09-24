/** Types of the "pattern" core. */

export interface PaletteEntry {
  /** Thread code in the chosen brand (e.g. "3346" for DMC). */
  code: string;
  name: string;
  /** Display colour, as hexadecimal `#rrggbb`. */
  hex: string;
  /** Symbol shown in the cell at high zoom — text fallback while
   * `symbolSvg` is unavailable or not loaded yet. */
  symbol: string;
  /** Real symbol cut out of the source PDF (Lot 4), a self-contained `<svg>`
   * ready to display — see `pattern/render.ts` for rendering and the image
   * cache. Absent for a palette entered by hand (Lot 2). */
  symbolSvg?: string;
}

/**
 * A backstitch stroke (Lot 8), in cell **corner** coordinates: (0, 0) is the
 * top-left corner of cell (0, 0), (1, 0) the top-right corner of that same
 * cell — never a pixel or a cell centre, same convention as
 * `backend/app/schemas.py::BackstitchSegment`. `paletteIndex` is 1-based,
 * like `Pattern.cells`.
 */
export interface BackstitchSegment {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
  readonly paletteIndex: number;
}

/**
 * A French knot (Lot 8), in cell **centre** coordinates: (0.5, 0.5) is the
 * centre of cell (0, 0) — never a corner (unlike `BackstitchSegment`) nor a
 * pixel. Same convention as `backend/app/schemas.py::FrenchKnot`.
 */
export interface FrenchKnot {
  readonly x: number;
  readonly y: number;
  readonly paletteIndex: number;
}

/** The five tracked stitch categories (Lot 8) — same enumeration as
 * `backend/app/schemas.py::ProgressOp.layer`, never an index space shared
 * between categories (a grid index for `full`/`half`/`quarter`, an index into
 * `Pattern.backstitch`/`frenchKnots` for `backstitch`/`knot`). */
export type StitchLayer = "full" | "half" | "quarter" | "backstitch" | "knot";

/**
 * A pattern grid.
 *
 * `cells` holds one palette index per cell (0 = empty cell), row by row. One
 * byte per cell: a 255 × 180 pattern fits in 45 KB, which allows keeping it
 * entirely in memory and redrawing only the visible portion.
 *
 * `cellsHalf`/`cellsQuarter` (Lot 8) follow exactly the same convention as
 * `cells`, same size — always present (never `undefined`), filled with zeros
 * when the pattern has no 1/2 or 1/4 stitch: rendering and tracking thus
 * never need a "missing layer" special case. A cell can carry a non-zero
 * value in several of these layers at once (§6.3: they are independent
 * layers, not mutually exclusive variants of the same cell).
 */
export interface Pattern {
  readonly id: string;
  readonly name: string;
  readonly width: number;
  readonly height: number;
  readonly cells: Uint8Array;
  readonly cellsHalf: Uint8Array;
  readonly cellsQuarter: Uint8Array;
  readonly backstitch: readonly BackstitchSegment[];
  readonly frenchKnots: readonly FrenchKnot[];
  readonly palette: readonly PaletteEntry[];
}

/**
 * Progress of the four special stitch categories (Lot 8), separate from
 * `Progress` (full stitch, below) — deliberately, so as not to change the
 * shape of `Progress` anywhere it is already consumed (statistics, library,
 * demo...): `Progress` still represents only the full stitch, the only one
 * counting towards the overall percentage (§7.1).
 *
 * `half`/`quarter` have the same size as `Pattern.cells` (one 0/1 byte per
 * cell, like `Progress`); `backstitch`/`knot` have the size of
 * `Pattern.backstitch`/`frenchKnots` (one 0/1 byte per element, never per
 * cell — these are not grids).
 */
export interface SpecialProgress {
  half: Uint8Array;
  quarter: Uint8Array;
  backstitch: Uint8Array;
  knot: Uint8Array;
}

export function emptySpecialProgress(pattern: Pattern): SpecialProgress {
  return {
    half: new Uint8Array(pattern.width * pattern.height),
    quarter: new Uint8Array(pattern.width * pattern.height),
    backstitch: new Uint8Array(pattern.backstitch.length),
    knot: new Uint8Array(pattern.frenchKnots.length),
  };
}

/**
 * Stitching progress.
 *
 * Stored **separately** from the grid (structural constraint of the
 * specification): a re-import of the source PDF replaces `Pattern`, never
 * `done`. Same indexing as `Pattern.cells`; 1 means "stitched cell".
 */
export type Progress = Uint8Array;

export function emptyProgress(pattern: Pattern): Progress {
  return new Uint8Array(pattern.width * pattern.height);
}

export function cellIndex(pattern: Pattern, x: number, y: number): number {
  return y * pattern.width + x;
}

export function isInside(pattern: Pattern, x: number, y: number): boolean {
  return x >= 0 && x < pattern.width && y >= 0 && y < pattern.height;
}
