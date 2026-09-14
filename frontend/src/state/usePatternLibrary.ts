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

import { useEffect, useState } from "react";

import {
  fetchGrid,
  fetchPatternDetail,
  fetchPatterns,
  fetchProgress,
  type ApiPatternSummary,
} from "../lib/api";
import { cachePattern, cacheProgress, db, getPendingOps } from "../lib/db";
import { patternFromApi, progressFromApi } from "../lib/mappers";
import type { Pattern, Progress } from "../pattern/types";

export interface LibraryPattern {
  pattern: Pattern;
  progress: Progress;
  version: number;
  hoursAgo: number;
}

export type LibrarySource = "loading" | "server" | "cache" | "demo";

async function applyPending(patternId: string, progress: Progress): Promise<Progress> {
  const pending = await getPendingOps(patternId);
  if (pending.length === 0) return progress;
  const next = progress.slice();
  for (const op of pending) next[op.index] = op.stitched ? 1 : 0;
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
  const done = await applyPending(summary.id, progressFromApi(progress));

  await cachePattern(pattern);
  await cacheProgress(summary.id, done, progress.version, progress.stitched_count);

  return {
    pattern,
    progress: done,
    version: progress.version,
    hoursAgo: hoursAgoFrom(summary.updated_at),
  };
}

async function loadEntriesFromCache(): Promise<LibraryPattern[]> {
  const cachedPatterns = await db.patterns.toArray();
  const entries: LibraryPattern[] = [];
  for (const row of cachedPatterns) {
    const cachedProgress = await db.progress.get(row.id);
    const base = cachedProgress?.done ?? new Uint8Array(row.pattern.width * row.pattern.height);
    const done = await applyPending(row.id, base);
    entries.push({
      pattern: row.pattern,
      progress: done,
      version: cachedProgress?.version ?? 0,
      hoursAgo: (Date.now() - row.cachedAt) / 3_600_000,
    });
  }
  return entries;
}

export function usePatternLibrary(): { entries: LibraryPattern[] | null; source: LibrarySource } {
  const [state, setState] = useState<{ entries: LibraryPattern[] | null; source: LibrarySource }>(
    { entries: null, source: "loading" },
  );

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const summaries = await fetchPatterns();
        if (summaries.length === 0) {
          if (!cancelled) setState({ entries: null, source: "demo" });
          return;
        }
        const entries = await Promise.all(summaries.map(loadEntryFromServer));
        if (!cancelled) setState({ entries, source: "server" });
      } catch {
        // Serveur injoignable : on retombe sur le cache local, puis sur la
        // démonstration si rien n'a jamais été mis en cache sur cet appareil.
        try {
          const entries = await loadEntriesFromCache();
          if (cancelled) return;
          setState(entries.length > 0 ? { entries, source: "cache" } : { entries: null, source: "demo" });
        } catch {
          if (!cancelled) setState({ entries: null, source: "demo" });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
