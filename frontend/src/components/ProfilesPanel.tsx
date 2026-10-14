import { useEffect, useState, type FormEvent } from "react";

import { useT } from "../i18n";
import {
  createUser,
  deleteUser,
  listUsers,
  translateApiError,
  updateUser,
  type ApiAdminUser,
  type ApiRole,
} from "../lib/api";
import { useAuth, useCurrentUser } from "../state/auth";
import { Avatar } from "./Avatar";

const MIN_PASSWORD_LENGTH = 8;

interface ProfileFormValues {
  first_name: string;
  last_name: string;
  email: string;
  role: ApiRole;
  /** Initial password for a new profile; a reset (optional) for an existing one. */
  password: string;
}

const EMPTY_FORM: ProfileFormValues = {
  first_name: "",
  last_name: "",
  email: "",
  role: "user",
  password: "",
};

function ProfileForm({
  initial,
  creating,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: ProfileFormValues;
  creating: boolean;
  busy: boolean;
  onSubmit: (values: ProfileFormValues) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof ProfileFormValues>(key: K, value: ProfileFormValues[K]): void =>
    setValues((current) => ({ ...current, [key]: value }));

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if ((creating || values.password !== "") && values.password.length < MIN_PASSWORD_LENGTH) {
      setError(t("account.password.tooShort", { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    setError(null);
    onSubmit(values);
  };

  return (
    <form
      onSubmit={submit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: 14,
        borderRadius: 18,
        background: "var(--color-surface)",
      }}
    >
      <label className="form-field">
        <span>{t("account.firstName")}</span>
        <input
          className="input"
          required
          value={values.first_name}
          onChange={(event) => set("first_name", event.target.value)}
        />
      </label>
      <label className="form-field">
        <span>{t("account.lastName")}</span>
        <input
          className="input"
          required
          value={values.last_name}
          onChange={(event) => set("last_name", event.target.value)}
        />
      </label>
      <label className="form-field">
        <span>{t("account.email")}</span>
        <input
          className="input"
          type="email"
          required
          value={values.email}
          onChange={(event) => set("email", event.target.value)}
        />
      </label>
      <div className="form-field">
        <span>{t("profiles.role")}</span>
        <div className="seg" style={{ alignSelf: "flex-start" }}>
          {(["user", "admin"] as const).map((role) => (
            <button
              key={role}
              type="button"
              aria-pressed={values.role === role}
              onClick={() => set("role", role)}
            >
              {role === "admin" ? t("account.role.admin") : t("account.role.user")}
            </button>
          ))}
        </div>
      </div>
      <label className="form-field">
        <span>{creating ? t("profiles.initialPassword") : t("profiles.resetPassword")}</span>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          required={creating}
          value={values.password}
          onChange={(event) => set("password", event.target.value)}
        />
      </label>
      {error !== null && (
        <div role="alert" className="form-error">
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="submit"
          className="btn btn-primary"
          style={{ minHeight: 44, padding: "0 18px" }}
          disabled={busy}
        >
          {creating ? t("profiles.create") : t("account.save")}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ minHeight: 44 }}
          onClick={onCancel}
        >
          {t("library.cancel")}
        </button>
      </div>
    </form>
  );
}

/**
 * Settings > "Profile management", admins only (Lot 10, issue #77): add a
 * profile with an initial password, edit any profile (role included), reset
 * a password, delete a profile with its personal library. The server refuses
 * anything that would leave no admin (`error.last_admin`).
 */
export function ProfilesPanel() {
  const t = useT();
  const me = useCurrentUser();
  const { replaceUser, retry } = useAuth();
  const [users, setUsers] = useState<ApiAdminUser[] | null>(null);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = (): Promise<void> => listUsers().then(setUsers);

  useEffect(() => {
    const controller = new AbortController();
    listUsers(controller.signal)
      .then(setUsers)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMessage(translateApiError(t, error));
      });
    return () => controller.abort();
  }, [t]);

  const run = (action: () => Promise<void>): void => {
    setBusy(true);
    setMessage(null);
    action()
      .catch((error: unknown) => setMessage(translateApiError(t, error)))
      .finally(() => setBusy(false));
  };

  const create = (values: ProfileFormValues): void =>
    run(async () => {
      await createUser(values);
      setEditing(null);
      await reload();
    });

  const save = (user: ApiAdminUser, values: ProfileFormValues): void =>
    run(async () => {
      const updated = await updateUser(user.id, {
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        role: values.role,
        ...(values.password !== "" && { password: values.password }),
      });
      // Editing oneself (name, or stepping down as admin) updates the session
      // view at once: a former admin's Settings lose their admin sections.
      if (updated.id === me.id) replaceUser(updated);
      setEditing(null);
      await reload();
    });

  const remove = (user: ApiAdminUser): void => {
    if (!window.confirm(t("profiles.deleteConfirm", { name: user.first_name, count: user.pattern_count }))) {
      return;
    }
    run(async () => {
      await deleteUser(user.id);
      // Deleting one's own profile ends this session too.
      if (user.id === me.id) {
        retry();
        return;
      }
      await reload();
    });
  };

  return (
    <section className="panel" aria-labelledby="profiles-title">
      <div>
        <div id="profiles-title" className="panel-title">
          {t("profiles.title")}
        </div>
        <div className="text-muted" style={{ fontSize: 12 }}>
          {t("profiles.hint")}
        </div>
      </div>

      {message !== null && (
        <div role="alert" className="form-error">
          {message}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {(users ?? []).map((user) =>
          editing === user.id ? (
            <ProfileForm
              key={user.id}
              creating={false}
              busy={busy}
              initial={{
                first_name: user.first_name,
                last_name: user.last_name,
                email: user.email,
                role: user.role,
                password: "",
              }}
              onSubmit={(values) => save(user, values)}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <div
              key={user.id}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                padding: "10px 14px",
                borderRadius: 16,
                background: "var(--color-surface)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                <Avatar initials={user.initials} hue={user.avatar_hue} size="sm" />
                <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                  <span style={{ fontSize: 14 }}>
                    {user.first_name} {user.last_name}
                    {user.id === me.id && ` ${t("profiles.you")}`}
                  </span>
                  <span className="text-muted" style={{ fontSize: 12 }}>
                    {user.role === "admin" ? t("account.role.admin") : t("account.role.user")}
                    {" · "}
                    {t("profiles.patternCount", { count: user.pattern_count })}
                  </span>
                  <span
                    className="text-muted"
                    style={{
                      fontSize: 12,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {user.email}
                  </span>
                </div>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 4 }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ minHeight: 40 }}
                  aria-label={t("profiles.editLabel", { name: user.first_name })}
                  onClick={() => setEditing(user.id)}
                >
                  {t("profiles.edit")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ minHeight: 40, color: "var(--color-accent-700)" }}
                  aria-label={t("profiles.deleteLabel", { name: user.first_name })}
                  disabled={busy}
                  onClick={() => remove(user)}
                >
                  {t("profiles.delete")}
                </button>
              </div>
            </div>
          ),
        )}
      </div>

      {editing === "new" ? (
        <ProfileForm
          creating
          busy={busy}
          initial={EMPTY_FORM}
          onSubmit={create}
          onCancel={() => setEditing(null)}
        />
      ) : (
        <button
          type="button"
          className="btn btn-secondary"
          style={{ alignSelf: "flex-start", minHeight: 44, padding: "0 18px" }}
          onClick={() => setEditing("new")}
        >
          {t("profiles.add")}
        </button>
      )}
    </section>
  );
}
