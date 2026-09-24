import type { PaletteEntry, Pattern, Progress } from "./types";

export interface ColorCount extends PaletteEntry {
  /** 1-based index into the palette, as stored in `Pattern.cells`. */
  index: number;
  total: number;
  done: number;
  remaining: number;
  /** Stitched share of this colour, from 0 to 1. */
  ratio: number;
}

/** Number of stitches one skein can cover (14-count fabric, estimate). */
export const STITCHES_PER_SKEIN = 1800;
/** Stitching pace used to estimate the remaining time. */
export const STITCHES_PER_HOUR = 420;

/**
 * Counts stitches per colour in a single pass over the grid.
 *
 * Called on every checked cell: stays linear and allocation-free per cell, so
 * as not to become the bottleneck on a 45,000-cell pattern.
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
  /** Progress as an integer percentage, 0 to 100. */
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
