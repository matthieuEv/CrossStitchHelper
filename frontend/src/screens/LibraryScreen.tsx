import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { PatternThumbnail } from "../components/PatternThumbnail";
import { CloseIcon, PlusIcon } from "../components/Icons";
import { useT } from "../i18n";
import { translateApiError } from "../lib/api";
import { useRelativeTime } from "../lib/format";
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
  /**
   * Pattern actions (issue #52), absent when they cannot apply — the built-in
   * demo patterns, or a library served from the offline cache: both need the
   * server. Each resolves once the library has been refreshed.
   */
  onDuplicate?: (patternId: string, name: string) => Promise<void>;
  onDelete?: (patternId: string) => Promise<void>;
}

/** Holding a card this long opens its actions, like a native long-press. */
const LONG_PRESS_MS = 550;
/** Moving the finger further than this cancels the long-press (a scroll). */
const LONG_PRESS_SLOP_PX = 10;

export function LibraryScreen({
  entries,
  wide,
  onOpen,
  onImport,
  onDuplicate,
  onDelete,
}: LibraryScreenProps) {
  const t = useT();
  const hasActions = onDuplicate !== undefined && onDelete !== undefined;
  const [actionsFor, setActionsFor] = useState<LibraryEntry | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const openActions = (entry: LibraryEntry): void => {
    setActionsFor(entry);
    setConfirmingDelete(false);
    setActionError(null);
  };
  const closeActions = (): void => {
    if (!busy) setActionsFor(null);
  };
  // Escape closes the actions, like a tap outside them.
  useEffect(() => {
    if (actionsFor === null) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !busy) setActionsFor(null);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [actionsFor, busy]);

  const runAction = async (action: () => Promise<void>): Promise<void> => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      setActionsFor(null);
    } catch (error) {
      setActionError(translateApiError(t, error));
    } finally {
      setBusy(false);
    }
  };

  // Long-press on a card (touch or mouse): opens its actions instead of the
  // pattern. The click that follows the release must then not open it too.
  const pressRef = useRef<{ timer: number; x: number; y: number } | null>(null);
  const suppressClickRef = useRef(false);
  const cancelPress = (): void => {
    if (pressRef.current !== null) window.clearTimeout(pressRef.current.timer);
    pressRef.current = null;
  };
  const startPress = (entry: LibraryEntry) => (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!hasActions) return;
    cancelPress();
    suppressClickRef.current = false;
    const timer = window.setTimeout(() => {
      pressRef.current = null;
      suppressClickRef.current = true;
      openActions(entry);
    }, LONG_PRESS_MS);
    pressRef.current = { timer, x: event.clientX, y: event.clientY };
  };
  const movePress = (event: ReactPointerEvent<HTMLButtonElement>): void => {
    const press = pressRef.current;
    if (press === null) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > LONG_PRESS_SLOP_PX) {
      cancelPress();
    }
  };
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
          <div key={entry.pattern.id} style={{ position: "relative", display: "grid" }}>
            <button
              type="button"
              className="card elev-sm library-card"
              style={{ border: 0, cursor: "pointer", textAlign: "left", padding: 12, gap: 12 }}
              onClick={() => {
                if (suppressClickRef.current) {
                  suppressClickRef.current = false;
                  return;
                }
                onOpen(entry.pattern.id);
              }}
              onPointerDown={startPress(entry)}
              onPointerMove={movePress}
              onPointerUp={cancelPress}
              onPointerCancel={cancelPress}
              onPointerLeave={cancelPress}
              onContextMenu={(event) => {
                // Right click, or a long-press the browser reports as such.
                if (!hasActions) return;
                event.preventDefault();
                cancelPress();
                openActions(entry);
              }}
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
            {hasActions && (
              <button
                type="button"
                className="btn btn-icon btn-secondary library-card-more"
                aria-label={t("library.actions", { name: entry.pattern.name })}
                aria-haspopup="dialog"
                onClick={() => openActions(entry)}
              >
                ⋯
              </button>
            )}
          </div>
        ))}
      </div>

      {actionsFor !== null && (
        <div className="drawer-backdrop is-fixed" role="presentation" onClick={closeActions}>
          <div
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label={t("library.actions", { name: actionsFor.pattern.name })}
            onClick={(event) => event.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                padding: "14px 18px 8px",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-heading)",
                  fontSize: 18,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {actionsFor.pattern.name}
              </div>
              <button
                type="button"
                className="btn btn-icon btn-secondary"
                onClick={closeActions}
                aria-label={t("track.close")}
              >
                <CloseIcon size={18} />
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "6px 18px 22px" }}>
              {confirmingDelete ? (
                <>
                  <p style={{ margin: 0 }}>{t("library.deleteConfirm", { name: actionsFor.pattern.name })}</p>
                  <button
                    type="button"
                    className="btn btn-primary btn-block"
                    style={{ minHeight: 48 }}
                    disabled={busy}
                    onClick={() => void runAction(() => onDelete!(actionsFor.pattern.id))}
                  >
                    {t("library.deleteConfirmAction")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-block"
                    style={{ minHeight: 48 }}
                    disabled={busy}
                    onClick={() => setConfirmingDelete(false)}
                  >
                    {t("library.cancel")}
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn btn-secondary btn-block"
                    style={{ minHeight: 48 }}
                    disabled={busy}
                    onClick={() =>
                      void runAction(() =>
                        onDuplicate!(
                          actionsFor.pattern.id,
                          t("library.copyName", { name: actionsFor.pattern.name }),
                        ),
                      )
                    }
                  >
                    {t("library.duplicate")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-block"
                    style={{ minHeight: 48 }}
                    disabled={busy}
                    onClick={() => setConfirmingDelete(true)}
                  >
                    {t("library.delete")}
                  </button>
                </>
              )}
              {actionError !== null && (
                <p role="alert" className="tag tag-accent" style={{ margin: 0 }}>
                  {actionError}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
