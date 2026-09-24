/**
 * Tracking screen state: progress, view, current tool.
 *
 * Performance choice: each stitch category (`full`/`half`/`quarter`/
 * `backstitch`/`knot`, Lot 8) is a `Uint8Array` mutated in place, grouped in
 * a single structure (`doneRef.current`) rather than five separate refs — a
 * single object to pass through the undo history and `applyRemote`. A version
 * counter triggers the React render; copying an array on every checked cell
 * would cost a 45 KB allocation per tap on the reference pattern — invisible
 * on a computer, noticeable on an iPhone.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { countByColor, summarise, type ColorCount, type PatternTotals } from "../pattern/counts";
import { MAX_CELL, MIN_CELL, SYMBOL_MIN_CELL, panMargin, type GridView } from "../pattern/render";
import { nearestBackstitchIndex, nearestKnotIndex } from "../pattern/specialHitTest";
import {
  emptySpecialProgress,
  type Pattern,
  type Progress,
  type SpecialProgress,
  type StitchLayer,
} from "../pattern/types";

export type Tool = "stitch" | "pan" | "select";

export interface Selection {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface CellPosition {
  x: number;
  y: number;
}

/** A touch point in fractional grid coordinates (not yet rounded to a cell)
 * — needed to target a backstitch segment or a knot, which are not aligned
 * on the cell grid. */
export interface GridPoint {
  gx: number;
  gy: number;
}

/** Profondeur de la pile d'annulation. */
const HISTORY_LIMIT = 16;

/**
 * Tap tolerance for backstitches/knots, in screen pixels — converted to
 * cells at tap time (see `toggleAtPoint`) so it stays visually constant
 * whatever the zoom, capped at half a cell so it never catches a visibly
 * distant element.
 */
const SPECIAL_TAP_TOLERANCE_PX = 16;
const SPECIAL_TAP_TOLERANCE_MAX_CELLS = 0.5;

interface TrackerState {
  full: Progress;
  half: Uint8Array;
  quarter: Uint8Array;
  backstitch: Uint8Array;
  knot: Uint8Array;
}

function layerArray(state: TrackerState, layer: StitchLayer): Uint8Array {
  switch (layer) {
    case "full":
      return state.full;
    case "half":
      return state.half;
    case "quarter":
      return state.quarter;
    case "backstitch":
      return state.backstitch;
    case "knot":
      return state.knot;
  }
}

export interface Tracker {
  pattern: Pattern;
  done: Progress;
  /** Progress of the four special stitch categories (Lot 8) — see
   * `SpecialProgress`. Always in step with `version`: incremented by the same
   * update as `done`. */
  special: SpecialProgress;
  /**
   * Incremented on every change to `done` or `special`.
   *
   * Since `done`/`special` are mutated in place, it is this value — not the
   * arrays — that must appear in a rendering `useEffect`'s dependencies.
   */
  version: number;
  counts: ColorCount[];
  totals: PatternTotals;

