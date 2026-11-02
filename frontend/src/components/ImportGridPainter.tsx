import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { useT } from "../i18n";
import type { ApiImportStitch } from "../lib/api";

/** The import brush (issues #41, #82): a cell stitch type painted by area,
 * or a backstitch drawn corner to corner, or a knot placed on a cell. */
export type ImportBrush = ApiImportStitch | "backstitch" | "knot";

/** Tap tolerance for erasing a backstitch, in screen pixels — converted to
 * cells at the current zoom, with a floor so a segment stays easy to hit
 * when zoomed in. */
const ERASE_TOLERANCE_PX = 14;

/** How far a finger may move, in screen pixels, and still count as a tap. */
const TAP_SLOP_PX = 8;

interface GridPoint {
  gx: number;
  gy: number;
}
import { useTheme } from "../lib/theme";
import { drawGrid, drawOverlay, onSymbolImageLoaded, readGridTheme } from "../pattern/render";
import type { CellPosition, ImportPainter } from "../state/useImportPainter";
import { UndoIcon } from "./Icons";

interface ImportGridPainterProps {
  painter: ImportPainter;
  /** 1-based palette index currently chosen for painting; 0 = eraser. */
  activeIndex: number;
  /** What the brush does (issues #41, #82), chosen in `StitchTypeBar`. */
  stitch: ImportBrush;
  /** Cells flagged uncertain by type B/C detection (Lot 5) — see
   * `pattern/render.ts::DrawGridOptions.uncertainCells`. */
  uncertainCells?: ReadonlySet<number> | null;
}

/**
 * Area-painting canvas (Lot 2): dragging draws a rectangular selection,
 * which is painted with the active colour as soon as the finger lifts — the
 * same gesture as "mark all of this colour" in tracking, with no separate
 * confirmation button so it stays quick on a grid painted by hand cell by
 * cell.
 */
