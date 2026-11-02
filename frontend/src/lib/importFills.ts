/**
 * Assemble a grid from painted areas — exact mirror of
 * `backend/app/imports_engine.py::apply_fills`, so the preview shown while
 * painting is always identical to what the server will compute.
 */

import type {
  ApiBackstitchSegment,
  ApiFrenchKnot,
  ApiImportFillZone,
  ApiImportStitchEdit,
} from "./api";
import type { Corner, PartialStitch } from "../pattern/types";

/** What an import paints — see `PaintedLayers` on the server: the full and
 * 1/2 stitch cell layers, and the 1/4 and 3/4 stitches as items with a
 * corner (issue #83), sorted by cell then corner. */
export interface PaintedLayers {
  full: Uint8Array;
  half: Uint8Array;
  quarter: PartialStitch[];
  threeQuarter: PartialStitch[];
}

/** Detected layers (Lots 4 and 9), used as the background rather than empty
 * cells — mirror of the server-side `base*` parameters of `apply_fills`. */
export interface DetectedLayers {
  full: readonly number[] | null;
  half: readonly number[] | null;
  quarter: readonly number[] | null;
}

const CORNERS: readonly Corner[] = ["tl", "tr", "bl", "br"];
const OPPOSITE: Record<Corner, Corner> = { tl: "br", tr: "bl", bl: "tr", br: "tl" };

/** A cell's 1/4 stitches (corner → palette index) and 3/4 stitch. */
interface PartialCell {
  quarters: Partial<Record<Corner, number>>;
  threeQuarter: { corner: Corner; paletteIndex: number } | null;
}

/**
 * Mirror of the server-side `_paint_partial`: the partial stitches of a
 * cell after painting a 1/4 or 3/4 stitch in `corner` (issue #83). What stays
 * is only what still fits beside it: a 3/4 stitch leaves its opposite corner
 * free, where a 1/4 stitch of another colour can sit — a split cell.
 */
function paintPartial(
  cell: PartialCell,
  stitch: "quarter" | "three_quarter",
  corner: Corner,
  paletteIndex: number,
): PartialCell {
  if (stitch === "quarter") {
    const keepThree =
      cell.threeQuarter !== null && OPPOSITE[cell.threeQuarter.corner] === corner;
    return {
      quarters: { ...cell.quarters, [corner]: paletteIndex },
      threeQuarter: keepThree ? cell.threeQuarter : null,
    };
  }
  const free = OPPOSITE[corner];
  const kept = cell.quarters[free];
  return {
    quarters: kept !== undefined ? { [free]: kept } : {},
    threeQuarter: { corner, paletteIndex },
  };
}

/**
 * A full or 1/2 stitch painted by hand is alone in its cell (issue #41):
 * painting one clears every other stitch of the cell, and the eraser (index
 * 0) clears them all. A 1/4 or 3/4 stitch (issue #83) goes in its corner
 * (top-left when absent) and keeps the partial stitches that still fit
 * beside it — see `paintPartial`.
 */
export function applyFillsLocal(
  columns: number,
  rows: number,
  fills: readonly ApiImportFillZone[],
  base: DetectedLayers = { full: null, half: null, quarter: null },
): PaintedLayers {
  const size = columns * rows;
  const layer = (detected: readonly number[] | null): Uint8Array => {
    const cells = new Uint8Array(size);
    // A detected layer is only valid for the dimensions it was computed with
    // — if the user changes them (manual correction, or simply while typing
    // one field's new value before the other), it no longer matches:
    // `Uint8Array.set` throws a `RangeError` if the source exceeds the
    // destination, which crashed the whole app (no component can render
    // while a hook throws). Mirror of the server-side `_detected_base`
    // (`backend/app/api/imports.py`).
    if (detected !== null && detected.length === size) cells.set(detected);
    return cells;
  };
  const full = layer(base.full);
  const half = layer(base.half);
  // Detected 1/4 stitches have no corner (Lot 9): top-left.
  const partials = new Map<number, PartialCell>();
  layer(base.quarter).forEach((paletteIndex, index) => {
    if (paletteIndex !== 0) partials.set(index, { quarters: { tl: paletteIndex }, threeQuarter: null });
  });
  for (const fill of fills) {
    const x0 = Math.max(0, Math.min(fill.x0, fill.x1));
    const x1 = Math.min(columns - 1, Math.max(fill.x0, fill.x1));
    const y0 = Math.max(0, Math.min(fill.y0, fill.y1));
    const y1 = Math.min(rows - 1, Math.max(fill.y0, fill.y1));
    const stitch = fill.stitch ?? "full";
    const corner = fill.corner ?? "tl";
    const value = fill.palette_index;
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const index = y * columns + x;
        full[index] = stitch === "full" ? value : 0;
        half[index] = stitch === "half" ? value : 0;
        if (value !== 0 && (stitch === "quarter" || stitch === "three_quarter")) {
          const cell = partials.get(index) ?? { quarters: {}, threeQuarter: null };
          partials.set(index, paintPartial(cell, stitch, corner, value));
        } else {
          partials.delete(index);
        }
      }
    }
  }
  const quarter: PartialStitch[] = [];
  const threeQuarter: PartialStitch[] = [];
  for (const index of [...partials.keys()].sort((a, b) => a - b)) {
    const cell = partials.get(index)!;
    const x = index % columns;
    const y = Math.floor(index / columns);
    for (const corner of CORNERS) {
      const paletteIndex = cell.quarters[corner];
      if (paletteIndex !== undefined) quarter.push({ x, y, corner, paletteIndex });
    }
    if (cell.threeQuarter !== null) threeQuarter.push({ x, y, ...cell.threeQuarter });
  }
  return { full, half, quarter, threeQuarter };
}

