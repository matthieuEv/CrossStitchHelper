import { useEffect, useState, type ReactNode } from "react";

import { useT } from "../i18n";
import {
  copySharedPattern,
  createSharedRequest,
  deleteSharedPattern,
  replaceSharedPattern,
  settleSharedRequest,
  translateApiError,
  updateSharedPattern,
  type ApiSharedRequest,
} from "../lib/api";
import { useCompareText } from "../lib/format";
import { allLabels } from "../lib/labels";
import type { Pattern } from "../pattern/types";
import { loadSharedPattern, type SharedEntry, type SharedLibrary } from "../state/useSharedLibrary";
import { CloseIcon } from "./Icons";
import { LabelPicker } from "./LabelPicker";
import { PatternThumbnail } from "./PatternThumbnail";

interface SharedLibraryViewProps {
  shared: SharedLibrary;
  isAdmin: boolean;
  /** The logged-in profile's own patterns: what it can propose as a new
   * version, or (admins) put in place of a shared pattern's content. */
  myPatterns: ReadonlyArray<{ id: string; name: string }>;
  /** After a copy into one's library: refresh it and show it. */
  onCopied: () => Promise<void>;
  /** A shared pattern's content changed (replacement, removal): the
   * profile's own copies now show "update available" or lose their link. */
  onOriginsChanged: () => Promise<void>;
}

type SheetMode = "menu" | "removal" | "propose" | "edit" | "replace" | "delete";

function Thumbnail({ pattern, label }: { pattern: Pattern; label: string }) {
  return (
    <div
      style={{
        aspectRatio: "4 / 3",
        borderRadius: 18,
        overflow: "hidden",
        background: "var(--color-neutral-200)",
      }}
    >
      <PatternThumbnail pattern={pattern} progress={null} label={label} />
    </div>
  );
}

