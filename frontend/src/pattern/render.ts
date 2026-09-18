/**
 * Rendu de grille sur `<canvas>`.
 *
 * Contrainte non négociable du projet : **jamais un élément DOM par case**.
 * Un motif de référence fait 45 900 cases ; seules les cases réellement
 * visibles sont dessinées, ce qui rend le coût d'une image proportionnel à la
 * taille de l'écran et non à celle du motif.
 */

import type { Pattern, Progress, SpecialProgress } from "./types";

/** En dessous de cette taille de case, les symboles deviennent illisibles. */
export const SYMBOL_MIN_CELL = 15;
/** En dessous de cette taille, le quadrillage mange le motif. */
export const GRIDLINE_MIN_CELL = 7;
/** Bornes de zoom, en pixels CSS par case. */
export const MIN_CELL = 4;
export const MAX_CELL = 34;

/**
 * Marge de débord autorisée au-delà d'un bord du motif, en cases — pour
 * qu'on puisse cocher/peindre une case de bord sans qu'elle ne reste collée
 * à l'arête de l'écran, et plus généralement pour que la vue ne se bloque
 * jamais pile sur le contour de la grille. Proportionnelle à la dimension
 * (10 %) plutôt qu'un nombre de cases fixe : un petit motif peint à la main
 * (Lot 2) et une grille de 255 cases de large ont besoin d'une marge très
 * différente en valeur absolue pour paraître comparable — un plancher évite
 * qu'un tout petit motif n'ait presque aucun débord.
 */
export function panMargin(dimension: number): number {
  return Math.max(6, dimension * 0.1);
}

export interface GridTheme {
  /** Couleur de la toile, derrière les cases non brodées. */
  fabric: string;
  /** Couleur de fond de l'application, utilisée pour délaver les cases faites. */
  ground: string;
  /** Couleur d'encre, utilisée pour les traits et les symboles. */
  ink: string;
}

/** Portion visible de la grille. `x0`/`y0` peuvent être fractionnaires. */
export interface GridView {
  cell: number;
  x0: number;
  y0: number;
}

/**
 * Cache des symboles réels découpés depuis un PDF (Lot 4, `symbolSvg`),
 * décodés une seule fois puis réutilisés à chaque case et à chaque rendu —
 * jamais rechargés depuis la chaîne SVG à chaque frame. Module-level plutôt
 * que par composant : plusieurs canvas (Suivi, pinceau d'import) affichent
 * souvent la même palette, inutile de décoder deux fois la même image.
 */
const symbolImageCache = new Map<string, HTMLImageElement>();
const symbolImagePending = new Set<string>();
const symbolImageListeners = new Set<() => void>();

/**
 * S'abonne au chargement d'un symbole réel — un composant appelant `drawGrid`
 * doit redessiner quand celui-ci se déclenche, pour remplacer le repli
 * textuel (`entry.symbol`) dès que l'image devient disponible. Renvoie une
 * fonction de désabonnement, pour un `useEffect` React classique.
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
      // Repli silencieux sur `entry.symbol` — un SVG mal formé ne doit
      // jamais faire disparaître la case ni casser le rendu du reste.
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
   * Progression des quatre catégories de points spéciaux (Lot 8) — absente
   * (`null`/`undefined`) pour un contexte qui n'en suit pas (pinceau
   * d'import) : chaque catégorie s'affiche alors comme entièrement non
   * cochée, jamais une erreur ni une case manquante.
   */
  special?: SpecialProgress | null;
  view: GridView;
  theme: GridTheme;
  /** Index de palette 1-based à mettre en avant ; 0 pour n'en surligner aucun. */
  highlight: number;
  gridlines?: boolean;
  /** Masque les cases déjà brodées (toile nue) plutôt que de les délaver. */
  hideDone?: boolean;
  /**
   * Index de cases (mêmes indices que `pattern.cells`) signalées incertaines
   * par la détection automatique type B/C (Lot 5, `uncertain_cells`) —
   * couleur douteuse et/ou symbole ambigu. Repère visuel dans l'assistant
   * d'import (`ImportGridPainter`) uniquement, jamais utilisé côté Suivi.
   */
  uncertainCells?: ReadonlySet<number> | null;
  /** Couleur du repère d'incertitude — lue depuis `--color-accent` par
   * l'appelant, comme `drawOverlay`, plutôt que dérivée de `theme`. */
  uncertainColor?: string;
}

/**
 * Lit les couleurs du thème depuis les variables CSS.
 *
 * Évite de dupliquer la palette du thème en JavaScript : `index.css` reste la
 * seule source de vérité, et un changement de thème suffit à changer le rendu.
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

/** Mélange deux couleurs hexadécimales. `amount` va de 0 (a) à 1 (b). */
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
 * Ajuste la résolution interne du canvas à la densité de l'écran.
 *
 * Sans cela, la grille est floue sur tous les appareils Apple. Le ratio est
 * plafonné à 2 : au-delà, on quadruple le nombre de pixels à peindre pour un
 * gain invisible, et le défilement décroche sur les grands motifs.
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
 * Point 1/2 (Lot 8) : triangle occupant la moitié de la case, diagonale —
 * une seule orientation (coin haut-gauche) faute d'information de direction
 * réelle dans le modèle de données (§6.3 : une valeur par case, pas un sens
 * de point), simplification déjà actée au Lot 8.
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

/** Point 1/4 (Lot 8) : un triangle plus petit qu'un point 1/2, même coin. */
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
          // Case masquée : on la laisse en toile nue, exactement comme une
          // case vide du motif — c'est ce qui fait disparaître visuellement
          // ce qui est déjà brodé plutôt que de simplement le délaver.
          if (!(isDone && options.hideDone === true)) {
            const dimmed = highlight !== 0 && highlight !== value;

            g.globalAlpha = dimmed ? 0.14 : 1;
            // Une case faite reste reconnaissable à sa couleur, mais délavée :
            // c'est ce qui permet de voir d'un coup d'œil ce qu'il reste à
            // broder.
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
              // Petit triangle plein dans le coin — un repère d'incertitude
              // doit rester visible même sur une case minuscule, contrairement
              // au symbole (`withSymbols`) qui, lui, devient illisible en
              // dessous de `SYMBOL_MIN_CELL` et disparaît entièrement à ce
              // zoom.
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

      // Points 1/2 et 1/4 (Lot 8) : couches indépendantes du point entier
      // ci-dessus, une case peut en porter une, l'autre, les deux, ou aucune
      // — voir `Pattern.cellsHalf`/`cellsQuarter`.
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

  // Point arrière et nœuds (Lot 8) : rendus seulement au niveau de détail le
  // plus rapproché (`withSymbols`), comme les symboles — en dessous, un
  // trait ou un point de quelques pixels n'apporterait rien et coûterait un
  // balayage de la liste complète à chaque frame pour un motif réel qui peut
  // en compter plusieurs centaines (Lot 9 à venir). Balayage linéaire avec
  // recadrage grossier sur la vue : suffisant tant que ces listes restent de
  // cette taille, voir `pattern/specialHitTest.ts` pour la même limite côté
  // interaction.
  if (withSymbols && pattern.backstitch.length > 0) {
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

  if (withSymbols && pattern.frenchKnots.length > 0) {
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

    // Lignes maîtresses toutes les 10 cases : c'est ainsi qu'on compte les
    // points sur une grille papier, et sans elles on se perd immédiatement.
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

/** Repères de position et de sélection, dessinés par-dessus la grille. */
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

/** Vignette : le motif entier ajusté au canvas, sans symbole ni quadrillage. */
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
