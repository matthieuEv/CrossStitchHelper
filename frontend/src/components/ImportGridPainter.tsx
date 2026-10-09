import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { useT } from "../i18n";
import { useTheme } from "../lib/theme";
import { drawGrid, drawOverlay, onSymbolImageLoaded, readGridTheme } from "../pattern/render";
import type { CellPosition, ImportPainter } from "../state/useImportPainter";

interface ImportGridPainterProps {
  painter: ImportPainter;
  /** 1-based palette index currently chosen for painting; 0 = eraser. */
  activeIndex: number;
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
  const { pattern, view, cursor, selection } = painter;

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
    drawOverlay(canvas, { view, accent, cursor, selection });
  }, [pattern, view, cursor, selection, resolved, symbolImageTick, uncertainCells]);

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

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const cell = cellAt(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { active: true, lastX: event.clientX, lastY: event.clientY };
    if (tool === "paint") {
      painter.setSelection({ x0: cell.x, y0: cell.y, x1: cell.x, y1: cell.y });
    }
    painter.setCursor(cell);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const drag = dragRef.current;
    const cell = cellAt(event);
    if (!drag.active) {
      painter.setCursor(cell);
      return;
    }

    if (tool === "pan") {
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
    if (tool === "paint" && painter.selection !== null) {
      painter.paint(activeIndex);
    }
    dragRef.current = { ...dragRef.current, active: false };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        className="track-canvas-wrap"
        style={{ height: 320, borderRadius: 18, overflow: "hidden" }}
      >
        <canvas
          ref={canvasRef}
          className="track-canvas"
          style={{ cursor: tool === "pan" ? "grab" : "crosshair" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerUp}
        />
      </div>
      <div
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}
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
        {t("import.paint.filled", { filled: painter.filledCount, total: painter.cellCount })}
      </div>
    </div>
  );
}
