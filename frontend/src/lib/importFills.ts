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

/** The three cell layers an import paints — see `PaintedLayers` on the server. */
export interface PaintedLayers {
  full: Uint8Array;
  half: Uint8Array;
  quarter: Uint8Array;
}

/** Detected layers (Lots 4 and 9), used as the background rather than empty
 * cells — mirror of the server-side `base*` parameters of `apply_fills`. */
export interface DetectedLayers {
  full: readonly number[] | null;
  half: readonly number[] | null;
  quarter: readonly number[] | null;
}

/**
 * A cell painted by hand holds one stitch type only (issue #41): painting a
 * colour clears the cell's other two layers, and the eraser (index 0) clears
 * all three.
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
  const layers: PaintedLayers = {
    full: layer(base.full),
    half: layer(base.half),
    quarter: layer(base.quarter),
  };
  for (const fill of fills) {
    const x0 = Math.max(0, Math.min(fill.x0, fill.x1));
    const x1 = Math.min(columns - 1, Math.max(fill.x0, fill.x1));
    const y0 = Math.max(0, Math.min(fill.y0, fill.y1));
    const y1 = Math.min(rows - 1, Math.max(fill.y0, fill.y1));
    const stitch = fill.stitch ?? "full";
    for (const name of ["full", "half", "quarter"] as const) {
      const value = name === stitch ? fill.palette_index : 0;
      const cells = layers[name];
      for (let y = y0; y <= y1; y++) {
        cells.fill(value, y * columns + x0, y * columns + x1 + 1);
      }
    }
  }
  return layers;
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
