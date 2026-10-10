/**
 * Remembers, per pattern and on this device only, where the tracking view
 * was (zoom level and position), so a page reload reopens the pattern at the
 * same spot instead of the default starting position.
 *
 * Kept in `localStorage` rather than on the server: the view is a per-device
 * convenience (a phone and an iPad never show the same area at the same
 * zoom), never tracking data — losing it (private browsing, cleared site
 * data) only means reopening at the default position.
 */

import type { GridView } from "../pattern/render";

const KEY_PREFIX = "csh.view.";

export function loadView(patternId: string): GridView | null {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + patternId);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { cell, x0, y0 } = parsed as Record<string, unknown>;
    if (
      typeof cell !== "number" ||
      typeof x0 !== "number" ||
      typeof y0 !== "number" ||
      !Number.isFinite(cell) ||
      !Number.isFinite(x0) ||
      !Number.isFinite(y0)
    ) {
      return null;
    }
    return { cell, x0, y0 };
  } catch {
    // Storage unavailable or corrupted value: default position.
    return null;
  }
}

export function saveView(patternId: string, view: GridView): void {
  try {
    localStorage.setItem(
      KEY_PREFIX + patternId,
      JSON.stringify({ cell: view.cell, x0: view.x0, y0: view.y0 }),
    );
  } catch {
    // Storage unavailable (Safari private browsing, quota): best effort only.
  }
}
