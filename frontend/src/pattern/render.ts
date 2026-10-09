/**
 * Grid rendering on `<canvas>`.
 *
 * Non-negotiable project constraint: **never one DOM element per cell**. A
 * reference pattern has 45,900 cells; only the actually visible cells are
 * drawn, which makes a frame's cost proportional to the screen size rather
 * than the pattern size.
 */

import type { Pattern, Progress, SpecialProgress } from "./types";

/** Below this cell size, symbols become unreadable. */
export const SYMBOL_MIN_CELL = 15;
/** Below this size, the grid lines swallow the pattern. */
export const GRIDLINE_MIN_CELL = 7;
/** Zoom bounds, in CSS pixels per cell. */
export const MIN_CELL = 4;
export const MAX_CELL = 34;

/**
 * Overscroll margin allowed beyond a pattern edge, in cells — so an edge cell
 * can be checked/painted without it staying stuck to the edge of the screen,
 * and more generally so the view never locks exactly on the grid's outline.
 * Proportional to the dimension (10%) rather than a fixed number of cells: a
 * small pattern painted by hand (Lot 2) and a 255-cell-wide grid need very
 * different absolute margins to feel comparable — a floor prevents a tiny
 * pattern from having almost no overscroll.
 */
export function panMargin(dimension: number): number {
  return Math.max(6, dimension * 0.1);
}

export interface GridTheme {
  /** Fabric colour, behind unstitched cells. */
  fabric: string;
  /** Application background colour, used to wash out done cells. */
  ground: string;
  /** Ink colour, used for strokes and symbols. */
  ink: string;
}

/** Visible portion of the grid. `x0`/`y0` can be fractional. */
export interface GridView {
  cell: number;
  x0: number;
  y0: number;
}

/**
 * Cache of the real symbols cut out of a PDF (Lot 4, `symbolSvg`), decoded
 * only once then reused for every cell and every render — never reloaded
 * from the SVG string on each frame. Module-level rather than per component:
 * several canvases (Tracking, import brush) often show the same palette, no
 * point decoding the same image twice.
 */
const symbolImageCache = new Map<string, HTMLImageElement>();
const symbolImagePending = new Set<string>();
const symbolImageListeners = new Set<() => void>();

/**
 * Subscribes to a real symbol finishing loading — a component calling
 * `drawGrid` must redraw when it fires, to replace the text fallback
 * (`entry.symbol`) as soon as the image becomes available. Returns an
 * unsubscribe function, for a regular React `useEffect`.
 */
export function onSymbolImageLoaded(listener: () => void): () => void {
  symbolImageListeners.add(listener);
  return () => symbolImageListeners.delete(listener);
}

function getSymbolImage(svg: string): HTMLImageElement | null {
  const cached = symbolImageCache.get(svg);
  if (cached !== undefined) return cached;
  if (!symbolImagePending.has(svg)) {
    symbolImagePending.add(svg);
    const image = new Image();
    image.onload = () => {
      symbolImageCache.set(svg, image);
      symbolImagePending.delete(svg);
      for (const listener of symbolImageListeners) listener();
    };
    image.onerror = () => {
      // Silent fallback to `entry.symbol` — a malformed SVG must never make
      // the cell disappear or break the rendering of the rest.
      symbolImagePending.delete(svg);
    };
    image.src = `data:image/svg+xml;base64,${btoa(svg)}`;
  }
  return null;
}

export interface DrawGridOptions {
  pattern: Pattern;
  done: Progress | null;
  /**
   * Progress of the four special stitch categories (Lot 8) — absent
   * (`null`/`undefined`) for a context that does not track them (import
   * brush): each category is then shown as entirely unchecked, never an
   * error or a missing cell.
   */
  special?: SpecialProgress | null;
  view: GridView;
  theme: GridTheme;
  /** 1-based palette index to highlight; 0 to highlight none. */
  highlight: number;
  gridlines?: boolean;
  /** Hides already stitched cells (bare fabric) rather than washing them out. */
  hideDone?: boolean;
  /**
   * Indices of cells (same indices as `pattern.cells`) flagged uncertain by
   * type B/C automatic detection (Lot 5, `uncertain_cells`) — doubtful colour
   * and/or ambiguous symbol. A visual marker in the import wizard
   * (`ImportGridPainter`) only, never used in Tracking.
   */
  uncertainCells?: ReadonlySet<number> | null;
  /** Colour of the uncertainty marker — read from `--color-accent` by the
   * caller, like `drawOverlay`, rather than derived from `theme`. */
  uncertainColor?: string;
}

