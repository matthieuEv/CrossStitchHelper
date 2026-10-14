import { defineConfig, devices } from "@playwright/test";

import { CLIENT_HEADERS, STORAGE_STATE } from "./e2e/global-setup";

/**
 * e2e tests against a real instance (backend + frontend), not mocks — this is
 * what verifies the roadmap's "done when" criteria, in particular those
 * touching persistence and synchronisation (Lot 1).
 *
 * Starts no server itself: the backend (SQLite + seeded demo pattern) and the
 * frontend must already be running — see `e2e/README.md` for the local
 * procedure and `.github/workflows/ci.yml` for the CI one (against the built
 * Docker image).
 *
 * Every spec runs logged in as the e2e admin (Lot 10): `e2e/global-setup.ts`
 * sets the instance up and saves that session.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    // The app picks its language from the browser's (FR/EN i18n, see
    // CLAUDE.md); the tests pin French so as not to depend on the default
    // locale of the machine running them.
    locale: "fr-FR",
    storageState: STORAGE_STATE,
    extraHTTPHeaders: CLIENT_HEADERS,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