/**
 * Uncertain cells (`ApiImportConfig.uncertain_cells`) that no painted area
 * covers yet. Painting over a flagged cell — with any colour, the detected
 * one included, or the eraser — is a manual decision on that cell, so its
 * uncertainty is resolved: the marker and the count must drop it (issue
 * #46). Derived from `fills` rather than stored separately: `fills` is
 * already the persisted record of every manual correction.
 */
export function unresolvedUncertainCells(
  columns: number,
  rows: number,
  uncertain: readonly number[],
  fills: readonly ApiImportFillZone[],
): number[] {
  const covered = new Uint8Array(columns * rows);
  for (const fill of fills) {
    const x0 = Math.max(0, Math.min(fill.x0, fill.x1));
    const x1 = Math.min(columns - 1, Math.max(fill.x0, fill.x1));
    const y0 = Math.max(0, Math.min(fill.y0, fill.y1));
    const y1 = Math.min(rows - 1, Math.max(fill.y0, fill.y1));
    for (let y = y0; y <= y1; y++) {
      covered.fill(1, y * columns + x0, y * columns + x1 + 1);
    }
  }
  return uncertain.filter((index) => index >= 0 && index < covered.length && covered[index] === 0);
}

function samePoint(ax: number, ay: number, bx: number, by: number): boolean {
  return Math.abs(ax - bx) < 1e-6 && Math.abs(ay - by) < 1e-6;
}

/** Same two ends, in either direction. */
function sameSegment(
  segment: Pick<ApiBackstitchSegment, "x1" | "y1" | "x2" | "y2">,
  other: Pick<ApiBackstitchSegment, "x1" | "y1" | "x2" | "y2">,
): boolean {
  return (
    (samePoint(segment.x1, segment.y1, other.x1, other.y1) &&
      samePoint(segment.x2, segment.y2, other.x2, other.y2)) ||
    (samePoint(segment.x1, segment.y1, other.x2, other.y2) &&
      samePoint(segment.x2, segment.y2, other.x1, other.y1))
  );
}

/**
 * Backstitches and knots drawn or erased by hand (issue #82), applied in
 * order on top of the detected ones — exact mirror of
 * `backend/app/imports_engine.py::apply_stitch_edits`, so what the wizard
 * shows is what the created pattern will hold.
 */
export function applyStitchEditsLocal(
  columns: number,
  rows: number,
  backstitch: readonly ApiBackstitchSegment[],
  frenchKnots: readonly ApiFrenchKnot[],
  edits: readonly ApiImportStitchEdit[],
): { backstitch: ApiBackstitchSegment[]; frenchKnots: ApiFrenchKnot[] } {
  let segments = [...backstitch];
  let knots = [...frenchKnots];
  for (const edit of edits) {
    if (edit.kind === "knot") {
      knots = knots.filter(
        (knot) => !(Math.floor(knot.x) === edit.x && Math.floor(knot.y) === edit.y),
      );
      if (edit.op === "add" && edit.x < columns && edit.y < rows) {
        knots.push({
          x: edit.x + 0.5,
          y: edit.y + 0.5,
          palette_index: edit.palette_index,
        });
      }
    } else {
      segments = segments.filter((segment) => !sameSegment(segment, edit));
      const inside = (x: number, y: number): boolean =>
        x >= 0 && x <= columns && y >= 0 && y <= rows;
      if (
        edit.op === "add" &&
        inside(edit.x1, edit.y1) &&
        inside(edit.x2, edit.y2) &&
        !samePoint(edit.x1, edit.y1, edit.x2, edit.y2)
      ) {
        segments.push({
          x1: edit.x1,
          y1: edit.y1,
          x2: edit.x2,
          y2: edit.y2,
          palette_index: edit.palette_index,
        });
      }
    }
  }
  return { backstitch: segments, frenchKnots: knots };
}
