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

import type {
  ApiBackstitchSegment,
  ApiFrenchKnot,
  ApiImportFillZone,
  ApiImportStitch,
  ApiImportStitchEdit,
} from "../lib/api";
import { applyFillsLocal, applyStitchEditsLocal, type DetectedLayers } from "../lib/importFills";
import { backstitchFromApi, frenchKnotFromApi } from "../lib/mappers";
import { nearestBackstitchIndex } from "../pattern/specialHitTest";
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

/** Backstitches and knots of the wizard (issue #82): the detected ones
 * (Lot 9) and the edits drawn by hand on top of them. */
export interface ImportStitchEdits {
  detectedBackstitch: readonly ApiBackstitchSegment[] | null;
  detectedKnots: readonly ApiFrenchKnot[] | null;
  edits: readonly ApiImportStitchEdit[];
  onChange: (edits: ApiImportStitchEdit[]) => void;
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
  /** Backstitch (issue #82): the corner a segment starts from, waiting for
   * the tap on its other end — `null` when none is pending. */
  pendingCorner: CellPosition | null;
  /** A tap on corner `(x, y)` with the backstitch tool: starts a segment, or
   * ends the pending one there (a second tap on the start cancels it). */
  tapCorner: (x: number, y: number, paletteIndex: number) => void;
  cancelPendingCorner: () => void;
  /** Places a knot on cell `(x, y)` or, with `paletteIndex = 0`, erases it. */
  tapKnot: (x: number, y: number, paletteIndex: number) => void;
  /** Erases the segment closest to `(gx, gy)` (corner coordinates), within
   * `maxDistance` cells — nothing if none is that close. */
  eraseBackstitchAt: (gx: number, gy: number, maxDistance: number) => void;
  /** Removes the last change, whatever it was (issue #37, #82): painted
   * areas and drawn stitches are each applied in order on top of what was
   * detected, so dropping the last one restores everything exactly as it was
   * before it, however many levels back. */
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
  stitchEdits: ImportStitchEdits,
): ImportPainter {
  const [cell, setCell] = useState(16);
  const [offset, setOffsetState] = useState({ x0: -2, y0: -2 });
  const [cursor, setCursor] = useState<CellPosition | null>(null);
  const [selection, setSelection] = useState<PainterSelection | null>(null);
  const [pendingCorner, setPendingCorner] = useState<CellPosition | null>(null);

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

  // Same palette guard as the server (`_special_stitches`): a stitch whose
  // colour has been removed from the palette since is dropped.
  const { detectedBackstitch, detectedKnots, edits, onChange: onEditsChange } = stitchEdits;
  const special = useMemo(() => {
    const valid = (item: { palette_index: number }): boolean =>
      item.palette_index >= 1 && item.palette_index <= palette.length;
    const applied = applyStitchEditsLocal(
      columns,
      rows,
      (detectedBackstitch ?? []).filter(valid),
      (detectedKnots ?? []).filter(valid),
      edits.filter((edit) => edit.palette_index <= palette.length),
    );
    return {
      backstitch: applied.backstitch.map(backstitchFromApi),
      frenchKnots: applied.frenchKnots.map(frenchKnotFromApi),
    };
  }, [columns, rows, detectedBackstitch, detectedKnots, edits, palette.length]);

  const pattern: Pattern = useMemo(
    () => ({
      id: "import-painter",
      name,
      width: columns,
      height: rows,
      cells: layers.full,
      // 1/2 and 1/4 stitches, detected and/or painted (issue #41).
      cellsHalf: layers.half,
      cellsQuarter: layers.quarter,
      // Detected and/or drawn by hand (issue #82).
      backstitch: special.backstitch,
      frenchKnots: special.frenchKnots,
      palette,
    }),
    [name, columns, rows, layers, special, palette],
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

  const addEdit = useCallback(
    (edit: ApiImportStitchEdit) => onEditsChange([...edits, edit]),
    [edits, onEditsChange],
  );

  const tapCorner = useCallback(
    (x: number, y: number, paletteIndex: number) => {
      if (x < 0 || y < 0 || x > columns || y > rows) return;
      if (pendingCorner === null) {
        setPendingCorner({ x, y });
        return;
      }
      setPendingCorner(null);
      if (pendingCorner.x === x && pendingCorner.y === y) return;
      addEdit({
        kind: "backstitch",
        op: "add",
        x1: pendingCorner.x,
        y1: pendingCorner.y,
        x2: x,
        y2: y,
        palette_index: paletteIndex,
        after_fills: fills.length,
      });
    },
    [columns, rows, pendingCorner, addEdit, fills.length],
  );

  const tapKnot = useCallback(
    (x: number, y: number, paletteIndex: number) => {
      if (x < 0 || y < 0 || x >= columns || y >= rows) return;
      const hasKnot = special.frenchKnots.some(
        (knot) => Math.floor(knot.x) === x && Math.floor(knot.y) === y,
      );
      // Erasing an empty cell is not a change worth an undo step.
      if (paletteIndex === 0 && !hasKnot) return;
      addEdit({
        kind: "knot",
        op: paletteIndex === 0 ? "remove" : "add",
        x,
        y,
        palette_index: paletteIndex,
        after_fills: fills.length,
      });
    },
    [columns, rows, special, addEdit, fills.length],
  );

  const eraseBackstitchAt = useCallback(
    (gx: number, gy: number, maxDistance: number) => {
      const index = nearestBackstitchIndex(special.backstitch, gx, gy, maxDistance);
      const segment = index === null ? undefined : special.backstitch[index];
      if (segment === undefined) return;
      addEdit({
        kind: "backstitch",
        op: "remove",
        x1: segment.x1,
        y1: segment.y1,
        x2: segment.x2,
        y2: segment.y2,
        palette_index: 0,
        after_fills: fills.length,
      });
    },
    [special, addEdit, fills.length],
  );

  const cancelPendingCorner = useCallback(() => setPendingCorner(null), []);

  const undo = useCallback(() => {
    setPendingCorner(null);
    // The last drawn stitch came after every painted area it counted: it
    // goes first. Otherwise the last painted area is the latest change.
    const lastEdit = edits[edits.length - 1];
    if (lastEdit !== undefined && lastEdit.after_fills >= fills.length) {
      onEditsChange(edits.slice(0, -1));
    } else if (fills.length > 0) {
      onFillsChange(fills.slice(0, -1));
    }
  }, [edits, fills, onEditsChange, onFillsChange]);

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
    pendingCorner,
    tapCorner,
    cancelPendingCorner,
    tapKnot,
    eraseBackstitchAt,
    undo,
    canUndo: fills.length > 0 || edits.length > 0,
  };
}
