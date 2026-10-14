/**
 * Who is using the application (Lot 10, issue #77).
 *
 * At startup the server says whether the instance still needs its first
 * admin (first launch), whether this device has a valid session cookie, or
 * neither ("Who's stitching?" screen). The session itself lives in an
 * HttpOnly cookie the page cannot read; the only thing kept on the device is
 * the last profile's public card and name (`localStorage`), so tracking keeps
 * working offline for that profile, from its own offline database
 * (`lib/db.ts`).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  fetchAuthStatus,
  fetchProfiles,
  login,
  logout,
  setUnauthorizedListener,
  setupFirstAdmin,
  syncProgress,
  type ApiProfileCard,
  type ApiProfileFields,
  type ApiUser,
} from "../lib/api";
import {
  drainLegacyOfflineDatabase,
  flushPendingOps,
  openOfflineDatabase,
  type SendQueuedOps,
} from "../lib/db";

const LAST_PROFILE_KEY = "csh.lastProfile";

export type AuthState =
  | { kind: "loading" }
  /** First launch: the instance has no profile yet. */
  | { kind: "setup" }
  /** "Who's stitching?": `preferredId` is the profile last used here. */
  | { kind: "login"; profiles: ApiProfileCard[]; preferredId: string | null }
  /** No server, and no profile ever used on this device. */
  | { kind: "unreachable" }
  | { kind: "ready"; user: ApiUser; offline: boolean };

interface AuthContextValue {
  state: AuthState;
  logIn: (userId: string, password: string) => Promise<void>;
  setUp: (fields: ApiProfileFields & { password: string }) => Promise<void>;
  /** Sends this profile's queued progress changes; returns how many could
   * not be sent (server unreachable) — they stay on this device, in this
   * profile's database, until its next login. */
  flushQueued: () => Promise<number>;
  /** Back to "Who's stitching?". */
  switchProfile: () => Promise<void>;
  /** After the profile edited its own information (`Settings`). */
  replaceUser: (user: ApiUser) => void;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readLastProfile(): ApiUser | null {
  try {
    const raw = window.localStorage.getItem(LAST_PROFILE_KEY);
    return raw === null ? null : (JSON.parse(raw) as ApiUser);
  } catch {
    return null;
  }
}

function writeLastProfile(user: ApiUser): void {
  try {
    window.localStorage.setItem(LAST_PROFILE_KEY, JSON.stringify(user));
  } catch {
    // Private browsing or storage full: only the offline fallback is lost.
  }
}

/** Sends one pattern's queued operations; a 404 means the pattern is gone
 * (deleted, or not this profile's), so those operations never will be. */
const sendQueuedOps: SendQueuedOps = async (patternId, baseVersion, ops) => {
  try {
    await syncProgress(
      patternId,
      baseVersion,
      ops.map((op) => ({ layer: op.layer ?? "full", index: op.index, stitched: op.stitched })),
    );
    return true;
  } catch (error) {
    return error instanceof ApiError && error.status === 404;
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ kind: "loading" });

  const enter = useCallback((user: ApiUser, offline: boolean) => {
    writeLastProfile(user);
    openOfflineDatabase(user.id);
    setState({ kind: "ready", user, offline });
    // The single-profile versions kept one database for everything: its
    // unsent changes belong to whoever received the old patterns — the first
    // admin (`backend/app/accounts.py::create_first_admin`).
    if (!offline && user.role === "admin") void drainLegacyOfflineDatabase(sendQueuedOps);
  }, []);

  const showLogin = useCallback(async () => {
    try {
      const profiles = await fetchProfiles();
      setState({ kind: "login", profiles, preferredId: readLastProfile()?.id ?? null });
    } catch {
      setState({ kind: "unreachable" });
    }
  }, []);

  const start = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const status = await fetchAuthStatus();
      if (status.setup_required) setState({ kind: "setup" });
      else if (status.user !== null) enter(status.user, false);
      else await showLogin();
    } catch {
      // No server: carry on offline as the profile last used on this
      // device, from its own offline cache — tracking must not depend on
      // the network (specification §3.1).
      const last = readLastProfile();
      if (last !== null) enter(last, true);
      else setState({ kind: "unreachable" });
    }
  }, [enter, showLogin]);

  useEffect(() => {
    void start();
  }, [start]);

  useEffect(() => {
    // Session ended elsewhere (password reset by an admin, profile deleted,
    // expiry): back to the login screen rather than failing request by
    // request.
    setUnauthorizedListener(() => void showLogin());
    return () => setUnauthorizedListener(null);
  }, [showLogin]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      logIn: async (userId, password) => {
        enter(await login(userId, password), false);
      },
      setUp: async (fields) => {
        enter(await setupFirstAdmin(fields), false);
      },
      flushQueued: () => flushPendingOps(sendQueuedOps),
      switchProfile: async () => {
        try {
          await logout();
        } catch {
          // Unreachable server: the cookie stays, but this screen still
          // leaves the profile — logging in again will replace it.
        }
        // The next profile starts from its library, not from a screen (or a
        // pattern URL) of the previous one.
        window.history.replaceState(null, "", "/");
        await showLogin();
      },
      replaceUser: (user) => {
        writeLastProfile(user);
        setState((current) => (current.kind === "ready" ? { ...current, user } : current));
      },
      retry: () => void start(),
    }),
    [state, enter, showLogin, start],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth outside AuthProvider");
  return value;
}

/** The logged-in profile — only inside the application proper, which is
 * mounted once a profile is `ready` (`AuthGate`, `main.tsx`). */
export function useCurrentUser(): ApiUser {
  const { state } = useAuth();
  if (state.kind !== "ready") throw new Error("useCurrentUser without a logged-in profile");
  return state.user;
}
