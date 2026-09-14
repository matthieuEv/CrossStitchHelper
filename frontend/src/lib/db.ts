/**
 * Cache hors-ligne (IndexedDB via Dexie — cahier des charges §5.3).
 *
 * Trois besoins distincts, trois tables : le motif et sa grille changent
 * rarement (recache à chaque visite en ligne) ; la dernière progression
 * connue du serveur permet un affichage instantané au chargement ; la file
 * d'opérations en attente est ce qui survit à une coupure réseau — elle
 * n'est vidée qu'une fois le serveur confirmé.
 */

import Dexie, { type Table } from "dexie";

import type { Pattern } from "../pattern/types";

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
}

export interface PendingOp {
  id?: number;
  patternId: string;
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
): Promise<void> {
  await db.progress.put({ patternId, done, version, stitchedCount, updatedAt: Date.now() });
}

export async function getCachedProgress(patternId: string): Promise<CachedProgress | null> {
  return (await db.progress.get(patternId)) ?? null;
}

export async function enqueueOps(
  patternId: string,
  ops: ReadonlyArray<{ index: number; stitched: boolean }>,
): Promise<void> {
  const now = Date.now();
  await db.pendingOps.bulkAdd(
    ops.map((op) => ({ patternId, index: op.index, stitched: op.stitched, createdAt: now })),
  );
}

export async function getPendingOps(patternId: string): Promise<PendingOp[]> {
  return db.pendingOps.where("patternId").equals(patternId).sortBy("id");
}

export async function clearPendingOps(ids: readonly number[]): Promise<void> {
  await db.pendingOps.bulkDelete(ids as number[]);
}
