import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { ColorList } from "../components/ColorList";
import {
  BackIcon,
  CloseIcon,
  MinusIcon,
  PanIcon,
  PlusIcon,
  SelectIcon,
  StitchIcon,
  UndoIcon,
} from "../components/Icons";
import { useT } from "../i18n";
import { useElementSize } from "../lib/hooks";
import { useNumberFormat } from "../lib/format";
import { useTheme } from "../lib/theme";
import { SYMBOL_MIN_CELL, drawGrid, drawOverlay, readGridTheme } from "../pattern/render";
import type { CellPosition, Tracker } from "../state/useTracker";

/**
 * Distance, en pixels, au-delà de laquelle un contact est considéré comme un
 * déplacement et non comme un tap.
 *
 * Trop bas, cocher une case déplace la grille par accident ; trop haut, le
 * défilement paraît collant. Cette valeur est réglée pour un doigt, pas pour
 * une souris.
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
  }>({ active: false, panning: false, startX: 0, startY: 0, lastX: 0, lastY: 0, cell: null });

  const { pattern, view, tool, highlight, cursor, selection, totals, counts, version } = tracker;

  // Redessine la grille puis les repères. Les dépendances couvrent tout ce qui
  // peut changer l'image : progression, vue, filtre, thème et taille de boîte.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const theme = readGridTheme(canvas);
    const drawn = drawGrid(canvas, {
      pattern,
      done: tracker.done,
      view,
      theme,
      highlight,
    });
    if (!drawn) return;

    const accent = getComputedStyle(canvas).getPropertyValue("--color-accent").trim();
    drawOverlay(canvas, { view, accent, cursor, selection });
  }, [pattern, tracker.done, version, view, highlight, cursor, selection, resolved, size]);

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

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const cell = cellAt(event);
    event.currentTarget.setPointerCapture(event.pointerId);

    dragRef.current = {
      active: true,
      panning: false,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      cell,
    };

    if (tool === "select") {
      tracker.setSelection({ x0: cell.x, y0: cell.y, x1: cell.x, y1: cell.y });
      tracker.setCursor(cell);
      return;
    }
    if (tool === "stitch") tracker.setCursor(cell);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>): void => {
    const drag = dragRef.current;
    const cell = cellAt(event);

    if (!drag.active) {
      // Survol à la souris : le réticule suit le pointeur. Sans contact tactile
      // en cours, il n'y a rien d'autre à faire.
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

    // Outil « cocher » : un tap coche, un glissé déplace la grille. On ne bascule
    // en déplacement qu'au-delà du seuil, sinon le moindre tremblement de doigt
    // empêcherait de cocher.
    if (!drag.panning) {
      const travelled = Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY);
      if (travelled < DRAG_THRESHOLD) return;
      drag.panning = true;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
    }
    pan();
  };

  const onPointerUp = (): void => {
    const drag = dragRef.current;
    // La case n'est cochée qu'au relâchement : c'est ce qui permet de commencer
    // un glissé depuis n'importe quelle case sans la marquer au passage.
    if (drag.active && !drag.panning && drag.cell !== null && tool === "stitch") {
      tracker.toggleCell(drag.cell);
    }
    dragRef.current = { ...drag, active: false, panning: false, cell: null };
  };

  const activeColor = highlight === 0 ? null : (counts[highlight - 1] ?? null);
  const zoomLabel =
    view.cell >= SYMBOL_MIN_CELL
      ? t("track.zoom.symbols", { size: view.cell })
      : t("track.zoom.blocks", { size: view.cell });

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
                // Sans cela, « Ligne 140 · Colonne 100 » passe sur deux lignes
                // sur un iPhone et fait grossir l'en-tête d'un tiers.
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
                {/* Avec un filtre couleur actif, ces actions ne touchent que
                    cette couleur : c'est le geste « je termine ce fil ici ». */}
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
