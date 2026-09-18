/**
 * État de l'étape « palette + peinture par zone » de l'assistant d'import
 * (Lot 2, roadmap) : sélection rectangulaire puis remplissage, exactement le
 * même geste que « marquer toute cette couleur » côté suivi
 * (`state/useTracker.ts`), appliqué ici pour construire la grille au lieu de
 * cocher une progression.
 *
 * Volontairement un hook séparé plutôt qu'une généralisation de
 * `useTracker` : les deux écrans ont des besoins proches mais pas
 * identiques (pas d'annulation multi-niveaux ni d'outils multiples ici), et
 * `useTracker` est un code du Lot 1 déjà testé qu'il vaut mieux ne pas
 * risquer de déstabiliser pour un besoin voisin.
 */

import { useCallback, useMemo, useState } from "react";

import type { ApiImportFillZone } from "../lib/api";
import { applyFillsLocal } from "../lib/importFills";
import { MAX_CELL, MIN_CELL, panMargin, type GridView } from "../pattern/render";
import type { PaletteEntry, Pattern } from "../pattern/types";

export interface PainterSelection {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface CellPosition {
  x: number;
  y: number;
}

export interface ImportPainter {
  pattern: Pattern;
  filledCount: number;
  cellCount: number;

  view: GridView;
  setOffset: (x0: number, y0: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  /** Comme `useTracker.zoomTo` : zoome vers `nextCell` en gardant le point du
   * motif sous `(anchorScreenX, anchorScreenY)` ancré au même endroit — pour
   * la molette/le trackpad plutôt que des boutons +/- centrés. */
  zoomTo: (
    nextCell: number,
    anchorScreenX: number,
    anchorScreenY: number,
    canvasRect: Pick<DOMRect, "left" | "top">,
    /** Déplacement additionnel du même geste, en cases — voir
     * `useTracker.ts::Tracker.zoomTo` pour le détail. */
    panDeltaX?: number,
  ) => void;

  cursor: CellPosition | null;
  setCursor: (cursor: CellPosition | null) => void;

  selection: PainterSelection | null;
  setSelection: (selection: PainterSelection | null) => void;

  /** Peint (ou, avec `paletteIndex = 0`, efface) la sélection courante. */
  paint: (paletteIndex: number) => void;
}

export function useImportPainter(
  columns: number,
  rows: number,
  palette: readonly PaletteEntry[],
  fills: readonly ApiImportFillZone[],
  onFillsChange: (fills: ApiImportFillZone[]) => void,
  name: string,
  detectedCells?: readonly number[] | null,
): ImportPainter {
  const [cell, setCell] = useState(16);
  const [offset, setOffsetState] = useState({ x0: -2, y0: -2 });
  const [cursor, setCursor] = useState<CellPosition | null>(null);
  const [selection, setSelection] = useState<PainterSelection | null>(null);

  const cells = useMemo(
    () => applyFillsLocal(columns, rows, fills, detectedCells),
    [columns, rows, fills, detectedCells],
  );
  const filledCount = useMemo(() => cells.reduce((sum, value) => sum + (value !== 0 ? 1 : 0), 0), [
    cells,
  ]);

  const pattern: Pattern = useMemo(
    () => ({
      id: "import-painter",
      name,
      width: columns,
      height: rows,
      cells,
      // L'assistant d'import ne construit que le point entier — le point
      // arrière/nœuds/1-2/1-4 restent le périmètre du Lot 9, pas encore
      // construit (voir `lib/mappers.ts::patternFromImportPreview`).
      cellsHalf: new Uint8Array(columns * rows),
      cellsQuarter: new Uint8Array(columns * rows),
      backstitch: [],
      frenchKnots: [],
      palette,
    }),
    [name, columns, rows, cells, palette],
  );

  const setOffset = useCallback(
    (x0: number, y0: number) => {
      const marginX = panMargin(columns);
      const marginY = panMargin(rows);
      setOffsetState({
        x0: Math.max(-marginX, Math.min(columns - marginX, x0)),
        y0: Math.max(-marginY, Math.min(rows - marginY, y0)),
      });
    },
    [columns, rows],
  );

  const zoomIn = useCallback(
    () => setCell((value) => Math.min(MAX_CELL, Math.round(value * 1.45))),
    [],
  );
  const zoomOut = useCallback(
    () => setCell((value) => Math.max(MIN_CELL, Math.round(value / 1.45))),
    [],
  );

  const zoomTo = useCallback(
    (
      nextCell: number,
      anchorScreenX: number,
      anchorScreenY: number,
      canvasRect: Pick<DOMRect, "left" | "top">,
      panDeltaX = 0,
    ) => {
      const clampedCell = Math.max(MIN_CELL, Math.min(MAX_CELL, nextCell));
      const anchorCellX = offset.x0 + (anchorScreenX - canvasRect.left) / cell;
      const anchorCellY = offset.y0 + (anchorScreenY - canvasRect.top) / cell;
      setCell(clampedCell);
      // Ajoute le déplacement du même geste plutôt qu'un `setOffset` séparé,
      // qui se ferait écraser par ce calcul — voir useTracker.ts::zoomTo.
      setOffset(
        anchorCellX - (anchorScreenX - canvasRect.left) / clampedCell + panDeltaX,
        anchorCellY - (anchorScreenY - canvasRect.top) / clampedCell,
      );
    },
    [cell, offset, setOffset],
  );

  const paint = useCallback(
    (paletteIndex: number) => {
      if (selection === null) return;
      const zone: ApiImportFillZone = {
        x0: Math.max(0, Math.min(selection.x0, selection.x1)),
        y0: Math.max(0, Math.min(selection.y0, selection.y1)),
        x1: Math.min(columns - 1, Math.max(selection.x0, selection.x1)),
        y1: Math.min(rows - 1, Math.max(selection.y0, selection.y1)),
        palette_index: paletteIndex,
      };
      onFillsChange([...fills, zone]);
    },
    [selection, columns, rows, fills, onFillsChange],
  );

  const view: GridView = { cell, x0: offset.x0, y0: offset.y0 };

  return {
    pattern,
    filledCount,
    cellCount: columns * rows,
    view,
    setOffset,
    zoomIn,
    zoomOut,
    zoomTo,
    cursor,
    setCursor,
    selection,
    setSelection,
    paint,
  };
}