export function ImportGridPainter({
  painter,
  activeIndex,
  stitch,
  uncertainCells = null,
}: ImportGridPainterProps) {
  const t = useT();
  const { resolved } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const dragRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  });

  const [tool, setTool] = useState<"paint" | "pan">("paint");
  // Backstitch tool: the corner under the pointer (mouse hover).
  const [hoverCorner, setHoverCorner] = useState<CellPosition | null>(null);
  const { pattern, view, cursor, selection } = painter;

  // "Show next": centres the uncertain cells one after the other, in reading
  // order (row by row), wrapping around after the last one.
  const lastShownRef = useRef(-1);
  const showNextUncertain = (): void => {
    const canvas = canvasRef.current;
    if (canvas === null || uncertainCells === null || uncertainCells.size === 0) return;
    const sorted = [...uncertainCells].sort((a, b) => a - b);
    const next = sorted.find((index) => index > lastShownRef.current) ?? sorted[0];
    if (next === undefined) return;
    lastShownRef.current = next;
    const x = next % pattern.width;
    const box = canvas.getBoundingClientRect();
    painter.focusCell(x, (next - x) / pattern.width, box.width, box.height);
  };

  // See TrackScreen.tsx: forces a re-render once a real symbol (Lot 4)
  // finishes decoding asynchronously.
  const [symbolImageTick, setSymbolImageTick] = useState(0);
  useEffect(() => onSymbolImageLoaded(() => setSymbolImageTick((value) => value + 1)), []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;
    const theme = readGridTheme(canvas);
    const accent = getComputedStyle(canvas).getPropertyValue("--color-accent").trim();
    const drawn = drawGrid(canvas, {
      pattern,
      done: null,
      view,
      theme,
      highlight: 0,
      uncertainCells,
      uncertainColor: accent,
    });
    if (!drawn) return;
    if (stitch === "backstitch") {
      // Corners, not cells: the hovered corner and the pending start.
      drawOverlay(canvas, {
        view,
        accent,
        cursor: null,
        selection: null,
        hoverCorner,
        pendingCorner: painter.pendingCorner,
      });
    } else {
      drawOverlay(canvas, { view, accent, cursor, selection });
    }
  }, [
    pattern,
    view,
    cursor,
    selection,
    resolved,
    symbolImageTick,
    uncertainCells,
    stitch,
    painter.pendingCorner,
    hoverCorner,
  ]);

  // A segment started with the backstitch tool does not survive switching
  // to another tool.
  const { cancelPendingCorner } = painter;
  useEffect(() => {
    if (stitch !== "backstitch") cancelPendingCorner();
  }, [stitch, cancelPendingCorner]);

  // Wheel/trackpad: zooms under the cursor — see TrackScreen.tsx for the
  // details (native DOM listener, not React `onWheel`, so that
  // `preventDefault()` really prevents page scrolling).
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      // Horizontal trackpad swipe: pans the view rather than zooming — see
      // TrackScreen.tsx for the details of the same choice, and for why a
      // diagonal gesture must go through the same `zoomTo` call rather than
      // a separate `setOffset`.
      const panDeltaX = event.deltaX !== 0 ? event.deltaX / view.cell : 0;
      if (event.deltaY !== 0) {
        const rect = canvas.getBoundingClientRect();
        const factor = Math.pow(1.0015, -event.deltaY);
        painter.zoomTo(view.cell * factor, event.clientX, event.clientY, rect, panDeltaX);
      } else if (panDeltaX !== 0) {
        painter.setOffset(view.x0 + panDeltaX, view.y0);
      }
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [painter.zoomTo, painter.setOffset, view.cell, view.x0]);

  const cellAt = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>): CellPosition => {
      const box = event.currentTarget.getBoundingClientRect();
      return {
        x: Math.floor(view.x0 + (event.clientX - box.left) / view.cell),
        y: Math.floor(view.y0 + (event.clientY - box.top) / view.cell),
      };
    },
    [view],
  );

  /** Grid position under the pointer, in cells (corner coordinates). */
  const gridPointAt = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>): GridPoint => {
      const box = event.currentTarget.getBoundingClientRect();
      return {
        gx: view.x0 + (event.clientX - box.left) / view.cell,
        gy: view.y0 + (event.clientY - box.top) / view.cell,
      };
    },
    [view],
  );

  const nearestCorner = ({ gx, gy }: GridPoint): CellPosition => ({
    x: Math.max(0, Math.min(pattern.width, Math.round(gx))),
    y: Math.max(0, Math.min(pattern.height, Math.round(gy))),
  });

  // Backstitch and knots act on a tap rather than a drag: where the finger
  // went down, once it lifts without having moved away — a drag pans the
  // view instead, so the grid can still be moved with this tool.
  const tapRef = useRef<{
    clientX: number;
    clientY: number;
    point: GridPoint;
  } | null>(null);
  const tapsStitches = tool === "paint" && (stitch === "backstitch" || stitch === "knot");

  const tapStitch = (point: GridPoint): void => {
    if (stitch === "backstitch") {
      if (activeIndex === 0) {
        painter.eraseBackstitchAt(
          point.gx,
          point.gy,
          Math.max(0.3, ERASE_TOLERANCE_PX / view.cell),
        );
      } else {
        const corner = nearestCorner(point);
        painter.tapCorner(corner.x, corner.y, activeIndex);
      }
    } else if (stitch === "knot") {
      painter.tapKnot(Math.floor(point.gx), Math.floor(point.gy), activeIndex);
    }
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const cell = cellAt(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      active: true,
      lastX: event.clientX,
      lastY: event.clientY,
    };
    if (tapsStitches) {
      tapRef.current = {
        clientX: event.clientX,
        clientY: event.clientY,
        point: gridPointAt(event),
      };
    } else if (tool === "paint") {
      painter.setSelection({ x0: cell.x, y0: cell.y, x1: cell.x, y1: cell.y });
    }
    painter.setCursor(cell);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const drag = dragRef.current;
    const cell = cellAt(event);
    if (stitch === "backstitch") setHoverCorner(nearestCorner(gridPointAt(event)));
    if (!drag.active) {
      painter.setCursor(cell);
      return;
    }

    const tap = tapRef.current;
    if (
      tap !== null &&
      Math.hypot(event.clientX - tap.clientX, event.clientY - tap.clientY) > TAP_SLOP_PX
    ) {
      tapRef.current = null;
    }

    if (tool === "pan" || (tapsStitches && tapRef.current === null)) {
      const dx = (event.clientX - drag.lastX) / view.cell;
      const dy = (event.clientY - drag.lastY) / view.cell;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
      painter.setOffset(view.x0 - dx, view.y0 - dy);
      return;
    }

    if (painter.selection !== null) {
      painter.setSelection({ ...painter.selection, x1: cell.x, y1: cell.y });
    }
    painter.setCursor(cell);
  };

  const onPointerUp = (): void => {
    // `pointerleave` also ends a gesture (a drag that leaves the canvas), but
    // it fires after `pointerup` too — a finger lifting, a mouse moving away
    // after a click: without this guard the same area was painted twice, so
    // the first undo seemed to do nothing.
    if (!dragRef.current.active) return;
    const tap = tapRef.current;
    tapRef.current = null;
    if (tap !== null) {
      tapStitch(tap.point);
    } else if (
      tool === "paint" &&
      painter.selection !== null &&
      stitch !== "backstitch" &&
      stitch !== "knot"
    ) {
      painter.paint(activeIndex, stitch);
    }
    dragRef.current = { ...dragRef.current, active: false };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        className="track-canvas-wrap edit-area"
        style={{ height: 320, borderRadius: 18, overflow: "hidden" }}
      >
        <canvas
          ref={canvasRef}
          className="track-canvas"
          style={{
            cursor: tool === "pan" ? "grab" : stitch === "knot" ? "pointer" : "crosshair",
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={() => {
            setHoverCorner(null);
            onPointerUp();
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-pressed={tool === "paint"}
            aria-label={t("import.paint.tool.paint")}
            onClick={() => setTool("paint")}
          >
            🖌
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-pressed={tool === "pan"}
            aria-label={t("import.paint.tool.pan")}
            onClick={() => setTool("pan")}
          >
            ✥
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label={t("import.paint.undo")}
            title={t("import.paint.undo")}
            onClick={painter.undo}
            disabled={!painter.canUndo}
            style={{ opacity: painter.canUndo ? 1 : 0.4 }}
          >
            <UndoIcon />
          </button>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label={t("track.zoomOut")}
            onClick={painter.zoomOut}
          >
            −
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label={t("track.zoomIn")}
            onClick={painter.zoomIn}
          >
            +
          </button>
        </div>
      </div>
      <div className="text-muted" style={{ fontSize: 12 }}>
        {t("import.paint.filled", {
          filled: painter.filledCount,
          total: painter.cellCount,
        })}
      </div>
      {uncertainCells !== null && uncertainCells.size > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            fontSize: 12,
          }}
        >
          <span className="uncertain-sample" aria-hidden="true" />
          <span className="text-muted" style={{ flex: "1 1 180px" }}>
            {t("import.paint.uncertainHint", { count: uncertainCells.size })}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ minHeight: 36, padding: "0 14px", fontSize: 13 }}
            onClick={showNextUncertain}
          >
            {t("import.paint.uncertainNext")}
          </button>
        </div>
      )}
    </div>
  );
}

