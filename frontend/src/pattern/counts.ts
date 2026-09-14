import type { PaletteEntry, Pattern, Progress } from "./types";

export interface ColorCount extends PaletteEntry {
  /** Index 1-based dans la palette, tel que stocké dans `Pattern.cells`. */
  index: number;
  total: number;
  done: number;
  remaining: number;
  /** Part brodée de cette couleur, de 0 à 1. */
  ratio: number;
}

/** Nombre de points qu'un écheveau permet de broder (toile 14 ct, estimation). */
export const STITCHES_PER_SKEIN = 1800;
/** Cadence de broderie retenue pour estimer le temps restant. */
export const STITCHES_PER_HOUR = 420;

/**
 * Compte les points par couleur en une seule passe sur la grille.
 *
 * Appelé à chaque case cochée : reste linéaire et sans allocation par case,
 * pour ne pas devenir le goulot d'étranglement sur un motif de 45 000 cases.
 */
export function countByColor(pattern: Pattern, done: Progress): ColorCount[] {
  const totals = new Uint32Array(pattern.palette.length + 1);
  const doneCounts = new Uint32Array(pattern.palette.length + 1);

  for (let i = 0; i < pattern.cells.length; i++) {
    const value = pattern.cells[i] ?? 0;
    if (value === 0) continue;
    totals[value] = (totals[value] ?? 0) + 1;
    if (done[i]) doneCounts[value] = (doneCounts[value] ?? 0) + 1;
  }

  return pattern.palette.map((entry, position) => {
    const index = position + 1;
    const total = totals[index] ?? 0;
    const doneCount = doneCounts[index] ?? 0;
    return {
      ...entry,
      index,
      total,
      done: doneCount,
      remaining: total - doneCount,
      ratio: total === 0 ? 0 : doneCount / total,
    };
  });
}

export interface PatternTotals {
  total: number;
  done: number;
  remaining: number;
  /** Progression en pourcentage entier, 0 à 100. */
  percent: number;
  skeinsRemaining: number;
  hoursRemaining: number;
}

export function summarise(counts: readonly ColorCount[]): PatternTotals {
  let total = 0;
  let done = 0;
  let skeinsRemaining = 0;

  for (const count of counts) {
    total += count.total;
    done += count.done;
    skeinsRemaining += Math.ceil(count.remaining / STITCHES_PER_SKEIN);
  }

  const remaining = total - done;
  return {
    total,
    done,
    remaining,
    percent: total === 0 ? 0 : Math.round((done / total) * 100),
    skeinsRemaining,
    hoursRemaining: Math.round(remaining / STITCHES_PER_HOUR),
  };
}
