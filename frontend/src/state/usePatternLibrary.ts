/**
 * Loads the pattern library from the server, with an offline fallback.
 *
 * Three possible sources, in this order of preference:
 * 1. **Server** — the normal, online case.
 * 2. **Cache** (IndexedDB) — server unreachable, but patterns have already
 *    been visited on this device: they are shown again as they were.
 * 3. **Demo** — neither server nor cache (first offline launch, or no backend
 *    instance in development): `App.tsx` falls back to the pattern built on
 *    the client (`demo/lavender.ts`).
 *
 * A server that answers with no pattern is an empty library, never the demo
 * (Lot 10): a profile that has imported nothing yet must not be shown
 * client-made patterns as if they were its own.
 *
 * In cases 1 and 2, any operation still queued (not yet confirmed by the
 * server) is replayed on top of the loaded progress, so the display never
 * "goes backwards" after a reload during a network outage.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchGrid,
  fetchPatternDetail,
  fetchPatterns,
  fetchProgress,
  type ApiPatternSummary,
} from "../lib/api";
import {
  cachePattern,
  cacheProgress,
  getCachedPatterns,
  getCachedProgress,
  getPendingOps,
  type PendingOp,
} from "../lib/db";
import { patternFromApi, progressFromApi, specialProgressFromApi } from "../lib/mappers";
import type { Pattern, Progress, SpecialProgress } from "../pattern/types";

export interface LibraryPattern {
  pattern: Pattern;
  progress: Progress;
  special: SpecialProgress;
  version: number;
  /** When the pattern was last stitched, in milliseconds since the epoch. */
  lastActivityAt: number;
}

export type LibrarySource = "loading" | "server" | "cache" | "demo";

interface LayeredBase {
  full: Progress;
  special: SpecialProgress;
}

/**
 * Replays the operations still queued (not yet confirmed by the server) on
 * top of a base progress, so the display never "goes backwards" after a
 * reload during a network outage — all five stitch categories (Lot 8) at
 * once, a queued operation always carries its own `layer`.
 */
async function applyPending(patternId: string, base: LayeredBase): Promise<LayeredBase> {
  const pending = await getPendingOps(patternId);
  if (pending.length === 0) return base;
  const next: LayeredBase = {
    full: base.full.slice(),
    special: {
      half: base.special.half.slice(),
      quarter: base.special.quarter.slice(),
      backstitch: base.special.backstitch.slice(),
      knot: base.special.knot.slice(),
    },
  };
  const targetFor = (op: PendingOp): Uint8Array => {
    // An operation queued before Lot 8 has no `layer`: it can only be a full
    // stitch, same default as on the server.
    switch (op.layer ?? "full") {
      case "half":
        return next.special.half;
      case "quarter":
        return next.special.quarter;
      case "backstitch":
        return next.special.backstitch;
      case "knot":
        return next.special.knot;
      default:
        return next.full;
    }
  };
  for (const op of pending) {
    const target = targetFor(op);
    if (op.index >= 0 && op.index < target.length) target[op.index] = op.stitched ? 1 : 0;
  }
  return next;
}

async function loadEntryFromServer(summary: ApiPatternSummary): Promise<LibraryPattern> {
  const [detail, grid, progress] = await Promise.all([
    fetchPatternDetail(summary.id),
    fetchGrid(summary.id),
    fetchProgress(summary.id),
  ]);
  const pattern = patternFromApi(detail, grid);
  const merged = await applyPending(summary.id, {
    full: progressFromApi(progress),
    special: specialProgressFromApi(grid, progress),
  });

  await cachePattern(pattern);
  await cacheProgress(summary.id, merged.full, progress.version, progress.stitched_count, merged.special);

  return {
    pattern,
    progress: merged.full,
    special: merged.special,
    version: progress.version,
    lastActivityAt: Date.parse(summary.updated_at),
  };
}

async function loadEntriesFromCache(): Promise<LibraryPattern[]> {
  const cachedPatterns = await getCachedPatterns();
  const entries: LibraryPattern[] = [];
  for (const row of cachedPatterns) {
    const cachedProgress = await getCachedProgress(row.id);
    const cellCount = row.pattern.width * row.pattern.height;
    const base: LayeredBase = {
      full: cachedProgress?.done ?? new Uint8Array(cellCount),
      special: {
        half: cachedProgress?.half ?? new Uint8Array(cellCount),
        quarter: cachedProgress?.quarter ?? new Uint8Array(cellCount),
        backstitch: cachedProgress?.backstitch ?? new Uint8Array(row.pattern.backstitch.length),
        knot: cachedProgress?.knot ?? new Uint8Array(row.pattern.frenchKnots.length),
      },
    };
    const merged = await applyPending(row.id, base);
    entries.push({
      pattern: row.pattern,
      progress: merged.full,
      special: merged.special,
      version: cachedProgress?.version ?? 0,
      lastActivityAt: row.cachedAt,
    });
  }
  return entries;
}

export interface PatternLibrary {
  entries: LibraryPattern[] | null;
  source: LibrarySource;
  /**
   * Reloads from the server (cache/demo fallback unchanged). Used after a
   * validated import (Lot 2): the newly created pattern must appear without
   * waiting for the screen's next mount.
   */
  refresh: () => Promise<void>;
}

export function usePatternLibrary(): PatternLibrary {
  const [state, setState] = useState<{ entries: LibraryPattern[] | null; source: LibrarySource }>(
    { entries: null, source: "loading" },
  );
  // Avoids publishing the result of a request that has become stale if
  // `refresh` is called while a previous load is still in flight.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const isStale = (): boolean => requestId !== requestIdRef.current;

    try {
      const summaries = await fetchPatterns();
      const entries = await Promise.all(summaries.map(loadEntryFromServer));
      if (!isStale()) setState({ entries, source: "server" });
    } catch {
      // Server unreachable: fall back to the local cache, then to the demo if
      // nothing has ever been cached on this device.
      try {
        const entries = await loadEntriesFromCache();
        if (isStale()) return;
        setState(
          entries.length > 0 ? { entries, source: "cache" } : { entries: null, source: "demo" },
        );
      } catch {
        if (!isStale()) setState({ entries: null, source: "demo" });
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { ...state, refresh: load };
}
