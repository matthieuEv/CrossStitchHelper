import { useState, type FormEvent } from "react";

import { useT } from "../i18n";
import { translateApiError } from "../lib/api";
import { useAuth } from "../state/auth";

const MIN_PASSWORD_LENGTH = 8;

/**
 * First launch (Lot 10, issue #77): the instance has no profile yet, so its
 * first one — necessarily an admin — is created here. Whatever the instance
 * already held (an upgrade from a single-user version) becomes that admin's.
 */
export function SetupScreen() {
  const t = useT();
  const { setUp } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(t("account.password.tooShort", { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (password !== confirmation) {
      setError(t("account.password.mismatch"));
      return;
    }
    setBusy(true);
    setError(null);
    setUp({ first_name: firstName, last_name: lastName, email, password }).catch(
      (caught: unknown) => {
        setError(translateApiError(t, caught));
        setBusy(false);
      },
    );
  };

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <h1 style={{ margin: 0 }}>{t("auth.setup.title")}</h1>
        <p className="text-muted" style={{ margin: "0 0 6px", fontSize: 14, lineHeight: 1.5 }}>
          {t("auth.setup.intro")}
        </p>
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
        <label className="form-field">
          <span>{t("account.password")}</span>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
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
        {error !== null && (
          <div role="alert" className="form-error">
            {error}
          </div>
        )}
        <button
          type="submit"
          className="btn btn-primary btn-block"
          style={{ minHeight: 52, marginTop: 6 }}
          disabled={busy}
        >
          {t("auth.setup.submit")}
        </button>
      </form>
    </main>
  );
}
