/**
 * État de l'écran de suivi : progression, vue, outil courant.
 *
 * Choix de performance : `done` est un `Uint8Array` muté sur place, et un
 * compteur de version déclenche le rendu React. Recopier le tableau à chaque
 * case cochée coûterait une allocation de 45 Ko par tap sur le motif de
 * référence — invisible sur un ordinateur, sensible sur un iPhone.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { countByColor, summarise, type ColorCount, type PatternTotals } from "../pattern/counts";
import { MAX_CELL, MIN_CELL, type GridView } from "../pattern/render";
import type { Pattern, Progress } from "../pattern/types";

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

/** Profondeur de la pile d'annulation. */
const HISTORY_LIMIT = 16;

export interface Tracker {
  pattern: Pattern;
  done: Progress;
  /**
   * Incrémenté à chaque modification de `done`.
   *
   * `done` étant muté sur place, c'est cette valeur — et non le tableau — qui
   * doit figurer dans les dépendances d'un `useEffect` de rendu.
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
  ) => void;

  tool: Tool;
  setTool: (tool: Tool) => void;

  /** Index de palette 1-based mis en avant ; 0 = aucun filtre. */
  highlight: number;
  toggleHighlight: (index: number) => void;
  clearHighlight: () => void;

  cursor: CellPosition | null;
  setCursor: (cursor: CellPosition | null) => void;

  selection: Selection | null;
  setSelection: (selection: Selection | null) => void;

  toggleCell: (cell: CellPosition) => void;
  fillSelection: (value: 0 | 1) => void;
  undo: () => void;
  canUndo: boolean;

  /**
   * Applique des changements venus d'ailleurs (synchronisation serveur,
   * Lot 1) : met à jour `done` et déclenche un rendu, mais sans repasser par
   * `onChange` (ce ne sont pas de nouvelles intentions locales à
   * resynchroniser) ni par la pile d'annulation (annuler ne doit défaire que
   * les propres gestes de cet appareil).
   */
  applyRemote: (changes: CellChange[]) => void;
}

export interface CellChange {
  index: number;
  stitched: 0 | 1;
}

/**
 * `onChange` est appelé de façon synchrone avec les cases réellement
 * modifiées (jamais un tableau complet) : c'est ce qui permet à un appelant
 * (la synchronisation serveur, Lot 1) d'envoyer des deltas précis sans avoir
 * à comparer deux copies de 45 Ko à chaque case cochée.
 */
export function useTracker(
  pattern: Pattern,
  initialProgress: Progress,
  onChange?: (changes: CellChange[]) => void,
): Tracker {
  const doneRef = useRef<Progress>(initialProgress);
  const historyRef = useRef<Progress[]>([]);
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
    x0: Math.max(-6, Math.min(pattern.width - 4, 30)),
    y0: Math.max(-6, Math.min(pattern.height - 4, 24)),
  }));
  const [tool, setTool] = useState<Tool>("stitch");
  const [highlight, setHighlight] = useState(0);
  const [cursor, setCursor] = useState<CellPosition | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const done = doneRef.current;

  const counts = useMemo(
    () => countByColor(pattern, done),
    // `version` est la dépendance réelle : `done` est muté sur place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pattern, version],
  );
  const totals = useMemo(() => summarise(counts), [counts]);

  const snapshot = useCallback(() => {
    historyRef.current.push(doneRef.current.slice());
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
      const next = doneRef.current[index] === 1 ? 0 : 1;
      doneRef.current[index] = next;
      setVersion((value) => value + 1);
      onChangeRef.current?.([{ index, stitched: next }]);
    },
    [pattern, snapshot],
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
      for (let y = minY; y <= maxY; y++) {
        for (let x = minX; x <= maxX; x++) {
          const index = y * pattern.width + x;
          const colour = pattern.cells[index] ?? 0;
          if (colour === 0) continue;
          // Avec un filtre actif, on ne remplit que la couleur filtrée : c'est
          // le geste « termine cette couleur dans la zone visible ».
          if (highlight !== 0 && colour !== highlight) continue;
          if (doneRef.current[index] === value) continue;
          doneRef.current[index] = value;
          changes.push({ index, stitched: value });
        }
      }
      setVersion((current) => current + 1);
      if (changes.length > 0) onChangeRef.current?.(changes);
    },
    [selection, pattern, highlight, snapshot],
  );

  const undo = useCallback(() => {
    const previous = historyRef.current.pop();
    if (previous === undefined) return;
    // On réécrit dans le même tableau plutôt que d'en changer la référence :
    // la bibliothèque et les statistiques pointent dessus et doivent continuer
    // à voir la progression réelle après une annulation.
    const changes: CellChange[] = [];
    if (onChangeRef.current !== undefined) {
      for (let index = 0; index < previous.length; index++) {
        const value = previous[index] as 0 | 1;
        if (doneRef.current[index] !== value) changes.push({ index, stitched: value });
      }
    }
    doneRef.current.set(previous);
    setVersion((value) => value + 1);
    if (changes.length > 0) onChangeRef.current?.(changes);
  }, []);

  const applyRemote = useCallback((changes: CellChange[]) => {
    if (changes.length === 0) return;
    for (const change of changes) {
      doneRef.current[change.index] = change.stitched;
    }
    setVersion((value) => value + 1);
  }, []);

  const setOffset = useCallback(
    (x0: number, y0: number) => {
      // On autorise un léger débord pour pouvoir cocher les cases de bord
      // sans les coller à l'arête de l'écran.
      setOffsetState({
        x0: Math.max(-6, Math.min(pattern.width - 4, x0)),
        y0: Math.max(-6, Math.min(pattern.height - 4, y0)),
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
    ) => {
      const clampedCell = Math.max(MIN_CELL, Math.min(MAX_CELL, nextCell));
      // Case du motif actuellement sous le point d'ancrage (le point médian du
      // pincement), avant que la taille de case ne change.
      const anchorCellX = offset.x0 + (anchorScreenX - canvasRect.left) / cell;
      const anchorCellY = offset.y0 + (anchorScreenY - canvasRect.top) / cell;
      setCell(clampedCell);
      // On replace l'origine de la vue pour que cette même case du motif se
      // retrouve toujours sous le point d'ancrage une fois la taille changée —
      // c'est ce qui fait « zoomer sous les doigts » plutôt que vers un coin.
      setOffset(
        anchorCellX - (anchorScreenX - canvasRect.left) / clampedCell,
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

  const view: GridView = { cell, x0: offset.x0, y0: offset.y0 };

  return {
    pattern,
    done,
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
    highlight,
    toggleHighlight,
    clearHighlight,
    cursor,
    setCursor,
    selection,
    setSelection,
    toggleCell,
    fillSelection,
    undo,
    canUndo: historyRef.current.length > 0,
    applyRemote,
  };
}