/**
 * Reads the theme colours from the CSS variables.
 *
 * Avoids duplicating the theme palette in JavaScript: `index.css` remains the
 * single source of truth, and a theme change is enough to change rendering.
 */
export function readGridTheme(element: Element): GridTheme {
  const styles = getComputedStyle(element);
  const read = (name: string, fallback: string): string => {
    const value = styles.getPropertyValue(name).trim();
    return value === "" ? fallback : value;
  };
  return {
    fabric: read("--canvas-fabric", "#efe3cd"),
    ground: read("--canvas-ground", "#f5ead8"),
    ink: read("--canvas-ink", "#201e1d"),
  };
}

function parseHex(hex: string): [number, number, number] {
  const clean = hex.trim().replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean;
  return [
    Number.parseInt(full.slice(0, 2), 16) || 0,
    Number.parseInt(full.slice(2, 4), 16) || 0,
    Number.parseInt(full.slice(4, 6), 16) || 0,
  ];
}

/** Mixes two hexadecimal colours. `amount` goes from 0 (a) to 1 (b). */
export function mix(a: string, b: string, amount: number): string {
  const left = parseHex(a);
  const right = parseHex(b);
  const channel = (index: 0 | 1 | 2): string =>
    Math.round(left[index] + (right[index] - left[index]) * amount)
      .toString(16)
      .padStart(2, "0");
  return `#${channel(0)}${channel(1)}${channel(2)}`;
}

/**
 * Adjusts the canvas's internal resolution to the screen density.
 *
 * Without this, the grid is blurry on every Apple device. The ratio is capped
 * at 2: beyond that, the number of pixels to paint quadruples for an
 * invisible gain, and scrolling stutters on large patterns.
 */
