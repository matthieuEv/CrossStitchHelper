import { useEffect, useRef, useState } from "react";

import { PatternThumbnail } from "../components/PatternThumbnail";
import { PlusIcon } from "../components/Icons";
import { useT } from "../i18n";
import { useCompareText, useRelativeTime } from "../lib/format";
import {
  LIBRARY_SORTS,
  readStoredLibrarySort,
  storeLibrarySort,
  type LibrarySort,
} from "../lib/librarySort";
import { summarise, countByColor } from "../pattern/counts";
import type { Pattern, Progress, SpecialProgress } from "../pattern/types";

export interface LibraryEntry {
  pattern: Pattern;
  progress: Progress;
  hoursAgo: number;
  /** Progress version known to the server; absent for a purely local pattern. */
  version?: number;
  /** Special stitch progress (Lot 8); absent for a purely local demo pattern
   * (`demo/`), which never has any — see `emptySpecialProgress` for the
   * fallback in `App.tsx`. */
  special?: SpecialProgress;
}

interface LibraryScreenProps {
  entries: readonly LibraryEntry[];
  wide: boolean;
  onOpen: (patternId: string) => void;
  onImport: () => void;
}

export function LibraryScreen({ entries, wide, onOpen, onImport }: LibraryScreenProps) {
  const t = useT();
  const relative = useRelativeTime();
  const compareText = useCompareText();
  const [sort, setSort] = useState<LibrarySort>(readStoredLibrarySort);
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const sortMenuRef = useRef<HTMLDivElement>(null);

  // The menu closes on a tap anywhere else, or with Escape.
  useEffect(() => {
    if (!sortMenuOpen) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!sortMenuRef.current?.contains(event.target as Node)) setSortMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setSortMenuOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [sortMenuOpen]);

  const chooseSort = (next: LibrarySort): void => {
    setSort(next);
    storeLibrarySort(next);
    setSortMenuOpen(false);
  };

  const cards = entries.map((entry) => {
    const totals = summarise(countByColor(entry.pattern, entry.progress));
    return { entry, totals };
  });
  // Ties always fall back to recent activity, then name: the order never
  // depends on the order the server happened to list the patterns in.
  const byRecent = (a: (typeof cards)[number], b: (typeof cards)[number]): number =>
    a.entry.hoursAgo - b.entry.hoursAgo;
  const byName = (a: (typeof cards)[number], b: (typeof cards)[number]): number =>
    compareText(a.entry.pattern.name, b.entry.pattern.name);
  cards.sort((a, b) => {
    if (sort === "name") return byName(a, b) || byRecent(a, b);
    if (sort === "progress") return b.totals.percent - a.totals.percent || byRecent(a, b) || byName(a, b);
    return byRecent(a, b) || byName(a, b);
  });
  const inProgress = cards.filter(
    (card) => card.totals.percent > 0 && card.totals.percent < 100,
  ).length;

  return (
    <div className="screen">
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 18,
        }}
      >
        <div>
          <h2 style={{ margin: "0 0 2px" }}>{t("library.title")}</h2>
          <div className="text-muted" style={{ fontSize: 13 }}>
            {t("library.summary", { count: entries.length, active: inProgress })}
          </div>
        </div>
        <div ref={sortMenuRef} style={{ position: "relative" }}>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ minHeight: 44, padding: "0 16px" }}
            aria-haspopup="menu"
            aria-expanded={sortMenuOpen}
            onClick={() => setSortMenuOpen((open) => !open)}
          >
            {t("library.sort")}
          </button>
          {sortMenuOpen && (
            <div role="menu" aria-label={t("library.sort")} className="menu elev-md">
              {LIBRARY_SORTS.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="menuitemradio"
                  aria-checked={sort === option}
                  className="menu-item"
                  onClick={() => chooseSort(option)}
                >
                  {t(`library.sort.${option}`)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {!wide && (
        <button
          type="button"
          className="btn btn-primary btn-block elev-md"
          style={{ minHeight: 56, fontSize: 17, gap: 10, marginBottom: 20 }}
          onClick={onImport}
        >
          <PlusIcon size={22} />
          {t("library.importCta")}
        </button>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
          gap: 16,
        }}
      >
        {cards.map(({ entry, totals }) => (
          <button
            key={entry.pattern.id}
            type="button"
            className="card elev-sm"
            style={{ border: 0, cursor: "pointer", textAlign: "left", padding: 12, gap: 12 }}
            onClick={() => onOpen(entry.pattern.id)}
          >
            <div
              style={{
                aspectRatio: "4 / 3",
                borderRadius: 18,
                overflow: "hidden",
                background: "var(--color-neutral-200)",
              }}
            >
              <PatternThumbnail
                pattern={entry.pattern}
                progress={entry.progress}
                label={entry.pattern.name}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <div className="card-title">{entry.pattern.name}</div>
                <div className="text-muted num" style={{ fontSize: 13 }}>
                  {totals.percent}%
                </div>
              </div>
              <div className="text-muted" style={{ fontSize: 12 }}>
                {t("library.patternMeta", {
                  size: `${entry.pattern.width} × ${entry.pattern.height}`,
                  colors: entry.pattern.palette.length,
                })}
              </div>
              <div className="bar">
                <span
                  style={{
                    width: `${totals.percent}%`,
                    background:
                      totals.percent === 100 ? "var(--color-accent-2)" : "var(--color-accent)",
                  }}
                />
              </div>
              <div className="text-faint" style={{ fontSize: 11 }}>
                {relative(entry.hoursAgo)}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
