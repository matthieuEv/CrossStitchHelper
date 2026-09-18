/**
 * État de l'écran de suivi : progression, vue, outil courant.
 *
 * Choix de performance : chaque catégorie de point (`full`/`half`/`quarter`/
 * `backstitch`/`knot`, Lot 8) est un `Uint8Array` muté sur place, regroupées
 * dans une seule structure (`doneRef.current`) plutôt que cinq refs
 * séparées — un seul objet à faire transiter dans l'historique d'annulation
 * et dans `applyRemote`. Un compteur de version déclenche le rendu React ;
 * recopier un tableau à chaque case cochée coûterait une allocation de 45 Ko
 * par tap sur le motif de référence — invisible sur un ordinateur, sensible
 * sur un iPhone.
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

/** Un point de contact en coordonnées de grille fractionnaires (pas encore
 * arrondi à une case) — nécessaire pour viser un segment de point arrière ou
 * un nœud, qui ne sont pas alignés sur la grille de cases. */
export interface GridPoint {
  gx: number;
  gy: number;
}

/** Profondeur de la pile d'annulation. */
const HISTORY_LIMIT = 16;

/**
 * Tolérance de tap pour le point arrière/les nœuds, en pixels d'écran —
 * convertie en cases au moment du tap (voir `toggleAtPoint`) pour rester
 * constante à l'œil quel que soit le zoom, plafonnée à une demi-case pour ne
 * jamais capter un élément visiblement distant.
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
  /** Progression des quatre catégories de points spéciaux (Lot 8) — voir
   * `SpecialProgress`. Toujours en phase avec `version` : incrémenté par la
   * même contrepasse que `done`. */
  special: SpecialProgress;
  /**
   * Incrémenté à chaque modification de `done` ou `special`.
   *
   * `done`/`special` étant mutés sur place, c'est cette valeur — et non les
   * tableaux — qui doit figurer dans les dépendances d'un `useEffect` de
   * rendu.
   */
  version: number;
  counts: ColorCount[];
  totals: PatternTotals;

  view: GridView;
  setOffset: (x0: number, y0: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  /**
   * Zoome vers une taille de case cible en gardant un point de l'écran ancré
   * sur la même case du motif (voir l'implémentation pour le détail du calcul).
   * Utilisé par le pincement à deux doigts : le point médian du geste doit
   * rester sous les doigts, pas sauter vers le coin de l'écran.
   */
  zoomTo: (
    nextCell: number,
    anchorScreenX: number,
    anchorScreenY: number,
    canvasRect: Pick<DOMRect, "left" | "top">,
    /** Déplacement additionnel à appliquer dans le même geste, en cases du
     * motif — un glissé diagonal au trackpad zoome et déplace la vue à la
     * fois (voir TrackScreen.tsx) : sans ça, l'appel à `setOffset` séparé
     * pour le déplacement serait aussitôt écrasé par celui, interne à
     * `zoomTo`, qui recalcule l'origine depuis la position d'avant le geste. */
    panDeltaX?: number,
  ) => void;

  tool: Tool;
  setTool: (tool: Tool) => void;

  /** Catégorie de point ciblée par l'outil « cocher » (Lot 8) — sans effet
   * sur les outils « déplacer »/« sélectionner ». `backstitch`/`knot` ne
   * sont interactifs qu'à partir de `SYMBOL_MIN_CELL` (voir `toggleAtPoint`),
   * même seuil que l'apparition des symboles : en dessous, une case fait
   * quelques pixels et deux éléments voisins seraient impossibles à
   * distinguer au doigt. */
  activeLayer: StitchLayer;
  setActiveLayer: (layer: StitchLayer) => void;

  /** Index de palette 1-based mis en avant ; 0 = aucun filtre. */
  highlight: number;
  toggleHighlight: (index: number) => void;
  clearHighlight: () => void;

  /** Masque les cases déjà brodées plutôt que de les délaver. */
  hideDone: boolean;
  toggleHideDone: () => void;

  cursor: CellPosition | null;
  setCursor: (cursor: CellPosition | null) => void;

  selection: Selection | null;
  setSelection: (selection: Selection | null) => void;

  /** Coche/décoche une case de la grille en point entier — indépendant de
   * `activeLayer`, conservé pour les appelants qui visent explicitement le
   * point entier (voir `fillSelection`, inchangé depuis le Lot 1). */
  toggleCell: (cell: CellPosition) => void;
  /**
   * Coche/décoche l'élément ciblé par un point de contact, selon
   * `activeLayer` : une case pour `full`/`half`/`quarter` (arrondie vers le
   * bas), le segment de point arrière ou le nœud le plus proche pour
   * `backstitch`/`knot` (sans effet si rien d'assez proche, ou en dessous du
   * seuil de zoom d'interaction).
   */
  toggleAtPoint: (point: GridPoint) => void;
  fillSelection: (value: 0 | 1) => void;
  undo: () => void;
  canUndo: boolean;

  /**
   * Applique des changements venus d'ailleurs (synchronisation serveur,
   * Lot 1) : met à jour `done`/`special` et déclenche un rendu, mais sans
   * repasser par `onChange` (ce ne sont pas de nouvelles intentions locales à
   * resynchroniser) ni par la pile d'annulation (annuler ne doit défaire que
   * les propres gestes de cet appareil).
   */
  applyRemote: (changes: CellChange[]) => void;
}

