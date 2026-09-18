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
  /** Progression des points spéciaux (Lot 8) — absente pour un enregistrement
   * mis en cache avant ce lot ; traitée comme « rien de coché » à la lecture. */
  half?: Uint8Array;
  quarter?: Uint8Array;
  backstitch?: Uint8Array;
  knot?: Uint8Array;
}

export interface PendingOp {
  id?: number;
  patternId: string;
  /** Absent pour une opération mise en file avant le Lot 8 — traitée comme
   * « full » à la lecture (`getPendingOps`), même défaut que côté serveur. */
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
