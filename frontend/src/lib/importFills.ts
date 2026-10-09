/**
 * Assemble a grid from painted areas — exact mirror of
 * `backend/app/imports_engine.py::apply_fills`, so the preview shown while
 * painting is always identical to what the server will compute.
 */

import type { ApiImportFillZone } from "./api";

/**
 * `base` (Lot 4): automatically detected grid, used as the background rather
 * than an empty cell — mirror of the server-side `base` parameter of
 * `apply_fills`.
 */
export function applyFillsLocal(
  columns: number,
  rows: number,
  fills: readonly ApiImportFillZone[],
  base?: readonly number[] | null,
): Uint8Array {
  const cells = new Uint8Array(columns * rows);
  // A detected grid is only valid for the dimensions it was computed with —
  // if the user changes them (manual correction, or simply while typing one
  // field's new value before the other), `base` no longer matches `cells`:
  // `Uint8Array.set` throws a `RangeError` if the source exceeds the
  // destination, which crashed the whole app (no component can render while
  // a hook throws). Mirror of the server-side `_detected_base`
  // (`backend/app/api/imports.py`).
  if (base !== null && base !== undefined && base.length === cells.length) cells.set(base);
  for (const fill of fills) {
    const x0 = Math.max(0, Math.min(fill.x0, fill.x1));
    const x1 = Math.min(columns - 1, Math.max(fill.x0, fill.x1));
    const y0 = Math.max(0, Math.min(fill.y0, fill.y1));
    const y1 = Math.min(rows - 1, Math.max(fill.y0, fill.y1));
    for (let y = y0; y <= y1; y++) {
      const rowOffset = y * columns;
      for (let x = x0; x <= x1; x++) {
        cells[rowOffset + x] = fill.palette_index;
      }
    }
  }
  return cells;
}
