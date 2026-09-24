/**
 * Offline cache (IndexedDB via Dexie — specification §5.3).
 *
 * Three distinct needs, three tables: the pattern and its grid rarely change
 * (re-cached on every online visit); the last progress known from the server
 * allows an instant display on load; the pending operation queue is what
 * survives a network outage — it is only emptied once the server has
 * confirmed.
 */

import Dexie, { type Table } from "dexie";

import type { Pattern, SpecialProgress, StitchLayer } from "../pattern/types";

export interface CachedPattern {
  id: string;
  pattern: Pattern;
  cachedAt: number;
}

export interface CachedProgress {
  patternId: string;
  done: Uint8Array;
  version: number;
  stitchedCount: number;
  updatedAt: number;
  /** Special stitch progress (Lot 8) — absent for a record cached before
   * that lot; treated as "nothing checked" when read. */
  half?: Uint8Array;
  quarter?: Uint8Array;
  backstitch?: Uint8Array;
  knot?: Uint8Array;
}

export interface PendingOp {
  id?: number;
  patternId: string;
  /** Absent for an operation queued before Lot 8 — treated as "full" when
   * read (`getPendingOps`), same default as on the server. */
  layer?: StitchLayer;
  index: number;
  stitched: boolean;
  createdAt: number;
}

class OfflineDatabase extends Dexie {
  patterns!: Table<CachedPattern, string>;
  progress!: Table<CachedProgress, string>;
  pendingOps!: Table<PendingOp, number>;

  constructor() {
    super("crossstitchhelper");
    this.version(1).stores({
      patterns: "id",
      progress: "patternId",
      pendingOps: "++id, patternId",
    });
  }
}

export const db = new OfflineDatabase();

export async function cachePattern(pattern: Pattern): Promise<void> {
  await db.patterns.put({ id: pattern.id, pattern, cachedAt: Date.now() });
}

export async function getCachedPattern(id: string): Promise<Pattern | null> {
  const row = await db.patterns.get(id);
  return row?.pattern ?? null;
}

export async function cacheProgress(
  patternId: string,
  done: Uint8Array,
  version: number,
  stitchedCount: number,
  special?: SpecialProgress,
): Promise<void> {
  await db.progress.put({
    patternId,
    done,
    version,
    stitchedCount,
    updatedAt: Date.now(),
    ...(special !== undefined && {
      half: special.half,
      quarter: special.quarter,
      backstitch: special.backstitch,
      knot: special.knot,
    }),
  });
}

export async function getCachedProgress(patternId: string): Promise<CachedProgress | null> {
  return (await db.progress.get(patternId)) ?? null;
}

export async function enqueueOps(
  patternId: string,
  ops: ReadonlyArray<{ layer: StitchLayer; index: number; stitched: boolean }>,
): Promise<void> {
  const now = Date.now();
  await db.pendingOps.bulkAdd(
    ops.map((op) => ({
      patternId,
      layer: op.layer,
      index: op.index,
      stitched: op.stitched,
      createdAt: now,
    })),
  );
}

export async function getPendingOps(patternId: string): Promise<PendingOp[]> {
  return db.pendingOps.where("patternId").equals(patternId).sortBy("id");
}

export async function clearPendingOps(ids: readonly number[]): Promise<void> {
  await db.pendingOps.bulkDelete(ids as number[]);
}

/**
 * Empties the whole offline cache (Lot 8, `SettingsScreen.tsx` — restoring a
 * backup). After a server restore, the patterns/progress cached here refer
 * to a state that no longer exists: keeping them would risk showing stale
 * data again before the next sync, or worse, replaying an obsolete
 * `pendingOps` on top of the freshly restored data.
 */
export async function clearOfflineCache(): Promise<void> {
  await Promise.all([db.patterns.clear(), db.progress.clear(), db.pendingOps.clear()]);
}
