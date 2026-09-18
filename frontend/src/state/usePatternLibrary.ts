/**
 * Charge la bibliothèque de motifs depuis le serveur, avec repli hors-ligne.
 *
 * Trois sources possibles, dans cet ordre de préférence :
 * 1. **Serveur** — le cas normal, en ligne.
 * 2. **Cache** (IndexedDB) — serveur injoignable, mais des motifs ont déjà
 *    été visités sur cet appareil : on les réaffiche tels quels.
 * 3. **Démonstration** — ni serveur ni cache (premier lancement hors-ligne,
 *    ou instance backend absente en développement) : `App.tsx` retombe sur
 *    le motif construit côté client (`demo/lavender.ts`).
 *
 * Dans les cas 1 et 2, toute opération encore en file (pas encore confirmée
 * par le serveur) est rejouée par-dessus la progression chargée, pour ne
 * jamais faire « reculer » l'affichage après un rechargement pendant une
 * coupure réseau.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchGrid,
  fetchPatternDetail,
  fetchPatterns,
  fetchProgress,
  type ApiPatternSummary,
} from "../lib/api";
import { cachePattern, cacheProgress, db, getPendingOps, type PendingOp } from "../lib/db";
import { patternFromApi, progressFromApi, specialProgressFromApi } from "../lib/mappers";
import type { Pattern, Progress, SpecialProgress } from "../pattern/types";

export interface LibraryPattern {
  pattern: Pattern;
  progress: Progress;
  special: SpecialProgress;
  version: number;
  hoursAgo: number;
}

export type LibrarySource = "loading" | "server" | "cache" | "demo";

interface LayeredBase {
  full: Progress;
  special: SpecialProgress;
}

/**
 * Rejoue les opérations encore en file (pas encore confirmées par le
 * serveur) par-dessus une progression de base, pour ne jamais faire
 * « reculer » l'affichage après un rechargement pendant une coupure réseau —
 * les cinq catégories de points (Lot 8) à la fois, une opération en file
 * porte toujours sa propre `layer`.
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
    // Une opération mise en file avant le Lot 8 n'a pas de `layer` : elle ne
    // peut être qu'un point entier, même défaut que côté serveur.
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

function hoursAgoFrom(isoDate: string): number {
  return Math.max(0, (Date.now() - new Date(isoDate).getTime()) / 3_600_000);
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
    hoursAgo: hoursAgoFrom(summary.updated_at),
  };
}

async function loadEntriesFromCache(): Promise<LibraryPattern[]> {
  const cachedPatterns = await db.patterns.toArray();
  const entries: LibraryPattern[] = [];
  for (const row of cachedPatterns) {
    const cachedProgress = await db.progress.get(row.id);
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
      hoursAgo: (Date.now() - row.cachedAt) / 3_600_000,
    });
  }
  return entries;
}

export interface PatternLibrary {
  entries: LibraryPattern[] | null;
  source: LibrarySource;
  /**
   * Recharge depuis le serveur (repli cache/démonstration inchangé).
   * Utilisé après un import validé (Lot 2) : le motif tout juste créé doit
   * apparaître sans attendre le prochain montage de l'écran.
   */
  refresh: () => Promise<void>;
}

export function usePatternLibrary(): PatternLibrary {
  const [state, setState] = useState<{ entries: LibraryPattern[] | null; source: LibrarySource }>(
    { entries: null, source: "loading" },
  );
  // Évite de publier le résultat d'une requête devenue obsolète si `refresh`
  // est appelé pendant qu'un chargement précédent est encore en vol.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const isStale = (): boolean => requestId !== requestIdRef.current;

    try {
      const summaries = await fetchPatterns();
      if (summaries.length === 0) {
        if (!isStale()) setState({ entries: null, source: "demo" });
        return;
      }
      const entries = await Promise.all(summaries.map(loadEntryFromServer));
      if (!isStale()) setState({ entries, source: "server" });
    } catch {
      // Serveur injoignable : on retombe sur le cache local, puis sur la
      // démonstration si rien n'a jamais été mis en cache sur cet appareil.
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
