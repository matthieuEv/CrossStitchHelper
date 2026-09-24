/**
 * Finds the backstitch segment / knot closest to a touch point (Lot 8) —
 * pure geometry, with no canvas dependency, so it stays testable
 * independently of rendering.
 *
 * Backstitches and knots are not aligned on the cell grid like full/1-2/1-4
 * stitches: a tap's target is the nearest segment or point, within a
 * tolerance given in grid units (see `state/useTracker.ts::toggleAtPoint` for
 * how that tolerance is computed from the current zoom).
 *
 * Linear scan over the whole list: largely sufficient for the number of
 * elements in a real pattern (a few dozen to a few hundred segments/knots) —
 * no spatial index for now, to revisit if a future extraction connector
 * (Lot 9) produces patterns much denser in special stitches.
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
 * Index (into `segments`) of the segment closest to `(gx, gy)` (same cell
 * corner coordinates as `BackstitchSegment`), within `maxDistance` cells —
 * `null` if nothing is close enough.
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
 * Index (into `knots`) of the knot closest to `(gx, gy)` (same cell centre
 * coordinates as `FrenchKnot`), within `maxDistance` cells — `null` if
 * nothing is close enough.
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