const STITCHES: readonly ImportBrush[] = ["full", "half", "quarter", "backstitch", "knot"];

/** Stitch-type toolbar of the import brush (issues #41, #82): full, 1/2 or
 * 1/4 painted by area, backstitch drawn corner to corner, knot on a cell.
 * Kept outside `ImportGridPainter` so the grid stays level with the source
 * file shown beside it on a wide screen (issue #40). */
export function StitchTypeBar({
  stitch,
  onChange,
}: {
  stitch: ImportBrush;
  onChange: (stitch: ImportBrush) => void;
}) {
  const t = useT();
  return (
    <div
      className="seg"
      role="group"
      aria-label={t("import.paint.stitch")}
      // Five entries (issue #82): narrower than the default `.seg` padding,
      // so the bar still fits a 320 px wide phone.
      style={{ alignSelf: "flex-start", maxWidth: "100%" }}
    >
      {STITCHES.map((item) => (
        <button
          key={item}
          type="button"
          style={{ padding: "0 10px", flex: "1 1 auto" }}
          aria-pressed={stitch === item}
          aria-label={t(`import.paint.stitch.${item}`)}
          title={t(`import.paint.stitch.${item}`)}
          onClick={() => onChange(item)}
        >
          {t(`import.paint.stitch.${item}.short`)}
        </button>
      ))}
    </div>
  );
}