  view: GridView;
  setOffset: (x0: number, y0: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  /**
   * Zooms to a target cell size while keeping a screen point anchored on the
   * same pattern cell (see the implementation for the details of the
   * computation). Used by two-finger pinch: the gesture's midpoint must stay
   * under the fingers, not jump to the corner of the screen.
   */
  zoomTo: (
    nextCell: number,
    anchorScreenX: number,
    anchorScreenY: number,
    canvasRect: Pick<DOMRect, "left" | "top">,
    /** Additional pan to apply in the same gesture, in pattern cells — a
     * diagonal trackpad swipe zooms and pans the view at the same time (see
     * TrackScreen.tsx): without this, the separate `setOffset` call for the
     * pan would immediately be overwritten by the one inside `zoomTo`, which
     * recomputes the origin from the position before the gesture. */
    panDeltaX?: number,
  ) => void;

  tool: Tool;
  setTool: (tool: Tool) => void;

  /** Stitch category targeted by the "check" tool (Lot 8) — no effect on the
   * "move"/"select" tools. `backstitch`/`knot` are only interactive from
   * `SYMBOL_MIN_CELL` (see `toggleAtPoint`), the same threshold at which
   * symbols appear: below it, a cell is a few pixels and two neighbouring
   * elements would be impossible to tell apart with a finger. */
  activeLayer: StitchLayer;
  setActiveLayer: (layer: StitchLayer) => void;

  /** Index de palette 1-based mis en avant ; 0 = aucun filtre. */
  highlight: number;
  toggleHighlight: (index: number) => void;
  clearHighlight: () => void;

  /** Hides already stitched cells rather than washing them out. */
  hideDone: boolean;
  toggleHideDone: () => void;

  cursor: CellPosition | null;
  setCursor: (cursor: CellPosition | null) => void;

  selection: Selection | null;
  setSelection: (selection: Selection | null) => void;

  /** Checks/unchecks a grid cell as a full stitch — independent of
   * `activeLayer`, kept for callers that explicitly target the full stitch
   * (see `fillSelection`, unchanged since Lot 1). */
  toggleCell: (cell: CellPosition) => void;
  /**
   * Checks/unchecks the element targeted by a touch point, depending on
   * `activeLayer`: a cell for `full`/`half`/`quarter` (rounded down), the
   * nearest backstitch segment or knot for `backstitch`/`knot` (no effect if
   * nothing is close enough, or below the interaction zoom threshold).
   */
  toggleAtPoint: (point: GridPoint) => void;
  fillSelection: (value: 0 | 1) => void;
  undo: () => void;
  canUndo: boolean;

  /**
   * Applies changes coming from elsewhere (server sync, Lot 1): updates
   * `done`/`special` and triggers a render, but without going through
   * `onChange` again (these are not new local intentions to resync) nor the
   * undo stack (undo must only revert this device's own gestures).
   */
  applyRemote: (changes: CellChange[]) => void;
}

export interface CellChange {
  layer: StitchLayer;
  index: number;
  stitched: 0 | 1;
}

/**
 * `onChange` is called synchronously with the elements actually changed
 * (never a whole array): that is what lets a caller (server sync, Lot 1) send
 * precise deltas without having to compare two 45 KB copies on every checked
 * cell.
 */
export function useTracker(
  pattern: Pattern,
  initialProgress: Progress,
  initialSpecial: SpecialProgress = emptySpecialProgress(pattern),
  onChange?: (changes: CellChange[]) => void,
): Tracker {
  const doneRef = useRef<TrackerState>({
    full: initialProgress,
    half: initialSpecial.half,
    quarter: initialSpecial.quarter,
    backstitch: initialSpecial.backstitch,
    knot: initialSpecial.knot,
  });
  const historyRef = useRef<TrackerState[]>([]);
  const [version, setVersion] = useState(0);

  // A ref rather than a direct dependency: `onChange` can change identity on
  // every render on the caller's side without invalidating the memoised
  // callbacks below.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const [cell, setCell] = useState(16);
  // Starting position designed for a large pattern (move away from the
  // corner so the view does not stick to the edge); without the same clamping
  // as `setOffset` below, a small pattern painted by hand (Lot 2) would open
  // on an entirely empty view, outside its grid.
  const [offset, setOffsetState] = useState(() => ({
    x0: Math.max(-panMargin(pattern.width), Math.min(pattern.width - panMargin(pattern.width), 30)),
    y0: Math.max(-panMargin(pattern.height), Math.min(pattern.height - panMargin(pattern.height), 24)),
  }));
  const [tool, setTool] = useState<Tool>("stitch");
  const [activeLayer, setActiveLayer] = useState<StitchLayer>("full");
  const [highlight, setHighlight] = useState(0);
  const [hideDone, setHideDone] = useState(false);
  const [cursor, setCursor] = useState<CellPosition | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const state = doneRef.current;
  const done = state.full;

  const counts = useMemo(
    () => countByColor(pattern, done),
    // `version` is the real dependency: `done` is mutated in place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pattern, version],
  );
  const totals = useMemo(() => summarise(counts), [counts]);

  const snapshot = useCallback(() => {
    const current = doneRef.current;
    historyRef.current.push({
      full: current.full.slice(),
      half: current.half.slice(),
      quarter: current.quarter.slice(),
      backstitch: current.backstitch.slice(),
      knot: current.knot.slice(),
    });
    if (historyRef.current.length > HISTORY_LIMIT) historyRef.current.shift();
  }, []);

  const toggleCell = useCallback(
    (position: CellPosition) => {
      if (
        position.x < 0 ||
        position.x >= pattern.width ||
        position.y < 0 ||
        position.y >= pattern.height
      ) {
        return;
      }
      const index = position.y * pattern.width + position.x;
      // An empty pattern cell cannot be stitched: checking it would make no
      // sense and would skew the counters.
      if ((pattern.cells[index] ?? 0) === 0) return;

      snapshot();
      const current = doneRef.current;
      const next = current.full[index] === 1 ? 0 : 1;
      current.full[index] = next;
      setVersion((value) => value + 1);
      onChangeRef.current?.([{ layer: "full", index, stitched: next }]);
    },
    [pattern, snapshot],
  );

  /** Like `toggleCell`, for the 1/2 and 1/4 layers — a cell with no stitch in
   * that category (see `Pattern.cellsHalf`/`cellsQuarter`) is ignored. */
  const toggleGridLayer = useCallback(
    (layer: "half" | "quarter", position: CellPosition) => {
      if (
        position.x < 0 ||
        position.x >= pattern.width ||
        position.y < 0 ||
        position.y >= pattern.height
      ) {
        return;
      }
      const index = position.y * pattern.width + position.x;
      const sourceCells = layer === "half" ? pattern.cellsHalf : pattern.cellsQuarter;
      if ((sourceCells[index] ?? 0) === 0) return;

      snapshot();
      const current = doneRef.current;
      const target = layer === "half" ? current.half : current.quarter;
      const next = target[index] === 1 ? 0 : 1;
      target[index] = next;
      setVersion((value) => value + 1);
      onChangeRef.current?.([{ layer, index, stitched: next }]);
    },
    [pattern, snapshot],
  );

  /** Checks/unchecks a backstitch segment or a knot, by index into
   * `Pattern.backstitch`/`frenchKnots` — never a grid index. */
  const toggleElementLayer = useCallback(
    (layer: "backstitch" | "knot", index: number) => {
      const current = doneRef.current;
      const target = layer === "backstitch" ? current.backstitch : current.knot;
      if (index < 0 || index >= target.length) return;

      snapshot();
      const next = target[index] === 1 ? 0 : 1;
      target[index] = next;
      setVersion((value) => value + 1);
      onChangeRef.current?.([{ layer, index, stitched: next }]);
    },
    [snapshot],
  );

  const toggleAtPoint = useCallback(
    (point: GridPoint) => {
      if (activeLayer === "full") {
        toggleCell({ x: Math.floor(point.gx), y: Math.floor(point.gy) });
        return;
      }
      if (activeLayer === "half" || activeLayer === "quarter") {
        toggleGridLayer(activeLayer, { x: Math.floor(point.gx), y: Math.floor(point.gy) });
        return;
      }

      // Backstitch / knot: the target is the segment or point nearest the
      // touch, not a cell — disabled below `SYMBOL_MIN_CELL` (the same
      // threshold at which symbols appear): at that zoom, a cell is a few
      // pixels and two neighbouring elements would become impossible to tell
      // apart with a finger.
      if (cell < SYMBOL_MIN_CELL) return;
      const tolerance = Math.min(SPECIAL_TAP_TOLERANCE_MAX_CELLS, SPECIAL_TAP_TOLERANCE_PX / cell);
      if (activeLayer === "backstitch") {
        const index = nearestBackstitchIndex(pattern.backstitch, point.gx, point.gy, tolerance);
        if (index !== null) toggleElementLayer("backstitch", index);
      } else {
        const index = nearestKnotIndex(pattern.frenchKnots, point.gx, point.gy, tolerance);
        if (index !== null) toggleElementLayer("knot", index);
      }
    },
    [activeLayer, cell, pattern, toggleCell, toggleGridLayer, toggleElementLayer],
  );

  const fillSelection = useCallback(
    (value: 0 | 1) => {
      if (selection === null) return;
      snapshot();
      const minX = Math.max(0, Math.min(selection.x0, selection.x1));
      const maxX = Math.min(pattern.width - 1, Math.max(selection.x0, selection.x1));
      const minY = Math.max(0, Math.min(selection.y0, selection.y1));
      const maxY = Math.min(pattern.height - 1, Math.max(selection.y0, selection.y1));

      const changes: CellChange[] = [];
      const current = doneRef.current;
      for (let y = minY; y <= maxY; y++) {
        for (let x = minX; x <= maxX; x++) {
          const index = y * pattern.width + x;
          const colour = pattern.cells[index] ?? 0;
          if (colour === 0) continue;
          // With an active filter, only the filtered colour is filled: this is
          // the "finish this colour in the visible area" gesture.
          if (highlight !== 0 && colour !== highlight) continue;
          if (current.full[index] === value) continue;
          current.full[index] = value;
          changes.push({ layer: "full", index, stitched: value });
        }
      }
      setVersion((value2) => value2 + 1);
      if (changes.length > 0) onChangeRef.current?.(changes);
    },
    [selection, pattern, highlight, snapshot],
  );

  const undo = useCallback(() => {
    const previous = historyRef.current.pop();
    if (previous === undefined) return;
    // Write back into the same arrays rather than changing their reference:
    // the library and statistics point to them and must keep seeing the real
    // progress after an undo.
    const current = doneRef.current;
    const changes: CellChange[] = [];
    const hasListener = onChangeRef.current !== undefined;
    const restoreLayer = (layer: StitchLayer, previousArray: Uint8Array, currentArray: Uint8Array): void => {
      if (hasListener) {
        for (let index = 0; index < previousArray.length; index++) {
          const value = previousArray[index] as 0 | 1;
          if (currentArray[index] !== value) changes.push({ layer, index, stitched: value });
        }
      }
      currentArray.set(previousArray);
    };
    restoreLayer("full", previous.full, current.full);
    restoreLayer("half", previous.half, current.half);
    restoreLayer("quarter", previous.quarter, current.quarter);
    restoreLayer("backstitch", previous.backstitch, current.backstitch);
    restoreLayer("knot", previous.knot, current.knot);
    setVersion((value) => value + 1);
    if (changes.length > 0) onChangeRef.current?.(changes);
  }, []);

  const applyRemote = useCallback((changes: CellChange[]) => {
    if (changes.length === 0) return;
    const current = doneRef.current;
    for (const change of changes) {
      layerArray(current, change.layer)[change.index] = change.stitched;
    }
    setVersion((value) => value + 1);
  }, []);

  const setOffset = useCallback(
    (x0: number, y0: number) => {
      const marginX = panMargin(pattern.width);
      const marginY = panMargin(pattern.height);
      setOffsetState({
        x0: Math.max(-marginX, Math.min(pattern.width - marginX, x0)),
        y0: Math.max(-marginY, Math.min(pattern.height - marginY, y0)),
      });
    },
    [pattern],
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
      // Pattern cell currently under the anchor point (the pinch midpoint),
      // before the cell size changes.
      const anchorCellX = offset.x0 + (anchorScreenX - canvasRect.left) / cell;
      const anchorCellY = offset.y0 + (anchorScreenY - canvasRect.top) / cell;
      setCell(clampedCell);
      // Reposition the view's origin so that this same pattern cell is still
      // under the anchor point once the size has changed — this is what makes
      // it "zoom under the fingers" rather than towards a corner — then add
      // the pan from the same gesture, rather than a separate `setOffset`
      // that would be overwritten by this computation.
      setOffset(
        anchorCellX - (anchorScreenX - canvasRect.left) / clampedCell + panDeltaX,
        anchorCellY - (anchorScreenY - canvasRect.top) / clampedCell,
      );
    },
    [cell, offset, setOffset],
  );

  const toggleHighlight = useCallback(
    (index: number) => setHighlight((current) => (current === index ? 0 : index)),
    [],
  );
  const clearHighlight = useCallback(() => setHighlight(0), []);

  const toggleHideDone = useCallback(() => setHideDone((current) => !current), []);

  const view: GridView = { cell, x0: offset.x0, y0: offset.y0 };

  return {
    pattern,
    done,
    special: { half: state.half, quarter: state.quarter, backstitch: state.backstitch, knot: state.knot },
    version,
    counts,
    totals,
    view,
    setOffset,
    zoomIn,
    zoomOut,
    zoomTo,
    tool,
    setTool,
    activeLayer,
    setActiveLayer,
    highlight,
    toggleHighlight,
    clearHighlight,
    hideDone,
    toggleHideDone,
    cursor,
    setCursor,
    selection,
    setSelection,
    toggleCell,
    toggleAtPoint,
    fillSelection,
    undo,
    canUndo: historyRef.current.length > 0,
    applyRemote,
  };
}
