/**
 * Library sort order (Library screen's "Sort" menu).
 *
 * Remembered on this device only, in `localStorage`: a display preference,
 * never pattern data — losing it (private browsing, cleared site data) only
 * means going back to the default order.
 */

export const LIBRARY_SORTS = ["recent", "name", "progress"] as const;
export type LibrarySort = (typeof LIBRARY_SORTS)[number];

const STORAGE_KEY = "csh.librarySort";

/** Most recently worked on first: what you most likely want to reopen. */
export const DEFAULT_LIBRARY_SORT: LibrarySort = "recent";

export function readStoredLibrarySort(): LibrarySort {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if ((LIBRARY_SORTS as readonly string[]).includes(stored ?? "")) return stored as LibrarySort;
  } catch {
    // Storage unavailable: default order.
  }
  return DEFAULT_LIBRARY_SORT;
}

export function storeLibrarySort(sort: LibrarySort): void {
  try {
    localStorage.setItem(STORAGE_KEY, sort);
  } catch {
    // Storage unavailable (Safari private browsing): the choice lasts until
    // the next reload only.
  }
}
