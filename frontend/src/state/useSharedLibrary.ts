/**
 * The shared library tab (Lot 11, issue #78): its patterns, ready to draw as
 * thumbnails, and the requests the logged-in profile may see.
 *
 * Online only — unlike one's own library, nothing of it is cached on the
 * device: it is a catalogue to copy from, never something stitched as is.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchSharedGrid,
  fetchSharedLibrary,
  fetchSharedPatternDetail,
  type ApiSharedPattern,
  type ApiSharedRequest,
} from "../lib/api";
import { patternFromApi } from "../lib/mappers";
import type { Pattern } from "../pattern/types";

export interface SharedEntry {
  pattern: Pattern;
  summary: ApiSharedPattern;
}

export type SharedLibraryState = "loading" | "ready" | "unavailable";

export interface SharedLibrary {
  state: SharedLibraryState;
  entries: SharedEntry[];
  requests: ApiSharedRequest[];
  refresh: () => Promise<void>;
}

/** A shared pattern or a proposal, drawn like any other pattern. */
export async function loadSharedPattern(id: string): Promise<Pattern> {
  const [detail, grid] = await Promise.all([fetchSharedPatternDetail(id), fetchSharedGrid(id)]);
  return patternFromApi(detail, grid);
}

export function useSharedLibrary(): SharedLibrary {
  const [state, setState] = useState<SharedLibraryState>("loading");
  const [entries, setEntries] = useState<SharedEntry[]>([]);
  const [requests, setRequests] = useState<ApiSharedRequest[]>([]);
  // Patterns already drawn, by id and revision: a refresh after an action
  // only fetches what changed.
  const cacheRef = useRef(new Map<string, { revision: number; pattern: Pattern }>());
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    try {
      const library = await fetchSharedLibrary();
      const loaded = await Promise.all(
        library.patterns.map(async (summary): Promise<SharedEntry> => {
          const cached = cacheRef.current.get(summary.id);
          const pattern =
            cached !== undefined && cached.revision === summary.revision
              ? { ...cached.pattern, name: summary.name, labels: summary.labels }
              : await loadSharedPattern(summary.id);
          cacheRef.current.set(summary.id, { revision: summary.revision, pattern });
          return { pattern, summary };
        }),
      );
      if (requestId !== requestIdRef.current) return;
      setEntries(loaded);
      setRequests(library.requests);
      setState("ready");
    } catch {
      if (requestId === requestIdRef.current) setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { state, entries, requests, refresh: load };
}
