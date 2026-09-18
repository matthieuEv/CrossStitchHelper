import { PatternThumbnail } from "../components/PatternThumbnail";
import { PlusIcon } from "../components/Icons";
import { useT } from "../i18n";
import { useRelativeTime } from "../lib/format";
import { summarise, countByColor } from "../pattern/counts";
import type { Pattern, Progress, SpecialProgress } from "../pattern/types";

export interface LibraryEntry {
  pattern: Pattern;
  progress: Progress;
  hoursAgo: number;
  /** Version de progression connue du serveur ; absente pour un motif purement local. */
  version?: number;
  /** Progression des points spéciaux (Lot 8) ; absente pour un motif de
   * démonstration purement local (`demo/`), qui n'en a jamais — voir
   * `emptySpecialProgress` pour le repli côté `App.tsx`. */
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

  const cards = entries.map((entry) => {
    const totals = summarise(countByColor(entry.pattern, entry.progress));
    return { entry, totals };
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
        <button type="button" className="btn btn-secondary" style={{ minHeight: 44, padding: "0 16px" }}>
          {t("library.sort")}
        </button>
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