export interface CellChange {
  layer: StitchLayer;
  index: number;
  stitched: 0 | 1;
}

/**
 * `onChange` est appelé de façon synchrone avec les éléments réellement
 * modifiés (jamais un tableau complet) : c'est ce qui permet à un appelant
 * (la synchronisation serveur, Lot 1) d'envoyer des deltas précis sans avoir
 * à comparer deux copies de 45 Ko à chaque case cochée.
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

  // Ref plutôt que dépendance directe : `onChange` peut changer d'identité à
  // chaque rendu côté appelant sans que cela invalide les callbacks mémoïsés
  // ci-dessous.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const [cell, setCell] = useState(16);
  // Position de départ pensée pour un grand motif (s'écarter du coin pour ne
  // pas coller la vue au bord) ; sans le même bornage que `setOffset`
  // ci-dessous, un petit motif peint à la main (Lot 2) s'ouvrirait sur une
  // vue entièrement vide, en dehors de sa grille.
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
    // `version` est la dépendance réelle : `done` est muté sur place.
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
      // Une case vide du motif n'est pas brodable : la cocher n'aurait aucun
      // sens et fausserait les compteurs.
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

  /** Comme `toggleCell`, pour les couches 1/2 et 1/4 — une case sans point de
   * cette catégorie (voir `Pattern.cellsHalf`/`cellsQuarter`) est ignorée. */
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

  /** Coche/décoche un segment de point arrière ou un nœud, par index dans
   * `Pattern.backstitch`/`frenchKnots` — jamais un index de grille. */
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

      // Point arrière / nœud : la cible est le segment ou le point le plus
      // proche du contact, pas une case — coupé en dessous de
      // `SYMBOL_MIN_CELL` (même seuil que l'apparition des symboles) : à ce
      // zoom, une case fait quelques pixels et deux éléments voisins
      // deviendraient impossibles à distinguer au doigt.
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
          // Avec un filtre actif, on ne remplit que la couleur filtrée : c'est
          // le geste « termine cette couleur dans la zone visible ».
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
    // On réécrit dans les mêmes tableaux plutôt que d'en changer la
    // référence : la bibliothèque et les statistiques pointent dessus et
    // doivent continuer à voir la progression réelle après une annulation.
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
      // Case du motif actuellement sous le point d'ancrage (le point médian du
      // pincement), avant que la taille de case ne change.
      const anchorCellX = offset.x0 + (anchorScreenX - canvasRect.left) / cell;
      const anchorCellY = offset.y0 + (anchorScreenY - canvasRect.top) / cell;
      setCell(clampedCell);
      // On replace l'origine de la vue pour que cette même case du motif se
      // retrouve toujours sous le point d'ancrage une fois la taille changée —
      // c'est ce qui fait « zoomer sous les doigts » plutôt que vers un coin —
      // puis on ajoute le déplacement du même geste, plutôt qu'un `setOffset`
      // séparé qui se ferait écraser par ce calcul.
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
