import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

import { request, type FullConfig } from "@playwright/test";

/**
 * Since profiles (Lot 10, issue #77), every API route but health and login
 * needs a logged-in profile. Before any spec runs, this creates the instance's
 * first admin — the e2e admin below — on a fresh instance (CI, or a fresh
 * `CSH_DATA_DIR`), or logs it in again on an instance it already set up, and
 * saves the session for every spec (`storageState`, `playwright.config.ts`).
 *
 * Set up on a fresh instance, this admin also receives the seeded demo
 * pattern (`backend/app/accounts.py::create_first_admin`), which the specs
 * keep using as before.
 */

/** Test-only credentials of the e2e instance — never a real account. */
export const E2E_ADMIN = {
  email: "e2e-admin@example.test",
  first_name: "E2E",
  last_name: "Admin",
  password: "e2e-admin-password",
};

export const STORAGE_STATE = "e2e/.auth/admin.json";

/** Sent on every API call from the specs, like the real frontend does
 * (`src/lib/api.ts`) — the server refuses state-changing requests without
 * it. */
export const CLIENT_HEADERS = { "X-CSH-Client": "e2e" };

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL;
  const api = await request.newContext({
    ...(baseURL !== undefined && { baseURL }),
    extraHTTPHeaders: CLIENT_HEADERS,
  });

  const status = (await (await api.get("/api/auth/status")).json()) as { setup_required: boolean };
  if (status.setup_required) {
    const setup = await api.post("/api/auth/setup", { data: E2E_ADMIN });
    if (!setup.ok()) throw new Error(`e2e admin setup failed: ${setup.status()} ${await setup.text()}`);
  } else {
    const profiles = (await (await api.get("/api/auth/profiles")).json()) as Array<{
      id: string;
      first_name: string;
    }>;
    const admin = profiles.find((profile) => profile.first_name === E2E_ADMIN.first_name);
    if (admin === undefined) {
      throw new Error(
        "This instance was set up without the e2e admin: run the e2e suite against a fresh " +
          "instance (empty CSH_DATA_DIR, demo pattern seeded) — see e2e/README.md.",
      );
    }
    const login = await api.post("/api/auth/login", {
      data: { user_id: admin.id, password: E2E_ADMIN.password },
    });
    if (!login.ok()) throw new Error(`e2e admin login failed: ${login.status()}`);
  }

  mkdirSync(dirname(STORAGE_STATE), { recursive: true });
  await api.storageState({ path: STORAGE_STATE });
  await api.dispose();
}
