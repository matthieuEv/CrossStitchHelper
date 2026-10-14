import { App } from "./App";
import { useT } from "./i18n";
import { LoginScreen } from "./screens/LoginScreen";
import { SetupScreen } from "./screens/SetupScreen";
import { useAuth } from "./state/auth";

/**
 * What to show before the application proper (Lot 10): first launch, "Who's
 * stitching?", or the application once a profile is logged in. The
 * application is keyed by the profile, so switching profile on a shared
 * device starts from a clean state — library, open pattern, undo history —
 * with nothing of the previous profile left in memory.
 */
export function AuthGate() {
  const t = useT();
  const { state, retry } = useAuth();

  switch (state.kind) {
    case "loading":
      return (
        <main className="auth-screen" aria-busy="true">
          <span className="spinner" aria-label={t("auth.loading")} />
        </main>
      );
    case "setup":
      return <SetupScreen />;
    case "login":
      return <LoginScreen profiles={state.profiles} preferredId={state.preferredId} />;
    case "unreachable":
      return (
        <main className="auth-screen">
          <p className="text-muted" style={{ maxWidth: 360, textAlign: "center", lineHeight: 1.5 }}>
            {t("auth.unreachable")}
          </p>
          <button type="button" className="btn btn-primary" style={{ minHeight: 48, padding: "0 22px" }} onClick={retry}>
            {t("auth.retry")}
          </button>
        </main>
      );
    case "ready":
      return <App key={state.user.id} />;
  }
}
