/**
 * Assemble une grille à partir de zones peintes — miroir exact de
 * `backend/app/imports_engine.py::apply_fills`, pour que l'aperçu affiché
 * pendant la peinture soit toujours identique à ce que le serveur calculera.
 */

import type { ApiImportFillZone } from "./api";

/**
 * `base` (Lot 4) : grille détectée automatiquement, utilisée comme fond
 * plutôt qu'une case vide — miroir du paramètre `base` de `apply_fills`
 * côté serveur.
 */
export function applyFillsLocal(
  columns: number,
  rows: number,
  fills: readonly ApiImportFillZone[],
  base?: readonly number[] | null,
): Uint8Array {
  const cells = new Uint8Array(columns * rows);
  // Une grille détectée ne vaut que pour les dimensions avec lesquelles
  // elle a été calculée — si l'utilisateur les change (correction manuelle,
  // ou simplement pendant qu'il tape la nouvelle valeur d'un champ avant
  // l'autre), `base` ne correspond plus à `cells` : `Uint8Array.set` lève
  // une `RangeError` si la source dépasse la destination, ce qui plantait
  // toute l'appli (aucun composant ne peut rendre pendant qu'un hook lève).
  // Miroir de `_detected_base` côté serveur (`backend/app/api/imports.py`).
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
