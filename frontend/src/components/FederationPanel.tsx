import { useEffect, useState } from "react";

import { useT } from "../i18n";
import {
  createInvitation,
  fetchFederation,
  joinHost,
  leavePeer,
  renameInstance,
  translateApiError,
  ApiError,
  withdrawInvitation,
  type ApiFederation,
  type ApiPeer,
} from "../lib/api";

/**
 * Settings > "Linked sites", admins only (Lot 11b, issue #78): link this
 * instance with another self-hosted one so both share one shared library.
 *
 * The site that hosts the library invites; the other joins with the code.
 * Only the host must be reachable from the other server — the code carries
 * the address that server will use, by default the one the admin is using.
 */
export function FederationPanel() {
  const t = useT();
  const [state, setState] = useState<ApiFederation | null>(null);
  const [name, setName] = useState("");
  const [publicUrl, setPublicUrl] = useState(() => window.location.origin);
  const [trustAdmins, setTrustAdmins] = useState(true);
  const [code, setCode] = useState<string | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = async (): Promise<void> => {
    const loaded = await fetchFederation();
    setState(loaded);
    setName(loaded.instance_name);
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchFederation(controller.signal)
      .then((loaded) => {
        setState(loaded);
        setName(loaded.instance_name);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMessage(translateApiError(t, error));
      });
    return () => controller.abort();
  }, [t]);

  const run = (action: () => Promise<void>, done?: string): void => {
    setBusy(true);
    setMessage(null);
    action()
      .then(() => {
        if (done !== undefined) setMessage(done);
      })
      .catch((error: unknown) => setMessage(translateApiError(t, error)))
      .finally(() => setBusy(false));
  };

  const peerStatus = (peer: ApiPeer): string => {
    if (peer.last_error !== null) {
      return translateApiError(t, new ApiError(502, peer.last_error));
    }
    if (peer.role === "subscriber") return t("federation.peer.subscriberStatus");
    return peer.last_sync_at === null
      ? t("federation.peer.neverSynced")
      : t("federation.peer.syncedAt", { date: new Date(peer.last_sync_at).toLocaleString() });
  };

  return (
    <section className="panel" aria-labelledby="federation-title">
      <div>
        <div id="federation-title" className="panel-title">
          {t("federation.title")}
        </div>
        <div className="text-muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
          {t("federation.hint")}
        </div>
      </div>

      {message !== null && (
        <div role="status" className="text-muted" style={{ fontSize: 13 }}>
          {message}
        </div>
      )}

      <form
        style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}
        onSubmit={(event) => {
          event.preventDefault();
          run(() => renameInstance(name.trim()).then(reload), t("account.saved"));
        }}
      >
        <label className="form-field" style={{ flex: "1 1 200px" }}>
          <span>{t("federation.instanceName")}</span>
          <input className="input" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button
          type="submit"
          className="btn btn-secondary"
          style={{ minHeight: 44, padding: "0 18px" }}
          disabled={busy || state === null || name.trim() === state.instance_name}
        >
          {t("account.save")}
        </button>
      </form>

      {(state?.peers ?? []).length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {state!.peers.map((peer) => (
            <div
              key={peer.id}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 4,
                padding: "10px 14px",
                borderRadius: 16,
                background: "var(--color-surface)",
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 600 }}>{peer.name}</span>
              <span className="text-muted" style={{ fontSize: 12 }}>
                {t(peer.role === "host" ? "federation.peer.host" : "federation.peer.subscriber")}
                {peer.trust_admins && ` · ${t("federation.peer.trusted")}`}
              </span>
              <span className={peer.last_error !== null ? "form-error" : "text-muted"} style={{ fontSize: 12 }}>
                {peerStatus(peer)}
              </span>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ alignSelf: "flex-end", minHeight: 40, color: "var(--color-accent-700)" }}
                aria-label={t("federation.peer.leaveLabel", { name: peer.name })}
                disabled={busy}
                onClick={() => {
                  if (!window.confirm(t("federation.peer.leaveConfirm", { name: peer.name }))) return;
                  run(() => leavePeer(peer.id).then(reload));
                }}
              >
                {t("federation.peer.leave")}
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{t("federation.invite")}</div>
        <span className="text-muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
          {t("federation.invite.hint")}
        </span>
        <label className="form-field">
          <span>{t("federation.invite.url")}</span>
          <input
            className="input"
            type="url"
            value={publicUrl}
            onChange={(event) => setPublicUrl(event.target.value)}
          />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14 }}>
          <input
            type="checkbox"
            checked={trustAdmins}
            onChange={(event) => setTrustAdmins(event.target.checked)}
            style={{ width: 20, height: 20 }}
          />
          {t("federation.invite.trust")}
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ alignSelf: "flex-start", minHeight: 44, padding: "0 18px" }}
          disabled={busy}
          onClick={() =>
            run(async () => {
              const created = await createInvitation(publicUrl.trim(), trustAdmins);
              setCode(created.code);
              await reload();
            })
          }
        >
          {t("federation.invite.create")}
        </button>
        {code !== null && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <textarea
              className="input"
              readOnly
              rows={3}
              aria-label={t("federation.invite.code")}
              value={code}
              onFocus={(event) => event.target.select()}
              style={{ borderRadius: 18, padding: "10px 14px", fontFamily: "monospace", fontSize: 12 }}
            />
            <span className="text-muted" style={{ fontSize: 12 }}>
              {t("federation.invite.codeHint")}
            </span>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ alignSelf: "flex-start", minHeight: 40 }}
              onClick={() => void navigator.clipboard?.writeText(code).catch(() => undefined)}
            >
              {t("federation.invite.copy")}
            </button>
          </div>
        )}
        {(state?.invitations ?? []).length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {state!.invitations.map((invitation) => (
              <div
                key={invitation.id}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}
              >
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {t("federation.invite.pending", {
                    date: new Date(invitation.expires_at).toLocaleString(),
                  })}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ minHeight: 36 }}
                  disabled={busy}
                  onClick={() => run(() => withdrawInvitation(invitation.id).then(reload))}
                >
                  {t("federation.invite.withdraw")}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <form
        style={{ display: "flex", flexDirection: "column", gap: 10 }}
        onSubmit={(event) => {
          event.preventDefault();
          run(async () => {
            await joinHost(joinCode.trim());
            setJoinCode("");
            await reload();
          }, t("federation.join.done"));
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>{t("federation.join")}</div>
        <label className="form-field">
          <span>{t("federation.join.code")}</span>
          <textarea
            className="input"
            rows={3}
            required
            value={joinCode}
            onChange={(event) => setJoinCode(event.target.value)}
            style={{ borderRadius: 18, padding: "10px 14px", fontFamily: "monospace", fontSize: 12 }}
          />
        </label>
        <button
          type="submit"
          className="btn btn-secondary"
          style={{ alignSelf: "flex-start", minHeight: 44, padding: "0 18px" }}
          disabled={busy || joinCode.trim() === ""}
        >
          {t("federation.join.submit")}
        </button>
      </form>
    </section>
  );
}
