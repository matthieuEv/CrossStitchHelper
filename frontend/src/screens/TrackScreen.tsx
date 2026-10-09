import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { ColorList } from "../components/ColorList";
import {
  BackIcon,
  BackstitchIcon,
  CloseIcon,
  EyeOffIcon,
  FrenchKnotIcon,
  HalfStitchIcon,
  MinusIcon,
  PanIcon,
  PlusIcon,
  QuarterStitchIcon,
  SelectIcon,
  StitchIcon,
  UndoIcon,
} from "../components/Icons";
import { useT } from "../i18n";
import { useElementSize } from "../lib/hooks";
import { useNumberFormat } from "../lib/format";
import { useTheme } from "../lib/theme";
import {
  SYMBOL_MIN_CELL,
  drawGrid,
  drawOverlay,
  onSymbolImageLoaded,
  readGridTheme,
} from "../pattern/render";
import type { CellPosition, Tracker } from "../state/useTracker";

/**
 * Distance, in pixels, beyond which a touch is considered a pan rather than a
 * tap.
 *
 * Too low, and checking a cell moves the grid by accident; too high, and
 * scrolling feels sticky. This value is tuned for a finger, not a mouse.
 */
const DRAG_THRESHOLD = 7;

interface TrackScreenProps {
  tracker: Tracker;
  wide: boolean;
  onBack: () => void;
}

