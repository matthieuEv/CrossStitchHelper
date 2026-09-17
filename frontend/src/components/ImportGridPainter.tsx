import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { useT } from "../i18n";
import { useTheme } from "../lib/theme";
import { drawGrid, drawOverlay, onSymbolImageLoaded, readGridTheme } from "../pattern/render";
import type { CellPosition, ImportPainter } from "../state/useImportPainter";

interface ImportGridPainterProps {
  painter: ImportPainter;
  /** Index de palette 1-based actuellement choisi pour peindre ; 0 = gomme. */
  activeIndex: number;
}

/**
 * Canvas de peinture par zone (Lot 2) : glisser dessine une sélection
 * rectangulaire, qui se peint immédiatement de la couleur active dès que le
 * doigt se lève — même geste que « marquer toute cette couleur » côté suivi,
 * sans bouton de confirmation séparé pour rester rapide sur une grille peinte
 * à la main case par case.
 */
export function ImportGridPainter({ painter, activeIndex }: ImportGridPainterProps) {
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

  // Voir TrackScreen.tsx : force un nouveau rendu une fois qu'un symbole
  // réel (Lot 4) termine de se décoder de façon asynchrone.
  const [symbolImageTick, setSymbolImageTick] = useState(0);
  useEffect(() => onSymbolImageLoaded(() => setSymbolImageTick((value) => value + 1)), []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;
    const theme = readGridTheme(canvas);
    const drawn = drawGrid(canvas, { pattern, done: null, view, theme, highlight: 0 });
    if (!drawn) return;
    const accent = getComputedStyle(canvas).getPropertyValue("--color-accent").trim();
    drawOverlay(canvas, { view, accent, cursor, selection });
  }, [pattern, view, cursor, selection, resolved, symbolImageTick]);

  // Molette/trackpad : zoome sous le curseur — voir TrackScreen.tsx pour le
  // détail (écouteur DOM natif, pas `onWheel` React, pour que
  // `preventDefault()` empêche vraiment le défilement de la page).
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      // Glissé horizontal du trackpad : déplace la vue plutôt que de zoomer
      // — voir TrackScreen.tsx pour le détail du même choix, et pour
      // pourquoi un geste en diagonale doit passer par le même appel à
      // `zoomTo` plutôt qu'un `setOffset` séparé.
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
