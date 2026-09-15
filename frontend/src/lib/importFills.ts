/**
 * Assemble une grille à partir de zones peintes — miroir exact de
 * `backend/app/imports_engine.py::apply_fills`, pour que l'aperçu affiché
 * pendant la peinture soit toujours identique à ce que le serveur calculera.
 */

import type { ApiImportFillZone } from "./api";

export function applyFillsLocal(
  columns: number,
  rows: number,
  fills: readonly ApiImportFillZone[],
): Uint8Array {
  const cells = new Uint8Array(columns * rows);
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
