/**
 * Sort order of the Library's "Shared" tab (issue #91), chosen from the same
 * "Sort" button as "My patterns" but remembered on its own: the two lists do
 * not hold the same things — a shared pattern has no progress of its own.
 *
 * Remembered on this device only, in `localStorage`, like `librarySort.ts`.
 */

import { createContext } from "react";

import type { ApiSharedPattern } from "./api";

export const SHARED_SORTS = ["recent", "name"] as const;
export type SharedSort = (typeof SHARED_SORTS)[number];

const STORAGE_KEY = "csh.sharedSort";

/** Most recently added or changed first: what is new in the shared library. */
export const DEFAULT_SHARED_SORT: SharedSort = "recent";

export function readStoredSharedSort(): SharedSort {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if ((SHARED_SORTS as readonly string[]).includes(stored ?? "")) return stored as SharedSort;
  } catch {
    // Storage unavailable: default order.
  }
  return DEFAULT_SHARED_SORT;
}

export function storeSharedSort(sort: SharedSort): void {
  try {
    localStorage.setItem(STORAGE_KEY, sort);
  } catch {
    // Storage unavailable (Safari private browsing): the choice lasts until
    // the next reload only.
  }
}

/** The order the Library's "Sort" menu chose for the "Shared" tab. A context
 * rather than a prop: the tab's content is built by `App`, outside the
 * Library screen that owns the menu. */
export const SharedSortContext = createContext<SharedSort>(DEFAULT_SHARED_SORT);

/** `a` before `b` in `sort` order. Ties always fall back to the other key,
 * so the order never depends on the order the server listed them in. */
export function compareShared(
  sort: SharedSort,
  a: Pick<ApiSharedPattern, "name" | "updated_at">,
  b: Pick<ApiSharedPattern, "name" | "updated_at">,
  compareText: (a: string, b: string) => number,
): number {
  const byRecent = Date.parse(b.updated_at) - Date.parse(a.updated_at);
  const byName = compareText(a.name, b.name);
  return sort === "name" ? byName || byRecent : byRecent || byName;
}