export function TrackScreen({ tracker, wide, onBack }: TrackScreenProps) {
  const t = useT();
  const formatNumber = useNumberFormat();
  const { resolved } = useTheme();

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [wrapRef, size] = useElementSize<HTMLDivElement>();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const dragRef = useRef<{
    active: boolean;
    panning: boolean;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    cell: CellPosition | null;
    /** Fractional touch point (Lot 8), captured at the same moment as `cell`
     * — needed to target a backstitch segment or a knot, which are not aligned
     * on the cell grid (see `tracker.toggleAtPoint`). */
    point: { gx: number; gy: number } | null;
  }>({
    active: false,
    panning: false,
    startX: 0,
    startY: 0,
    lastX: 0,
    lastY: 0,
    cell: null,
    point: null,
  });

  /** Last known position (client coordinates) of each active touch. */
  const pointersRef = useRef<Map<number, { x: number; y: number }>>(new Map());
  /**
   * Two-finger pinch state, active between the moment the second touch goes
   * down and the moment either of the two is released. `ids` fixes the two
   * pointers tracked for the whole gesture: any third touch is ignored rather
   * than disturbing the computation.
   */
  const pinchRef = useRef<{
    ids: [number, number];
    initialDistance: number;
    initialCell: number;
  } | null>(null);

  const {
    pattern,
    view,
    tool,
    activeLayer,
    highlight,
    hideDone,
    cursor,
    selection,
    totals,
    counts,
    version,
  } = tracker;

  // A real symbol (Lot 4) decodes asynchronously the first time it appears on
  // screen (see `onSymbolImageLoaded`): this counter forces a re-render once
  // it is ready, to replace the text fallback shown in the meantime.
  const [symbolImageTick, setSymbolImageTick] = useState(0);
  useEffect(() => onSymbolImageLoaded(() => setSymbolImageTick((value) => value + 1)), []);

  // Redraws the grid then the markers. The dependencies cover everything that
  // can change the image: progress, view, filter, theme and box size.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const theme = readGridTheme(canvas);
    const drawn = drawGrid(canvas, {
      pattern,
      done: tracker.done,
      special: tracker.special,
      view,
      theme,
      highlight,
      hideDone,
    });
    if (!drawn) return;

    const accent = getComputedStyle(canvas).getPropertyValue("--color-accent").trim();
    drawOverlay(canvas, { view, accent, cursor, selection });
  }, [
    pattern,
    tracker.done,
    tracker.special,
    version,
    view,
    highlight,
    hideDone,
    cursor,
    selection,
    resolved,
    size,
    symbolImageTick,
  ]);

  // Wheel and trackpad (two-finger scroll, on macOS as on Windows): zooms
  // under the cursor rather than scrolling the page. A native DOM listener
  // rather than React `onWheel`: a React handler is attached as "passive" for
  // this event, which would stop `preventDefault()` from working and let the
  // page scroll behind the canvas.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      // Horizontal trackpad swipe (deltaX): pans the view rather than
      // zooming — an explicit request, distinct from vertical scrolling
      // (deltaY), which zooms. A diagonal gesture does a bit of both at once:
      // both must go through the same `zoomTo` call, which recomputes the
      // view's origin entirely — a separate `setOffset` for the pan would
      // immediately be overwritten (a real bug found in manual testing:
      // panning seemed stuck as soon as you zoomed at the same time).
      const panDeltaX = event.deltaX !== 0 ? event.deltaX / view.cell : 0;
      if (event.deltaY !== 0) {
        const rect = canvas.getBoundingClientRect();
        // Exponential scale for the zoom factor: a mouse wheel sends large
        // discrete steps (~100 per notch), a trackpad small continuous steps —
        // proportional to the delta, the feel stays smooth in both cases, like
        // the existing two-finger pinch.
        const factor = Math.pow(1.0015, -event.deltaY);
        tracker.zoomTo(view.cell * factor, event.clientX, event.clientY, rect, panDeltaX);
      } else if (panDeltaX !== 0) {
        tracker.setOffset(view.x0 + panDeltaX, view.y0);
      }
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [tracker.zoomTo, tracker.setOffset, view.cell, view.x0]);

  const cellAt = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>): CellPosition => {
      const canvas = event.currentTarget;
      const box = canvas.getBoundingClientRect();
      return {
        x: Math.floor(view.x0 + (event.clientX - box.left) / view.cell),
        y: Math.floor(view.y0 + (event.clientY - box.top) / view.cell),
      };
    },
    [view],
  );

  /** Like `cellAt`, without rounding — needed to target a backstitch segment
   * or a knot (Lot 8), which are not aligned on the cell grid (see
   * `tracker.toggleAtPoint`). */
  const pointAt = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>): { gx: number; gy: number } => {
      const canvas = event.currentTarget;
      const box = canvas.getBoundingClientRect();
      return {
        gx: view.x0 + (event.clientX - box.left) / view.cell,
        gy: view.y0 + (event.clientY - box.top) / view.cell,
      };
    },
    [view],
  );

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (pointersRef.current.size >= 2 && pinchRef.current === null) {
      // Second touch: switch to pinching, whatever the active tool — it is a
      // navigation gesture, not a tool, it must work with "check", "move" and
      // "select".
      const ids = [...pointersRef.current.keys()].slice(0, 2) as [number, number];
      const p1 = pointersRef.current.get(ids[0])!;
      const p2 = pointersRef.current.get(ids[1])!;
      pinchRef.current = {
        ids,
        initialDistance: Math.hypot(p2.x - p1.x, p2.y - p1.y),
        initialCell: view.cell,
      };
      // Cancel any in-progress check/selection state from the first touch: a
      // pinch must never end with a cell checked or a selection drawn by
      // accident.
      dragRef.current = { ...dragRef.current, active: false, panning: false, cell: null, point: null };
      if (tool === "select") tracker.setSelection(null);
      tracker.setCursor(null);
      return;
    }

    if (pointersRef.current.size > 2) return; // Third touch: ignored.

    const cell = cellAt(event);
    const point = pointAt(event);
    dragRef.current = {
      active: true,
      panning: false,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      cell,
      point,
    };

    if (tool === "select") {
      tracker.setSelection({ x0: cell.x, y0: cell.y, x1: cell.x, y1: cell.y });
      tracker.setCursor(cell);
      return;
    }
    if (tool === "stitch") tracker.setCursor(cell);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    if (pointersRef.current.has(event.pointerId)) {
      pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    }

    if (pinchRef.current !== null) {
      const [id1, id2] = pinchRef.current.ids;
      const p1 = pointersRef.current.get(id1);
      const p2 = pointersRef.current.get(id2);
      // Both tracked touches must still be active; otherwise wait for the
      // pointerup that will end the pinch.
      if (p1 !== undefined && p2 !== undefined) {
        const distance = Math.hypot(p2.x - p1.x, p2.y - p1.y);
        const scale =
          pinchRef.current.initialDistance > 0 ? distance / pinchRef.current.initialDistance : 1;
        const nextCell = pinchRef.current.initialCell * scale;
        const midX = (p1.x + p2.x) / 2;
        const midY = (p1.y + p2.y) / 2;
        // The pinch midpoint must stay on the same pattern cell: zoom "under
        // the fingers", not towards a corner of the screen.
        tracker.zoomTo(nextCell, midX, midY, event.currentTarget.getBoundingClientRect());
      }
      return;
    }

    const drag = dragRef.current;
    const cell = cellAt(event);

    if (!drag.active) {
      // Mouse hover: the crosshair follows the pointer. With no touch in
      // progress, there is nothing else to do.
      tracker.setCursor(cell);
      return;
    }

    const pan = (): void => {
      const dx = (event.clientX - drag.lastX) / view.cell;
      const dy = (event.clientY - drag.lastY) / view.cell;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
      tracker.setOffset(view.x0 - dx, view.y0 - dy);
    };

    if (tool === "pan") {
      pan();
      return;
    }
    if (tool === "select") {
      if (selection !== null) {
        tracker.setSelection({ ...selection, x1: cell.x, y1: cell.y });
      }
      tracker.setCursor(cell);
      return;
    }

    // "Check" tool: a tap checks, a drag moves the grid. Only switch to panning
    // beyond the threshold, otherwise the slightest finger tremor would
    // prevent checking.
    if (!drag.panning) {
      const travelled = Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY);
      if (travelled < DRAG_THRESHOLD) return;
      drag.panning = true;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
    }
    pan();
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    pointersRef.current.delete(event.pointerId);

    if (pinchRef.current !== null) {
      if (pointersRef.current.size < 2) {
        // The pinch stops as soon as one of the two tracked touches is
        // released. The remaining touch, if any, does not resume a smooth pan
        // — a slight jump on the next gesture is accepted.
        pinchRef.current = null;
      }
      dragRef.current = { ...dragRef.current, active: false, panning: false, cell: null, point: null };
      return;
    }

    const drag = dragRef.current;
    // The element is only checked on release: that is what allows starting a
    // drag from anywhere without checking along the way. The targeted
    // category (`tracker.activeLayer`, Lot 8) decides whether `point` targets
    // a cell (full/half/quarter) or the nearest segment/knot
    // (backstitch/knot) — see `tracker.toggleAtPoint`.
    if (drag.active && !drag.panning && drag.point !== null && tool === "stitch") {
      tracker.toggleAtPoint(drag.point);
    }
    dragRef.current = { ...drag, active: false, panning: false, cell: null, point: null };
  };

  const activeColor = highlight === 0 ? null : (counts[highlight - 1] ?? null);
  // `view.cell` continuously takes fractional values during a wheel/trackpad
  // zoom or a pinch (`zoomTo`) — rounded only for display, never for
  // rendering itself (`drawGrid` copes perfectly well with a non-integer cell
  // size).
  const roundedCell = Math.round(view.cell);
  const zoomLabel =
    roundedCell >= SYMBOL_MIN_CELL
      ? t("track.zoom.symbols", { size: roundedCell })
      : t("track.zoom.blocks", { size: roundedCell });

  const colorList = (
    <ColorList counts={counts} highlight={highlight} onToggle={tracker.toggleHighlight} />
  );

  return (
    <div className="track-layout">
      <div className="track">
        <header className="track-head">
          <button
            type="button"
            className="btn btn-icon btn-secondary"
            onClick={onBack}
            aria-label={t("track.back")}
          >
            <BackIcon size={20} />
          </button>

          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontFamily: "var(--font-heading)",
                fontSize: 16,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {pattern.name}
            </div>
            <div
              className="text-muted num"
              style={{
                fontSize: 12,
                // Without this, "Row 140 · Column 100" wraps onto two lines on
                // an iPhone and makes the header a third taller.
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {t("track.position", {
                row: (cursor?.y ?? Math.round(view.y0)) + 1,
                col: (cursor?.x ?? Math.round(view.x0)) + 1,
              })}
            </div>
          </div>

          <div style={{ flex: "none", textAlign: "right" }}>
            <div className="num" style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
              {totals.percent}%
            </div>
            <div className="text-faint" style={{ fontSize: 11 }}>
              {t("track.remaining", { count: formatNumber(totals.remaining) })}
            </div>
          </div>

          {!wide && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ minHeight: 44, flex: "none", padding: "0 12px", gap: 8 }}
              onClick={() => setDrawerOpen(true)}
            >
              <span
                className="swatch"
                style={{
                  width: 14,
                  height: 14,
                  background: activeColor?.hex ?? "var(--color-neutral-400)",
                }}
              />
              {activeColor === null ? t("track.colors") : `DMC ${activeColor.code}`}
            </button>
          )}
        </header>

        <div className="track-canvas-wrap" ref={wrapRef}>
          <canvas
            ref={canvasRef}
            className="track-canvas"
            style={{ cursor: tool === "pan" ? "grab" : tool === "select" ? "crosshair" : "cell" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onPointerLeave={onPointerUp}
          />

          <div className="track-badges">
            <span className="badge text-muted num">{zoomLabel}</span>

            {selection !== null && (
              <>
                <span
                  className="badge num"
                  style={{ background: "var(--color-accent)", color: "var(--color-bg)" }}
                >
                  {t("track.selection", {
                    cols: Math.abs(selection.x1 - selection.x0) + 1,
                    rows: Math.abs(selection.y1 - selection.y0) + 1,
                  })}
                </span>
                {/* With an active colour filter, these actions only affect that
                    colour: it is the "I'm finishing this thread here" gesture. */}
                <button type="button" className="badge" onClick={() => tracker.fillSelection(1)}>
                  {t("track.fillSelection")}
                </button>
                <button type="button" className="badge" onClick={() => tracker.fillSelection(0)}>
                  {t("track.emptySelection")}
                </button>
                <button
                  type="button"
                  className="badge"
                  onClick={() => tracker.setSelection(null)}
                  aria-label={t("track.dropSelection")}
                >
                  ✕
                </button>
              </>
            )}

            {activeColor !== null && (
              <span className="badge">
                <span className="swatch" style={{ width: 12, height: 12, background: activeColor.hex }} />
                {t("track.filter", { dmc: activeColor.code })}
                <button
                  type="button"
                  onClick={tracker.clearHighlight}
                  aria-label={t("track.clearFilter")}
                  style={{ border: 0, background: "transparent", cursor: "pointer", fontSize: 13, padding: "0 2px" }}
                >
                  ✕
                </button>
              </span>
            )}
          </div>

          <div className="toolbar" role="toolbar" aria-label={t("nav.track")}>
            <button type="button" onClick={tracker.zoomOut} aria-label={t("track.zoomOut")}>
              <MinusIcon />
            </button>
            <button type="button" onClick={tracker.zoomIn} aria-label={t("track.zoomIn")}>
              <PlusIcon />
            </button>
            <div className="sep" />
            <button
              type="button"
              onClick={tracker.undo}
              aria-label={t("track.undo")}
              disabled={!tracker.canUndo}
              style={{ opacity: tracker.canUndo ? 1 : 0.4 }}
            >
              <UndoIcon />
            </button>
            <button
              type="button"
              aria-pressed={hideDone}
              onClick={tracker.toggleHideDone}
              aria-label={t(hideDone ? "track.showDone" : "track.hideDone")}
            >
              <EyeOffIcon />
            </button>
            <div className="sep" />
            <button
              type="button"
              aria-pressed={tool === "stitch"}
              onClick={() => {
                tracker.setTool("stitch");
                tracker.setSelection(null);
              }}
              aria-label={t("track.tool.stitch")}
            >
              <StitchIcon />
            </button>
            <button
              type="button"
              aria-pressed={tool === "pan"}
              onClick={() => tracker.setTool("pan")}
              aria-label={t("track.tool.pan")}
            >
              <PanIcon />
            </button>
            <button
              type="button"
              aria-pressed={tool === "select"}
              onClick={() => tracker.setTool("select")}
              aria-label={t("track.tool.select")}
            >
              <SelectIcon />
            </button>
          </div>

          {tool === "stitch" && (
            <div className="toolbar-layers" role="toolbar" aria-label={t("track.layer.title")}>
              <button
                type="button"
                aria-pressed={activeLayer === "full"}
                onClick={() => tracker.setActiveLayer("full")}
                aria-label={t("track.layer.full")}
              >
                <StitchIcon size={17} />
              </button>
              <button
                type="button"
                aria-pressed={activeLayer === "half"}
                onClick={() => tracker.setActiveLayer("half")}
                aria-label={t("track.layer.half")}
              >
                <HalfStitchIcon size={17} />
              </button>
              <button
                type="button"
                aria-pressed={activeLayer === "quarter"}
                onClick={() => tracker.setActiveLayer("quarter")}
                aria-label={t("track.layer.quarter")}
              >
                <QuarterStitchIcon size={17} />
              </button>
              <div className="sep" />
              {/* Backstitch / knots: targets too small for a reliable tap below
                  `SYMBOL_MIN_CELL` — disabled rather than silently inoperative,
                  see `tracker.toggleAtPoint`. */}
              <button
                type="button"
                aria-pressed={activeLayer === "backstitch"}
                onClick={() => tracker.setActiveLayer("backstitch")}
                disabled={view.cell < SYMBOL_MIN_CELL}
                aria-label={t("track.layer.backstitch")}
                title={view.cell < SYMBOL_MIN_CELL ? t("track.layer.zoomHint") : undefined}
              >
                <BackstitchIcon size={17} />
              </button>
              <button
                type="button"
                aria-pressed={activeLayer === "knot"}
                onClick={() => tracker.setActiveLayer("knot")}
                disabled={view.cell < SYMBOL_MIN_CELL}
                aria-label={t("track.layer.knot")}
                title={view.cell < SYMBOL_MIN_CELL ? t("track.layer.zoomHint") : undefined}
              >
                <FrenchKnotIcon size={17} />
              </button>
            </div>
          )}
        </div>

        {!wide && drawerOpen && (
          <div
            className="drawer-backdrop"
            role="presentation"
            onClick={() => setDrawerOpen(false)}
          >
            <div
              className="drawer"
              role="dialog"
              aria-modal="true"
              aria-label={t("track.drawer.title")}
              onClick={(event) => event.stopPropagation()}
            >
              <div
                style={{
                  flex: "none",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 18px 8px",
                }}
              >
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
                  {t("track.drawer.title")}
                </div>
                <button
                  type="button"
                  className="btn btn-icon btn-secondary"
                  onClick={() => setDrawerOpen(false)}
                  aria-label={t("track.close")}
                >
                  <CloseIcon size={18} />
                </button>
              </div>
              <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "0 12px 20px" }}>
                {colorList}
              </div>
            </div>
          </div>
        )}

      </div>

      {wide && (
        <aside className="side-panel">
          <div style={{ flex: "none", padding: "16px 16px 10px" }}>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: 17, marginBottom: 2 }}>
              {t("track.colors")}
            </div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("track.drawer.hint")}
            </div>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "0 10px 14px" }}>
            {colorList}
          </div>
          <div
            className="text-muted"
            style={{
              flex: "none",
              padding: "12px 16px",
              borderTop: "1px solid var(--color-divider)",
              fontSize: 12,
            }}
          >
            {t("track.remainingStitches", {
              count: formatNumber(totals.remaining),
              skeins: totals.skeinsRemaining,
            })}
          </div>
        </aside>
      )}
    </div>
  );
}
