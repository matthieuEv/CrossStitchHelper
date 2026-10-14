import { useState, type FormEvent } from "react";

import { useT } from "../i18n";
import { changeMyPassword, translateApiError, updateMe } from "../lib/api";
import { useAuth, useCurrentUser } from "../state/auth";
import { Avatar } from "./Avatar";
import { useSwitchProfile } from "./ProfileMenu";

const MIN_PASSWORD_LENGTH = 8;

/**
 * Settings > "My account" (Lot 10, issue #77): every profile edits its own
 * information and password here — never its role, which only an admin
 * changes (`ProfilesPanel`).
 */
export function AccountPanel() {
  const t = useT();
  const user = useCurrentUser();
  const { replaceUser } = useAuth();
  const { busy: switching, switchNow } = useSwitchProfile();

  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  const [email, setEmail] = useState(user.email);
  const [infoBusy, setInfoBusy] = useState(false);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const [changingPassword, setChangingPassword] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);

  const infoChanged =
    firstName !== user.first_name || lastName !== user.last_name || email !== user.email;

  const saveInfo = (event: FormEvent): void => {
    event.preventDefault();
    setInfoBusy(true);
    setInfoMessage(null);
    updateMe({ first_name: firstName, last_name: lastName, email })
      .then((updated) => {
        replaceUser(updated);
        setInfoMessage(t("account.saved"));
      })
      .catch((error: unknown) => setInfoMessage(translateApiError(t, error)))
      .finally(() => setInfoBusy(false));
  };

  const savePassword = (event: FormEvent): void => {
    event.preventDefault();
    if (next.length < MIN_PASSWORD_LENGTH) {
      setPasswordMessage(t("account.password.tooShort", { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (next !== confirmation) {
      setPasswordMessage(t("account.password.mismatch"));
      return;
    }
    setPasswordBusy(true);
    setPasswordMessage(null);
    changeMyPassword(current, next)
      .then(() => {
        setCurrent("");
        setNext("");
        setConfirmation("");
        setChangingPassword(false);
        setPasswordMessage(t("account.password.changed"));
      })
      .catch((error: unknown) => setPasswordMessage(translateApiError(t, error)))
      .finally(() => setPasswordBusy(false));
  };

  return (
    <section className="panel" aria-labelledby="account-title">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Avatar initials={user.initials} hue={user.avatar_hue} />
        <div style={{ minWidth: 0 }}>
          <div id="account-title" className="panel-title">
            {t("account.title")}
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {user.role === "admin" ? t("account.role.admin") : t("account.role.user")}
          </div>
        </div>
      </div>

      <form onSubmit={saveInfo} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label className="form-field">
          <span>{t("account.firstName")}</span>
          <input
            className="input"
            autoComplete="given-name"
            required
            value={firstName}
            onChange={(event) => setFirstName(event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>{t("account.lastName")}</span>
          <input
            className="input"
            autoComplete="family-name"
            required
            value={lastName}
            onChange={(event) => setLastName(event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>{t("account.email")}</span>
          <input
            className="input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        {infoMessage !== null && (
          <div role="status" className="text-muted" style={{ fontSize: 13 }}>
            {infoMessage}
          </div>
        )}
        <button
          type="submit"
          className="btn btn-secondary"
          style={{ alignSelf: "flex-start", minHeight: 44, padding: "0 18px" }}
          disabled={infoBusy || !infoChanged}
        >
          {t("account.save")}
        </button>
      </form>

      {changingPassword ? (
        <form onSubmit={savePassword} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label className="form-field">
            <span>{t("account.password.current")}</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </label>
          <label className="form-field">
            <span>{t("account.password.new")}</span>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              required
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
          </label>
          <label className="form-field">
            <span>{t("account.password.confirm")}</span>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="submit"
              className="btn btn-secondary"
              style={{ minHeight: 44, padding: "0 18px" }}
              disabled={passwordBusy}
            >
              {t("account.password.submit")}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ minHeight: 44 }}
              onClick={() => setChangingPassword(false)}
            >
              {t("library.cancel")}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="btn btn-secondary"
          style={{ alignSelf: "flex-start", minHeight: 44, padding: "0 18px" }}
          onClick={() => {
            setPasswordMessage(null);
            setChangingPassword(true);
          }}
        >
          {t("account.password.change")}
        </button>
      )}
      {passwordMessage !== null && (
        <div role="status" className="text-muted" style={{ fontSize: 13 }}>
          {passwordMessage}
        </div>
      )}

      <button
        type="button"
        className="btn btn-ghost"
        style={{ alignSelf: "flex-start", minHeight: 44 }}
        disabled={switching}
        onClick={() => void switchNow()}
      >
        {t("profile.switch")}
      </button>
    </section>
  );
}
