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

/** A cell's corner: top-left, top-right, bottom-left, bottom-right. */
export type Corner = "tl" | "tr" | "bl" | "br";

/**
 * A 1/4 or 3/4 stitch (issue #83): the cell `(x, y)` and a corner. A 1/4
 * stitch goes from that corner to the cell's centre; a 3/4 stitch is that
 * same short leg plus the long diagonal that does not pass through the
 * corner. A cell may hold several. Same convention as
 * `backend/app/schemas.py::PartialStitch`.
 */
export interface PartialStitch {
  readonly x: number;
  readonly y: number;
  readonly corner: Corner;
  readonly paletteIndex: number;
}

/** The tracked stitch categories (Lot 8, 3/4 since issue #83) — same
 * enumeration as `backend/app/schemas.py::ProgressOp.layer`, never an index
 * space shared between categories (a grid index for `full`/`half`, an index
 * into `Pattern.quarterStitches`/`threeQuarterStitches`/`backstitch`/
 * `frenchKnots` for the others). */
export type StitchLayer = "full" | "half" | "quarter" | "three_quarter" | "backstitch" | "knot";

/**
 * A pattern grid.
 *
 * `cells` holds one palette index per cell (0 = empty cell), row by row. One
 * byte per cell: a 255 × 180 pattern fits in 45 KB, which allows keeping it
 * entirely in memory and redrawing only the visible portion.
 *
 * `cellsHalf` (Lot 8) follows exactly the same convention as `cells`, same
 * size — always present (never `undefined`), filled with zeros when the
 * pattern has no 1/2 stitch: rendering and tracking thus never need a
 * "missing layer" special case. A cell can carry a non-zero value in both at
 * once (§6.3: they are independent layers, not mutually exclusive variants
 * of the same cell). 1/4 and 3/4 stitches are lists rather than layers
 * (issue #83): one cell may hold several, each in its own corner.
 */
export interface Pattern {
  readonly id: string;
  readonly name: string;
  /** Labels the user sorts the library with (issue #57) — absent for a
   * built-in demo pattern, which has none. */
  readonly labels?: readonly string[];
  readonly width: number;
  readonly height: number;
  readonly cells: Uint8Array;
  readonly cellsHalf: Uint8Array;
  readonly quarterStitches: readonly PartialStitch[];
  readonly threeQuarterStitches: readonly PartialStitch[];
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
 * `half` has the same size as `Pattern.cells` (one 0/1 byte per cell, like
 * `Progress`); the others have the size of `Pattern.quarterStitches`/
 * `threeQuarterStitches`/`backstitch`/`frenchKnots` (one 0/1 byte per
 * element, never per cell — these are not grids).
 */
export interface SpecialProgress {
  half: Uint8Array;
  quarter: Uint8Array;
  threeQuarter: Uint8Array;
  backstitch: Uint8Array;
  knot: Uint8Array;
}

export function emptySpecialProgress(pattern: Pattern): SpecialProgress {
  return {
    half: new Uint8Array(pattern.width * pattern.height),
    quarter: new Uint8Array(pattern.quarterStitches.length),
    threeQuarter: new Uint8Array(pattern.threeQuarterStitches.length),
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
