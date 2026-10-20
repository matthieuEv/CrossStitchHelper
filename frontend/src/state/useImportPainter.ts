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

import type { ApiImportFillZone, ApiImportStitch } from "../lib/api";
import { applyFillsLocal, type DetectedLayers } from "../lib/importFills";
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

/** Zoom level `focusCell` brings the view to, at least: a cell large enough
 * to see its colour, symbol and marker at a glance. */
const FOCUS_MIN_CELL = 20;

export interface ImportPainter {
  pattern: Pattern;
  filledCount: number;
  cellCount: number;

  view: GridView;
  setOffset: (x0: number, y0: number) => void;
  /** Centres a cell in a canvas of `viewWidth` × `viewHeight` CSS pixels,
   * zooming in first if needed so the cell is clearly readable. */
  focusCell: (x: number, y: number, viewWidth: number, viewHeight: number) => void;
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

  /** Paints the current selection as `stitch` (issue #41) or, with
   * `paletteIndex = 0`, erases it — every layer, see `applyFillsLocal`. */
  paint: (paletteIndex: number, stitch: ApiImportStitch) => void;
  /** Removes the last painted area (issue #37) — painted areas are applied in
   * order on top of the detected grid, so dropping the last one restores the
   * grid exactly as it was before it, however many levels back. */
  undo: () => void;
  canUndo: boolean;
}

export function useImportPainter(
  columns: number,
  rows: number,
  palette: readonly PaletteEntry[],
  fills: readonly ApiImportFillZone[],
  onFillsChange: (fills: ApiImportFillZone[]) => void,
  name: string,
  detected: DetectedLayers,
): ImportPainter {
  const [cell, setCell] = useState(16);
  const [offset, setOffsetState] = useState({ x0: -2, y0: -2 });
  const [cursor, setCursor] = useState<CellPosition | null>(null);
  const [selection, setSelection] = useState<PainterSelection | null>(null);

  const { full: detectedFull, half: detectedHalf, quarter: detectedQuarter } = detected;
  const layers = useMemo(
    () =>
      applyFillsLocal(columns, rows, fills, {
        full: detectedFull,
        half: detectedHalf,
        quarter: detectedQuarter,
      }),
    [columns, rows, fills, detectedFull, detectedHalf, detectedQuarter],
  );
  const filledCount = useMemo(() => {
    let count = 0;
    for (let index = 0; index < layers.full.length; index++) {
      if (layers.full[index] !== 0 || layers.half[index] !== 0 || layers.quarter[index] !== 0) {
        count++;
      }
    }
    return count;
  }, [layers]);

  const pattern: Pattern = useMemo(
    () => ({
      id: "import-painter",
      name,
      width: columns,
      height: rows,
      cells: layers.full,
      // 1/2 and 1/4 stitches, detected and/or painted (issue #41).
      // Backstitch and knots are not painted in the wizard yet.
      cellsHalf: layers.half,
      cellsQuarter: layers.quarter,
      backstitch: [],
      frenchKnots: [],
      palette,
    }),
    [name, columns, rows, layers, palette],
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

  const focusCell = useCallback(
    (x: number, y: number, viewWidth: number, viewHeight: number) => {
      const nextCell = Math.min(MAX_CELL, Math.max(cell, FOCUS_MIN_CELL));
      setCell(nextCell);
      setOffset(x + 0.5 - viewWidth / (2 * nextCell), y + 0.5 - viewHeight / (2 * nextCell));
    },
    [cell, setOffset],
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
    (paletteIndex: number, stitch: ApiImportStitch) => {
      if (selection === null) return;
      const zone: ApiImportFillZone = {
        x0: Math.max(0, Math.min(selection.x0, selection.x1)),
        y0: Math.max(0, Math.min(selection.y0, selection.y1)),
        x1: Math.min(columns - 1, Math.max(selection.x0, selection.x1)),
        y1: Math.min(rows - 1, Math.max(selection.y0, selection.y1)),
        palette_index: paletteIndex,
        // Full stitches stay without the field, as before issue #41.
        ...(stitch !== "full" && { stitch }),
      };
      onFillsChange([...fills, zone]);
    },
    [selection, columns, rows, fills, onFillsChange],
  );

  const undo = useCallback(() => {
    if (fills.length > 0) onFillsChange(fills.slice(0, -1));
  }, [fills, onFillsChange]);

  const view: GridView = { cell, x0: offset.x0, y0: offset.y0 };

  return {
    pattern,
    filledCount,
    cellCount: columns * rows,
    view,
    setOffset,
    focusCell,
    zoomIn,
    zoomOut,
    zoomTo,
    cursor,
    setCursor,
    selection,
    setSelection,
    paint,
    undo,
    canUndo: fills.length > 0,
  };
}
