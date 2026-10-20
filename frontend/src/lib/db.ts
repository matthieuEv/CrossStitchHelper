/**
 * Offline cache (IndexedDB via Dexie — specification §5.3).
 *
 * Three distinct needs, three tables: the pattern and its grid rarely change
 * (re-cached on every online visit); the last progress known from the server
 * allows an instant display on load; the pending operation queue is what
 * survives a network outage — it is only emptied once the server has
 * confirmed.
 *
 * One database **per profile** (Lot 10): `crossstitchhelper-<userId>`, opened
 * by `openOfflineDatabase` when a profile logs in. On a shared iPad, a
 * profile's cached library therefore never shows up in another profile's
 * session, and switching back and forth does not re-download everything.
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
  /** Issue #83 — absent for a record cached before it. */
  threeQuarter?: Uint8Array;
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

  constructor(name: string) {
    super(name);
    this.version(1).stores({
      patterns: "id",
      progress: "patternId",
      pendingOps: "++id, patternId",
    });
  }
}

const DATABASE_PREFIX = "crossstitchhelper-";
/** The database of the single-profile versions, before Lot 10. */
const LEGACY_DATABASE = "crossstitchhelper";

let current: OfflineDatabase | null = null;

/** The logged-in profile's database. Only ever used once a profile is
 * logged in (`state/auth.tsx` opens it before the application mounts). */
function db(): OfflineDatabase {
  if (current === null) throw new Error("Offline database used before a profile logged in");
  return current;
}

/** Switch the offline cache to `userId`'s database. */
export function openOfflineDatabase(userId: string): void {
  if (current?.name === DATABASE_PREFIX + userId) return;
  current?.close();
  current = new OfflineDatabase(DATABASE_PREFIX + userId);
}

export async function getCachedPatterns(): Promise<CachedPattern[]> {
  // A pattern cached before issue #83 has no 1/4 or 3/4 lists (its 1/4
  // stitches were a cell layer then): read as none rather than crash.
  return (await db().patterns.toArray()).map((row) => ({
    ...row,
    pattern: {
      ...row.pattern,
      quarterStitches: row.pattern.quarterStitches ?? [],
      threeQuarterStitches: row.pattern.threeQuarterStitches ?? [],
    },
  }));
}

/** Sends a pattern's queued operations; answers `true` once the server has
 * dealt with them for good (the queue entries can go), `false` to keep them
 * for a later attempt. */
export type SendQueuedOps = (
  patternId: string,
  baseVersion: number,
  ops: PendingOp[],
) => Promise<boolean>;

async function flushDatabase(database: OfflineDatabase, send: SendQueuedOps): Promise<number> {
  const pending = await database.pendingOps.orderBy("id").toArray();
  const byPattern = new Map<string, PendingOp[]>();
  for (const op of pending) {
    byPattern.set(op.patternId, [...(byPattern.get(op.patternId) ?? []), op]);
  }
  let left = 0;
  for (const [patternId, ops] of byPattern) {
    const progress = await database.progress.get(patternId);
    if (await send(patternId, progress?.version ?? 0, ops)) {
      await database.pendingOps.bulkDelete(
        ops.map((op) => op.id).filter((id): id is number => id !== undefined),
      );
    } else {
      left += ops.length;
    }
  }
  return left;
}

/** Sends every operation the logged-in profile still has queued, whatever
 * the pattern — before switching profile on a shared device. Returns how
 * many are left (server unreachable): they stay in this profile's database
 * and go out at its next login. */
export async function flushPendingOps(send: SendQueuedOps): Promise<number> {
  return current === null ? 0 : flushDatabase(current, send);
}

/**
 * Hands the progress operations still queued in the pre-profiles database
 * (`crossstitchhelper`, Lots 1-9) to the server once, then deletes that
 * database — kept as long as some could not be sent.
 */
export async function drainLegacyOfflineDatabase(send: SendQueuedOps): Promise<void> {
  if (!(await Dexie.exists(LEGACY_DATABASE))) return;
  const legacy = new OfflineDatabase(LEGACY_DATABASE);
  let left: number;
  try {
    left = await flushDatabase(legacy, send);
  } finally {
    legacy.close();
  }
  if (left === 0) await Dexie.delete(LEGACY_DATABASE);
}

export async function cachePattern(pattern: Pattern): Promise<void> {
  await db().patterns.put({ id: pattern.id, pattern, cachedAt: Date.now() });
}

export async function getCachedPattern(id: string): Promise<Pattern | null> {
  const row = await db().patterns.get(id);
  return row?.pattern ?? null;
}

export async function cacheProgress(
  patternId: string,
  done: Uint8Array,
  version: number,
  stitchedCount: number,
  special?: SpecialProgress,
): Promise<void> {
  await db().progress.put({
    patternId,
    done,
    version,
    stitchedCount,
    updatedAt: Date.now(),
    ...(special !== undefined && {
      half: special.half,
      quarter: special.quarter,
      threeQuarter: special.threeQuarter,
      backstitch: special.backstitch,
      knot: special.knot,
    }),
  });
}

export async function getCachedProgress(patternId: string): Promise<CachedProgress | null> {
  return (await db().progress.get(patternId)) ?? null;
}

export async function enqueueOps(
  patternId: string,
  ops: ReadonlyArray<{ layer: StitchLayer; index: number; stitched: boolean }>,
): Promise<void> {
  const now = Date.now();
  await db().pendingOps.bulkAdd(
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
  return db().pendingOps.where("patternId").equals(patternId).sortBy("id");
}

export async function clearPendingOps(ids: readonly number[]): Promise<void> {
  await db().pendingOps.bulkDelete(ids as number[]);
}

/** Forgets one pattern on this device: cached grid, progress and any
 * operation still queued for it — a deleted pattern must not come back from
 * the offline cache (issue #52). */
export async function forgetCachedPattern(patternId: string): Promise<void> {
  await Promise.all([
    db().patterns.delete(patternId),
    db().progress.delete(patternId),
    db().pendingOps.where("patternId").equals(patternId).delete(),
  ]);
}

/**
 * Empties the whole offline cache of this device (Lot 8, `SettingsScreen.tsx`
 * — restoring a backup). After a server restore, the patterns/progress cached
 * here refer to a state that no longer exists: keeping them would risk
 * showing stale data again before the next sync, or worse, replaying an
 * obsolete `pendingOps` on top of the freshly restored data. Every profile's
 * database goes (Lot 10): a restore replaces everyone's data, not only the
 * admin's who ran it.
 */
export async function clearOfflineCache(): Promise<void> {
  current?.close();
  current = null;
  const names = await Dexie.getDatabaseNames();
  await Promise.all(
    names
      .filter((name) => name === LEGACY_DATABASE || name.startsWith(DATABASE_PREFIX))
      .map((name) => Dexie.delete(name)),
  );
}
