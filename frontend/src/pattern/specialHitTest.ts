/**
 * Recherche du segment de point arrière / nœud le plus proche d'un point de
 * contact (Lot 8) — géométrie pure, sans dépendance au canvas, pour rester
 * testable indépendamment du rendu.
 *
 * Point arrière et nœuds ne sont pas alignés sur la grille de cases comme les
 * points entiers/1-2/1-4 : la cible d'un tap est le segment ou le point le
 * plus proche, dans une tolérance donnée en unités de grille (voir
 * `state/useTracker.ts::toggleAtPoint` pour le calcul de cette tolérance à
 * partir du zoom courant).
 *
 * Balayage linéaire sur la liste complète : largement suffisant pour le
 * nombre d'éléments d'un motif réel (quelques dizaines à quelques centaines
 * de segments/nœuds) — pas d'index spatial pour l'instant, à revisiter si un
 * futur connecteur d'extraction (Lot 9) produit des motifs nettement plus
 * denses en points spéciaux.
 */

import type { BackstitchSegment, FrenchKnot } from "./types";

function distanceToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/**
 * Index (dans `segments`) du segment le plus proche de `(gx, gy)` (mêmes
 * coordonnées de coins de case que `BackstitchSegment`), dans la limite de
 * `maxDistance` cases — `null` si rien d'assez proche.
 */
export function nearestBackstitchIndex(
  segments: readonly BackstitchSegment[],
  gx: number,
  gy: number,
  maxDistance: number,
): number | null {
  let best: number | null = null;
  let bestDistance = maxDistance;
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    if (segment === undefined) continue;
    const distance = distanceToSegment(gx, gy, segment.x1, segment.y1, segment.x2, segment.y2);
    if (distance <= bestDistance) {
      bestDistance = distance;
      best = i;
    }
  }
  return best;
}

/**
 * Index (dans `knots`) du nœud le plus proche de `(gx, gy)` (mêmes
 * coordonnées de centre de case que `FrenchKnot`), dans la limite de
 * `maxDistance` cases — `null` si rien d'assez proche.
 */
export function nearestKnotIndex(
  knots: readonly FrenchKnot[],
  gx: number,
  gy: number,
  maxDistance: number,
): number | null {
  let best: number | null = null;
  let bestDistance = maxDistance;
  for (let i = 0; i < knots.length; i++) {
    const knot = knots[i];
    if (knot === undefined) continue;
    const distance = Math.hypot(gx - knot.x, gy - knot.y);
    if (distance <= bestDistance) {
      bestDistance = distance;
      best = i;
    }
  }
  return best;
}