function prepareCanvas(canvas: HTMLCanvasElement): {
  context: CanvasRenderingContext2D;
  width: number;
  height: number;
} | null {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (width === 0 || height === 0) return null;

  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(width * ratio);
  const pixelHeight = Math.round(height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }

  const context = canvas.getContext("2d");
  if (context === null) return null;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

/**
 * 1/2 stitch (Lot 8): a triangle taking half of the cell, diagonal — a
 * single orientation (top-left corner) for lack of real direction
 * information in the data model (§6.3: one value per cell, not a stitch
 * direction), a simplification already settled in Lot 8.
 */
function fillHalfTriangle(
  g: CanvasRenderingContext2D,
  px: number,
  py: number,
  cell: number,
  fillStyle: string,
): void {
  g.fillStyle = fillStyle;
  g.beginPath();
  g.moveTo(px, py);
  g.lineTo(px + cell, py);
  g.lineTo(px, py + cell);
  g.closePath();
  g.fill();
}

/** 1/4 stitch (Lot 8): a triangle smaller than a 1/2 stitch, same corner. */
function fillQuarterTriangle(
  g: CanvasRenderingContext2D,
  px: number,
  py: number,
  cell: number,
  fillStyle: string,
): void {
  g.fillStyle = fillStyle;
  g.beginPath();
  g.moveTo(px, py);
  g.lineTo(px + cell / 2, py);
  g.lineTo(px, py + cell / 2);
  g.closePath();
  g.fill();
}

export function drawGrid(canvas: HTMLCanvasElement, options: DrawGridOptions): boolean {
  const prepared = prepareCanvas(canvas);
  if (prepared === null) return false;

  const { context: g, width: viewWidth, height: viewHeight } = prepared;
  const { pattern, done, view, theme, highlight, special = null } = options;
  const { cell, x0, y0 } = view;

  g.clearRect(0, 0, viewWidth, viewHeight);
  g.fillStyle = theme.fabric;
  g.fillRect(0, 0, viewWidth, viewHeight);

  const columns = Math.ceil(viewWidth / cell) + 1;
  const rows = Math.ceil(viewHeight / cell) + 1;
  const withSymbols = cell >= SYMBOL_MIN_CELL;

  if (withSymbols) {
    g.font = `${Math.round(cell * 0.62)}px ${getComputedStyle(canvas).fontFamily}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
  }

  const firstColumn = Math.floor(x0);
  const firstRow = Math.floor(y0);

  for (let row = 0; row < rows; row++) {
    const y = firstRow + row;
    if (y < 0 || y >= pattern.height) continue;
    for (let column = 0; column < columns; column++) {
      const x = firstColumn + column;
      if (x < 0 || x >= pattern.width) continue;

      const index = y * pattern.width + x;
      const value = pattern.cells[index] ?? 0;
      const halfValue = pattern.cellsHalf[index] ?? 0;
      const quarterValue = pattern.cellsQuarter[index] ?? 0;
      if (value === 0 && halfValue === 0 && quarterValue === 0) continue;

      const px = (x - x0) * cell;
      const py = (y - y0) * cell;

      if (value !== 0) {
        const entry = pattern.palette[value - 1];
        if (entry !== undefined) {
          const isDone = done !== null && done[index] === 1;
          // Hidden cell: leave it as bare fabric, exactly like an empty
          // pattern cell — this is what makes already stitched work visually
          // disappear rather than just washing it out.
          if (!(isDone && options.hideDone === true)) {
            const dimmed = highlight !== 0 && highlight !== value;

            g.globalAlpha = dimmed ? 0.14 : 1;
            // A done cell stays recognisable by its colour, but washed out:
            // that is what shows at a glance what is left to stitch.
            g.fillStyle = isDone ? mix(entry.hex, theme.ground, 0.62) : entry.hex;
            g.fillRect(px, py, cell + 0.5, cell + 0.5);

            if (isDone && cell >= 6) {
              g.strokeStyle = mix(entry.hex, theme.ink, 0.35);
              g.lineWidth = Math.max(1, cell * 0.11);
              g.beginPath();
              g.moveTo(px + cell * 0.22, py + cell * 0.22);
              g.lineTo(px + cell * 0.78, py + cell * 0.78);
              g.moveTo(px + cell * 0.78, py + cell * 0.22);
              g.lineTo(px + cell * 0.22, py + cell * 0.78);
              g.stroke();
            } else if (withSymbols) {
              const image = entry.symbolSvg !== undefined ? getSymbolImage(entry.symbolSvg) : null;
              if (image !== null) {
                const size = cell * 0.7;
                const inset = (cell - size) / 2;
                g.drawImage(image, px + inset, py + inset, size, size);
              } else {
                g.fillStyle = mix(entry.hex, theme.ink, 0.72);
                g.fillText(entry.symbol, px + cell / 2, py + cell * 0.54);
              }
            }
            g.globalAlpha = 1;

            if (!isDone && cell >= 6 && options.uncertainCells?.has(index) === true) {
              // Small solid triangle in the corner — an uncertainty marker
              // must stay visible even on a tiny cell, unlike the symbol
              // (`withSymbols`), which becomes unreadable below
              // `SYMBOL_MIN_CELL` and disappears entirely at that zoom.
              const size = Math.max(4, cell * 0.36);
              g.fillStyle = options.uncertainColor ?? theme.ink;
              g.beginPath();
              g.moveTo(px + cell - size, py);
              g.lineTo(px + cell, py);
              g.lineTo(px + cell, py + size);
              g.closePath();
              g.fill();
            }
          }
        }
      }

      // 1/2 and 1/4 stitches (Lot 8): layers independent of the full stitch
      // above, a cell can carry one, the other, both, or neither — see
      // `Pattern.cellsHalf`/`cellsQuarter`.
      if (halfValue !== 0) {
        const entry = pattern.palette[halfValue - 1];
        if (entry !== undefined) {
          const isDone = special !== null && special.half[index] === 1;
          if (!(isDone && options.hideDone === true)) {
            g.globalAlpha = highlight !== 0 && highlight !== halfValue ? 0.14 : 1;
            fillHalfTriangle(
              g,
              px,
              py,
              cell,
              isDone ? mix(entry.hex, theme.ground, 0.62) : entry.hex,
            );
            g.globalAlpha = 1;
          }
        }
      }

      if (quarterValue !== 0) {
        const entry = pattern.palette[quarterValue - 1];
        if (entry !== undefined) {
          const isDone = special !== null && special.quarter[index] === 1;
          if (!(isDone && options.hideDone === true)) {
            g.globalAlpha = highlight !== 0 && highlight !== quarterValue ? 0.14 : 1;
            fillQuarterTriangle(
              g,
              px,
              py,
              cell,
              isDone ? mix(entry.hex, theme.ground, 0.62) : entry.hex,
            );
            g.globalAlpha = 1;
          }
        }
      }
    }
  }

  // Backstitch and knots (Lot 8): rendered at every zoom level, unlike
  // symbols (`withSymbols`) — on a real paper diagram, these strokes stay
  // visible even on an overview of the grid, and a stitcher expects the same
  // here (direct feedback after real use). `lineWidth`/`radius` below have a
  // pixel floor (never proportional to `cell` alone) so they stay visible
  // even when zoomed far out. Checking a segment/knot remains reserved for
  // close zoom (`useTracker.ts`, same `SYMBOL_MIN_CELL` threshold): seeing it
  // does not imply being able to precisely target a cell a few pixels wide
  // with a finger. Linear scan of the whole list with coarse culling to the
  // view (as before): negligible even for a real pattern with several
  // hundred of them (Lot 9), see `pattern/specialHitTest.ts` for the same
  // limit on the interaction side.
  if (pattern.backstitch.length > 0) {
    const specialDone = special?.backstitch ?? null;
    g.lineCap = "round";
    for (let i = 0; i < pattern.backstitch.length; i++) {
      const segment = pattern.backstitch[i];
      if (segment === undefined) continue;
      const minX = Math.min(segment.x1, segment.x2);
      const maxX = Math.max(segment.x1, segment.x2);
      const minY = Math.min(segment.y1, segment.y2);
      const maxY = Math.max(segment.y1, segment.y2);
      if (maxX < firstColumn || minX > firstColumn + columns) continue;
      if (maxY < firstRow || minY > firstRow + rows) continue;

      const entry = pattern.palette[segment.paletteIndex - 1];
      if (entry === undefined) continue;
      const isDone = specialDone !== null && specialDone[i] === 1;
      if (isDone && options.hideDone === true) continue;

      g.strokeStyle = isDone ? mix(entry.hex, theme.ground, 0.62) : mix(entry.hex, theme.ink, 0.2);
      g.lineWidth = Math.max(1.4, cell * 0.14);
      g.beginPath();
      g.moveTo((segment.x1 - x0) * cell, (segment.y1 - y0) * cell);
      g.lineTo((segment.x2 - x0) * cell, (segment.y2 - y0) * cell);
      g.stroke();
    }
  }

  if (pattern.frenchKnots.length > 0) {
    const specialDone = special?.knot ?? null;
    for (let i = 0; i < pattern.frenchKnots.length; i++) {
      const knot = pattern.frenchKnots[i];
      if (knot === undefined) continue;
      if (knot.x < firstColumn || knot.x > firstColumn + columns) continue;
      if (knot.y < firstRow || knot.y > firstRow + rows) continue;

      const entry = pattern.palette[knot.paletteIndex - 1];
      if (entry === undefined) continue;
      const isDone = specialDone !== null && specialDone[i] === 1;
      if (isDone && options.hideDone === true) continue;

      const px = (knot.x - x0) * cell;
      const py = (knot.y - y0) * cell;
      const radius = Math.max(1.6, cell * 0.24);
      g.fillStyle = isDone ? mix(entry.hex, theme.ground, 0.62) : mix(entry.hex, theme.ink, 0.12);
      g.beginPath();
      g.arc(px, py, radius, 0, Math.PI * 2);
      g.fill();
    }
  }

  if (options.gridlines !== false && cell >= GRIDLINE_MIN_CELL) {
    g.strokeStyle = mix(theme.ground, theme.ink, 0.18);
    g.lineWidth = 1;
    g.beginPath();
    for (let x = firstColumn; x <= x0 + columns; x++) {
      const px = Math.round((x - x0) * cell) + 0.5;
      g.moveTo(px, 0);
      g.lineTo(px, viewHeight);
    }
    for (let y = firstRow; y <= y0 + rows; y++) {
      const py = Math.round((y - y0) * cell) + 0.5;
      g.moveTo(0, py);
      g.lineTo(viewWidth, py);
    }
    g.stroke();

    // Major lines every 10 cells: that is how stitches are counted on a
    // paper chart, and without them you get lost immediately.
    g.strokeStyle = mix(theme.ground, theme.ink, 0.55);
    g.lineWidth = 1.6;
    g.beginPath();
    for (let x = firstColumn; x <= x0 + columns; x++) {
      if (x % 10 !== 0) continue;
      const px = Math.round((x - x0) * cell) + 0.5;
      g.moveTo(px, 0);
      g.lineTo(px, viewHeight);
    }
    for (let y = firstRow; y <= y0 + rows; y++) {
      if (y % 10 !== 0) continue;
      const py = Math.round((y - y0) * cell) + 0.5;
      g.moveTo(0, py);
      g.lineTo(viewWidth, py);
    }
    g.stroke();
  }

  return true;
}

export interface OverlayOptions {
  view: GridView;
  accent: string;
  cursor: { x: number; y: number } | null;
  selection: { x0: number; y0: number; x1: number; y1: number } | null;
}

/** Position and selection markers, drawn on top of the grid. */
export function drawOverlay(canvas: HTMLCanvasElement, options: OverlayOptions): void {
  const g = canvas.getContext("2d");
  if (g === null) return;

  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const { cell, x0, y0 } = options.view;

  if (options.cursor !== null) {
    const px = (options.cursor.x - x0) * cell;
    const py = (options.cursor.y - y0) * cell;
    g.strokeStyle = options.accent;
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(0, py + cell / 2);
    g.lineTo(width, py + cell / 2);
    g.moveTo(px + cell / 2, 0);
    g.lineTo(px + cell / 2, height);
    g.globalAlpha = 0.35;
    g.stroke();
    g.globalAlpha = 1;
    g.strokeRect(px - 1, py - 1, cell + 2, cell + 2);
  }

  const selection = options.selection;
  if (selection !== null) {
    const x = (Math.min(selection.x0, selection.x1) - x0) * cell;
    const y = (Math.min(selection.y0, selection.y1) - y0) * cell;
    const w = (Math.abs(selection.x1 - selection.x0) + 1) * cell;
    const h = (Math.abs(selection.y1 - selection.y0) + 1) * cell;
    g.fillStyle = options.accent;
    g.globalAlpha = 0.13;
    g.fillRect(x, y, w, h);
    g.globalAlpha = 1;
    g.strokeStyle = options.accent;
    g.lineWidth = 2;
    g.setLineDash([6, 4]);
    g.strokeRect(x, y, w, h);
    g.setLineDash([]);
  }
}

/** Thumbnail: the whole pattern fitted to the canvas, without symbols or grid lines. */
export function drawThumbnail(
  canvas: HTMLCanvasElement,
  pattern: Pattern,
  done: Progress | null,
  theme: GridTheme,
): boolean {
  const prepared = prepareCanvas(canvas);
  if (prepared === null) return false;

  const { context: g, width, height } = prepared;
  g.fillStyle = theme.fabric;
  g.fillRect(0, 0, width, height);

  const cell = Math.min(width / pattern.width, height / pattern.height);
  const offsetX = (width - cell * pattern.width) / 2;
  const offsetY = (height - cell * pattern.height) / 2;

  for (let y = 0; y < pattern.height; y++) {
    for (let x = 0; x < pattern.width; x++) {
      const index = y * pattern.width + x;
      const value = pattern.cells[index] ?? 0;
      if (value === 0) continue;
      const entry = pattern.palette[value - 1];
      if (entry === undefined) continue;
      g.fillStyle =
        done !== null && done[index] === 1
          ? mix(entry.hex, theme.ground, 0.45)
          : entry.hex;
      g.fillRect(offsetX + x * cell, offsetY + y * cell, cell + 0.6, cell + 0.6);
    }
  }
  return true;
}
