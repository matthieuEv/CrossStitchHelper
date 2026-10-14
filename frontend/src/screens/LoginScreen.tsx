import { useState, type FormEvent } from "react";

import { Avatar } from "../components/Avatar";
import { useT } from "../i18n";
import { translateApiError, type ApiProfileCard } from "../lib/api";
import { useAuth } from "../state/auth";

interface LoginScreenProps {
  profiles: ApiProfileCard[];
  /** The profile last used on this device, picked in advance. */
  preferredId: string | null;
}

/**
 * "Who's stitching?" (Lot 10, issue #77): one tile per profile, then that
 * profile's password. Profiles are created by an admin only — there is no
 * "add a profile" tile.
 */
export function LoginScreen({ profiles, preferredId }: LoginScreenProps) {
  const t = useT();
  const { logIn } = useAuth();
  const initial =
    profiles.find((profile) => profile.id === preferredId) ??
    (profiles.length === 1 ? profiles[0] : undefined);
  const [selected, setSelected] = useState<ApiProfileCard | null>(initial ?? null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = (profile: ApiProfileCard): void => {
    setSelected(profile);
    setPassword("");
    setError(null);
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (selected === null || password === "") return;
    setBusy(true);
    setError(null);
    logIn(selected.id, password).catch((caught: unknown) => {
      setError(translateApiError(t, caught));
      setBusy(false);
    });
  };

  return (
    <main className="auth-screen">
      <h1 style={{ margin: 0, textAlign: "center" }}>{t("auth.who.title")}</h1>

      <div className="profile-picker" role="group" aria-label={t("auth.who.title")}>
        {profiles.map((profile) => (
          <button
            key={profile.id}
            type="button"
            className="profile-tile"
            aria-pressed={selected?.id === profile.id}
            onClick={() => choose(profile)}
          >
            <Avatar initials={profile.initials} hue={profile.avatar_hue} size="lg" />
            {profile.first_name}
          </button>
        ))}
      </div>

      {selected !== null && (
        <form className="auth-card" onSubmit={submit}>
          <label className="form-field">
            <span>{t("auth.who.password", { name: selected.first_name })}</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
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
            style={{ minHeight: 52 }}
            disabled={busy || password === ""}
          >
            {t("auth.who.submit")}
          </button>
        </form>
      )}
    </main>
  );
}
