import { defineConfig, devices } from "@playwright/test";

/**
 * Tests e2e contre une instance réelle (backend + frontend), pas des mocks —
 * c'est ce qui vérifie les critères "terminé quand" du roadmap, en particulier
 * ceux qui touchent à la persistance et à la synchronisation (Lot 1).
 *
 * Ne démarre aucun serveur lui-même : le backend (SQLite + motif de
 * démonstration seedé) et le frontend doivent déjà tourner — voir
 * `e2e/README.md` pour la procédure locale et `.github/workflows/ci.yml`
 * pour celle de la CI (contre l'image Docker construite).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    // L'app choisit sa langue selon celle du navigateur (i18n FR/EN, voir
    // CLAUDE.md) ; les tests fixent le français pour ne pas dépendre de la
    // locale par défaut de la machine qui les exécute.
    locale: "fr-FR",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
