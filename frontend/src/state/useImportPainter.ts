/**
 * State of the import wizard's "palette + area painting" step (Lot 2,
 * roadmap): rectangular selection then fill, exactly the same gesture as
 * "mark all of this colour" in tracking (`state/useTracker.ts`), applied here
 * to build the grid instead of checking progress.
 *
 * Deliberately a separate hook rather than a generalisation of `useTracker`:
 * the two screens have close but not identical needs (no multi-level undo or
 * multiple tools here), and `useTracker` is already-tested Lot 1 code that is
 * better not destabilised for a neighbouring need.
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
  /** Like `useTracker.zoomTo`: zooms to `nextCell` keeping the pattern point
   * under `(anchorScreenX, anchorScreenY)` anchored at the same place — for
   * the wheel/trackpad rather than centred +/- buttons. */
  zoomTo: (
    nextCell: number,
    anchorScreenX: number,
    anchorScreenY: number,
    canvasRect: Pick<DOMRect, "left" | "top">,
    /** Additional pan from the same gesture, in cells — see
     * `useTracker.ts::Tracker.zoomTo` for the details. */
    panDeltaX?: number,
  ) => void;

  cursor: CellPosition | null;
  setCursor: (cursor: CellPosition | null) => void;

  selection: PainterSelection | null;
  setSelection: (selection: PainterSelection | null) => void;

  /** Paints (or, with `paletteIndex = 0`, erases) the current selection. */
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
      // The import wizard only builds full stitches — backstitch/knots/1-2/1-4
      // remained Lot 9's scope, not built yet at the time (see
      // `lib/mappers.ts::patternFromImportPreview`).
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
      // Add the pan from the same gesture rather than a separate `setOffset`,
      // which would be overwritten by this computation — see
      // useTracker.ts::zoomTo.
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