/** A proposed version, fetched on demand (admins deciding, and its author). */
function ProposalThumbnail({ proposalId, label }: { proposalId: string; label: string }) {
  const [pattern, setPattern] = useState<Pattern | null>(null);
  useEffect(() => {
    let alive = true;
    void loadSharedPattern(proposalId)
      .then((loaded) => alive && setPattern(loaded))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [proposalId]);
  return pattern === null ? (
    <div style={{ aspectRatio: "4 / 3", borderRadius: 18, background: "var(--color-neutral-200)" }} />
  ) : (
    <Thumbnail pattern={pattern} label={label} />
  );
}

function StatusTag({ status }: { status: ApiSharedRequest["status"] }) {
  const t = useT();
  const tone = status === "accepted" ? "tag-accent-2" : status === "pending" ? "tag-neutral" : "tag-accent";
  return (
    <span className={`tag ${tone}`} style={{ fontSize: 11 }}>
      {t(`shared.request.status.${status}`)}
    </span>
  );
}

/**
 * The "Shared" tab of the Library (Lot 11, issue #78): the instance's shared
 * patterns, the requests about them, and what each profile may do — copy
 * into its library and ask the admins; admins rename, replace, remove and
 * decide on requests.
 */
export function SharedLibraryView({
  shared,
  isAdmin,
  myPatterns,
  onCopied,
  onOriginsChanged,
}: SharedLibraryViewProps) {
  const t = useT();
  const compareText = useCompareText();
  const [open, setOpen] = useState<SharedEntry | null>(null);
  const [mode, setMode] = useState<SheetMode>("menu");
  const [message, setMessage] = useState("");
  const [choice, setChoice] = useState("");
  const [editing, setEditing] = useState<{ name: string; labels: string[] }>({ name: "", labels: [] });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const knownLabels = allLabels(shared.entries.map((entry) => entry.pattern.labels), compareText);
  const byId = new Map(shared.entries.map((entry) => [entry.summary.id, entry]));
  const pending = shared.requests.filter((request) => request.status === "pending");
  // Admins decide on every pending request; anybody follows their own.
  const queue = isAdmin ? pending : [];
  const mine = shared.requests.filter(
    (request) => request.mine && request.status !== "cancelled" && !(isAdmin && request.status === "pending"),
  );

  const openSheet = (entry: SharedEntry): void => {
    setOpen(entry);
    setMode("menu");
    setMessage("");
    setChoice(myPatterns[0]?.id ?? "");
    setEditing({ name: entry.summary.name, labels: [...entry.summary.labels] });
    setError(null);
  };
  const close = (): void => {
    if (!busy) setOpen(null);
  };
  useEffect(() => {
    if (open === null) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !busy) setOpen(null);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, busy]);

  const run = async (action: () => Promise<void>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await shared.refresh();
      setOpen(null);
    } catch (caught) {
      setError(translateApiError(t, caught));
    } finally {
      setBusy(false);
    }
  };

  const settle = (request: ApiSharedRequest, action: "accept" | "reject" | "cancel"): void => {
    setRequestError(null);
    void settleSharedRequest(request.id, action)
      .then(() => Promise.all([shared.refresh(), action === "accept" ? onOriginsChanged() : undefined]))
      .catch((caught: unknown) => setRequestError(translateApiError(t, caught)));
  };

  if (shared.state === "loading") return null;
  if (shared.state === "unavailable") {
    return (
      <p className="text-muted" style={{ fontSize: 14 }}>
        {t("shared.unavailable")}
      </p>
    );
  }

  const requestLine = (request: ApiSharedRequest): string =>
    t(request.kind === "removal" ? "shared.request.removalLine" : "shared.request.replacementLine", {
      who: request.requested_by_name ?? t("shared.formerMember"),
      name: request.pattern_name,
    });

  const myPendingFor = (patternId: string): ApiSharedRequest[] =>
    shared.requests.filter(
      (request) => request.mine && request.status === "pending" && request.shared_pattern_id === patternId,
    );

  const block = (title: string, children: ReactNode): ReactNode => (
    <section style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
      <h3 style={{ margin: 0, fontSize: 16 }}>{title}</h3>
      {children}
    </section>
  );

  const sheetButton = (label: string, onClick: () => void, primary = false): ReactNode => (
    <button
      type="button"
      className={primary ? "btn btn-primary btn-block" : "btn btn-secondary btn-block"}
      style={{ minHeight: 48 }}
      disabled={busy}
      onClick={onClick}
    >
      {label}
    </button>
  );

  const choosePattern = (label: string): ReactNode =>
    myPatterns.length === 0 ? (
      <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>
        {t("shared.noOwnPattern")}
      </p>
    ) : (
      <label className="form-field">
        <span>{label}</span>
        <select
          className="input"
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
          style={{ minHeight: 46 }}
        >
          {myPatterns.map((pattern) => (
            <option key={pattern.id} value={pattern.id}>
              {pattern.name}
            </option>
          ))}
        </select>
      </label>
    );

  const messageField = (
    <label className="form-field">
      <span>{t("shared.request.message")}</span>
      <textarea
        className="input"
        rows={3}
        maxLength={1000}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        style={{ borderRadius: 18, padding: "10px 14px", resize: "vertical" }}
      />
    </label>
  );

  return (
    <>
      {requestError !== null && (
        <p role="alert" className="tag tag-accent" style={{ margin: "0 0 12px" }}>
          {requestError}
        </p>
      )}

      {queue.length > 0 &&
        block(
          t("shared.queue.title", { count: queue.length }),
          queue.map((request) => (
            <div key={request.id} className="panel" style={{ gap: 10 }}>
              <div style={{ fontSize: 14 }}>{requestLine(request)}</div>
              {request.message !== null && (
                <div className="text-muted" style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>
                  « {request.message} »
                </div>
              )}
              {request.kind === "replacement" && request.proposal_pattern_id !== null && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span className="text-muted" style={{ fontSize: 11 }}>
                      {t("shared.queue.current")}
                    </span>
                    {request.shared_pattern_id !== null && byId.has(request.shared_pattern_id) && (
                      <Thumbnail
                        pattern={byId.get(request.shared_pattern_id)!.pattern}
                        label={t("shared.queue.current")}
                      />
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span className="text-muted" style={{ fontSize: 11 }}>
                      {t("shared.queue.proposed")}
                    </span>
                    <ProposalThumbnail proposalId={request.proposal_pattern_id} label={t("shared.queue.proposed")} />
                  </div>
                </div>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ minHeight: 44, padding: "0 18px" }}
                  onClick={() => settle(request, "accept")}
                >
                  {t(request.kind === "removal" ? "shared.queue.acceptRemoval" : "shared.queue.acceptReplacement")}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ minHeight: 44, padding: "0 18px" }}
                  onClick={() => settle(request, "reject")}
                >
                  {t("shared.queue.reject")}
                </button>
              </div>
            </div>
          )),
        )}

      {mine.length > 0 &&
        block(
          t("shared.mine.title"),
          mine.map((request) => (
            <div
              key={request.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                padding: "10px 14px",
                borderRadius: 16,
                background: "var(--color-surface)",
              }}
            >
              <span style={{ fontSize: 13, minWidth: 0 }}>
                {t(request.kind === "removal" ? "shared.mine.removal" : "shared.mine.replacement", {
                  name: request.pattern_name,
                })}
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, flex: "none" }}>
                <StatusTag status={request.status} />
                {request.status === "pending" && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ minHeight: 36 }}
                    onClick={() => settle(request, "cancel")}
                  >
                    {t("shared.mine.cancel")}
                  </button>
                )}
              </span>
            </div>
          )),
        )}

      {shared.entries.length === 0 && (
        <p className="text-muted" style={{ fontSize: 14 }}>
          {t("shared.empty")}
        </p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 16 }}>
        {shared.entries.map((entry) => (
          <button
            key={entry.summary.id}
            type="button"
            className="card elev-sm"
            style={{ border: 0, cursor: "pointer", textAlign: "left", padding: 12, gap: 12 }}
            aria-haspopup="dialog"
            onClick={() => openSheet(entry)}
          >
            <Thumbnail pattern={entry.pattern} label={entry.summary.name} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="card-title">{entry.summary.name}</div>
              <div className="text-muted" style={{ fontSize: 12 }}>
                {t("library.patternMeta", {
                  size: `${entry.summary.width} × ${entry.summary.height}`,
                  colors: entry.summary.palette_count,
                })}
              </div>
              <div className="text-faint" style={{ fontSize: 11 }}>
                {entry.summary.contributed_by_name !== null
                  ? t("shared.addedBy", { name: entry.summary.contributed_by_name })
                  : t("shared.addedByFormer")}
              </div>
              {(entry.summary.labels.length > 0 || entry.summary.my_copy_ids.length > 0) && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {entry.summary.my_copy_ids.length > 0 && (
                    <span className="tag tag-accent-2" style={{ fontSize: 11 }}>
                      {t("shared.haveCopy")}
                    </span>
                  )}
                  {entry.summary.labels.map((label) => (
                    <span key={label} className="label-tag" style={{ fontSize: 11 }}>
                      {label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>

      {open !== null && (
        <div className="drawer-backdrop is-fixed" role="presentation" onClick={close}>
          <div
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label={t("library.actions", { name: open.summary.name })}
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
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: "var(--font-heading)",
                    fontSize: 18,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {open.summary.name}
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  {open.summary.contributed_by_name !== null
                    ? t("shared.addedBy", { name: open.summary.contributed_by_name })
                    : t("shared.addedByFormer")}
                </div>
              </div>
              <button type="button" className="btn btn-icon btn-secondary" onClick={close} aria-label={t("track.close")}>
                <CloseIcon size={18} />
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "6px 18px 22px", overflowY: "auto" }}>
              {mode === "menu" && (
                <>
                  {open.summary.my_copy_ids.length > 0 && (
                    <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>
                      {t("shared.haveCopy.hint")}
                    </p>
                  )}
                  {myPendingFor(open.summary.id).map((request) => (
                    <p key={request.id} className="text-muted" style={{ margin: 0, fontSize: 13 }}>
                      {t(request.kind === "removal" ? "shared.mine.removalPending" : "shared.mine.replacementPending")}
                    </p>
                  ))}
                  {sheetButton(
                    t("shared.copy"),
                    () =>
                      void run(async () => {
                        await copySharedPattern(open.summary.id, open.summary.name);
                        await onCopied();
                      }),
                    true,
                  )}
                  {isAdmin ? (
                    <>
                      {sheetButton(t("library.edit"), () => setMode("edit"))}
                      {sheetButton(t("shared.replace"), () => setMode("replace"))}
                      {sheetButton(t("shared.remove"), () => setMode("delete"))}
                    </>
                  ) : (
                    <>
                      {sheetButton(t("shared.propose"), () => setMode("propose"))}
                      {sheetButton(t("shared.askRemoval"), () => setMode("removal"))}
                    </>
                  )}
                </>
              )}

              {mode === "removal" && (
                <>
                  <p style={{ margin: 0, fontSize: 14 }}>{t("shared.askRemoval.hint")}</p>
                  {messageField}
                  {sheetButton(
                    t("shared.askRemoval.submit"),
                    () =>
                      void run(async () => {
                        await createSharedRequest({
                          kind: "removal",
                          shared_pattern_id: open.summary.id,
                          ...(message.trim() !== "" && { message: message.trim() }),
                        });
                      }),
                    true,
                  )}
                </>
              )}

              {mode === "propose" && (
                <>
                  <p style={{ margin: 0, fontSize: 14 }}>{t("shared.propose.hint")}</p>
                  {choosePattern(t("shared.propose.choose"))}
                  {messageField}
                  {myPatterns.length > 0 &&
                    sheetButton(
                      t("shared.propose.submit"),
                      () =>
                        void run(async () => {
                          await createSharedRequest({
                            kind: "replacement",
                            shared_pattern_id: open.summary.id,
                            proposal_pattern_id: choice,
                            ...(message.trim() !== "" && { message: message.trim() }),
                          });
                        }),
                      true,
                    )}
                </>
              )}

              {mode === "edit" && (
                <>
                  <label className="form-field">
                    <span>{t("library.edit.name")}</span>
                    <input
                      className="input"
                      style={{ minHeight: 46 }}
                      value={editing.name}
                      maxLength={200}
                      onChange={(event) => setEditing({ ...editing, name: event.target.value })}
                    />
                  </label>
                  <div className="form-field">
                    <span>{t("labels.title")}</span>
                    <LabelPicker
                      labels={editing.labels}
                      onChange={(labels) => setEditing({ ...editing, labels })}
                      known={knownLabels}
                    />
                  </div>
                  {sheetButton(
                    t("library.edit.save"),
                    () =>
                      void run(async () => {
                        await updateSharedPattern(open.summary.id, {
                          name: editing.name.trim(),
                          labels: editing.labels,
                        });
                      }),
                    true,
                  )}
                </>
              )}

              {mode === "replace" && (
                <>
                  <p style={{ margin: 0, fontSize: 14 }}>{t("shared.replace.hint")}</p>
                  {choosePattern(t("shared.replace.choose"))}
                  {myPatterns.length > 0 &&
                    sheetButton(
                      t("shared.replace.submit"),
                      () =>
                        void run(async () => {
                          await replaceSharedPattern(open.summary.id, choice);
                          await onOriginsChanged();
                        }),
                      true,
                    )}
                </>
              )}

              {mode === "delete" && (
                <>
                  <p style={{ margin: 0, fontSize: 14 }}>{t("shared.remove.confirm", { name: open.summary.name })}</p>
                  {sheetButton(
                    t("shared.remove.submit"),
                    () =>
                      void run(async () => {
                        await deleteSharedPattern(open.summary.id);
                        await onOriginsChanged();
                      }),
                    true,
                  )}
                </>
              )}

              {mode !== "menu" && sheetButton(t("library.cancel"), () => setMode("menu"))}

              {error !== null && (
                <p role="alert" className="tag tag-accent" style={{ margin: 0 }}>
                  {error}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
