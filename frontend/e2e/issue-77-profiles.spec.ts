import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { E2E_ADMIN } from "./global-setup";

/**
 * Issue #77 (Lot 10): profiles. An admin adds a profile from Settings with an
 * initial password; that profile logs in from "Who's stitching?", sees only
 * its own (empty) library and none of the admin sections; the last admin can
 * neither step down nor be deleted; an admin deletes the profile.
 *
 * The profile's own steps run in a fresh browser context with no saved
 * session, so they go through the real login flow. This spec also drops the
 * extra header the other specs send (`playwright.config.ts`): every request
 * here carries only what the real frontend adds itself (`src/lib/api.ts`) —
 * the specs' API calls are reads, which never need it.
 */

interface AdminUser {
  id: string;
  first_name: string;
  email: string;
  role: string;
}

/** Test-only password of the profile this spec creates. */
const PROFILE_PASSWORD = "zoe-e2e-password";

async function listUsers(request: APIRequestContext): Promise<AdminUser[]> {
  return (await (await request.get("/api/users")).json()) as AdminUser[];
}

async function freshPage(browser: Browser, baseURL: string | undefined): Promise<Page> {
  const context = await browser.newContext({
    ...(baseURL !== undefined && { baseURL }),
    locale: "fr-FR",
    viewport: { width: 375, height: 812 },
    // Contexts made in a test inherit the config's options, the e2e admin's
    // saved session included: start logged out.
    storageState: { cookies: [], origins: [] },
  });
  return context.newPage();
}

test.use({ viewport: { width: 375, height: 812 }, extraHTTPHeaders: {} });

test("an admin adds a profile, which logs in to its own private library", async ({
  page,
  request,
  browser,
  baseURL,
}) => {
  const runId = Date.now() % 100000;
  const firstName = `Zoé${runId}`;
  // ASCII: the browser's own `type="email"` validation refuses an accent.
  const email = `zoe${runId}@example.test`;

  // --- The admin adds the profile from Settings.
  await page.goto("/settings");
  const panel = page.getByRole("region", { name: "Gestion des profils" });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Ajouter un profil" }).click();
  await panel.getByLabel("Prénom").fill(firstName);
  await panel.getByLabel("Nom", { exact: true }).fill("Testeuse");
  await panel.getByLabel("Adresse e-mail").fill(email);
  await panel.getByLabel("Mot de passe initial").fill(PROFILE_PASSWORD);
  await panel.getByRole("button", { name: "Ajouter", exact: true }).click();
  await expect(panel.getByText(`${firstName} Testeuse`)).toBeVisible();

  const created = (await listUsers(request)).find((user) => user.email === email);
  expect(created?.role).toBe("user");

  // --- The new profile logs in from "Who's stitching?".
  const zoe = await freshPage(browser, baseURL);
  await zoe.goto("/");
  await expect(zoe.getByRole("heading", { name: "Qui brode ?" })).toBeVisible();
  await expect(zoe.getByRole("button", { name: E2E_ADMIN.first_name })).toBeVisible();
  await zoe.getByRole("button", { name: firstName }).click();

  const password = zoe.getByLabel(`Mot de passe de ${firstName}`);
  await password.fill("not-the-password");
  await zoe.getByRole("button", { name: "Entrer" }).click();
  await expect(zoe.getByRole("alert")).toHaveText("Mot de passe incorrect.");
  await password.fill(PROFILE_PASSWORD);
  await zoe.getByRole("button", { name: "Entrer" }).click();

  // Its own library: empty — neither the admin's patterns nor the client-made
  // demo ones.
  await expect(zoe.getByText("Aucun motif pour l'instant. Commencez par en importer un.")).toBeVisible();
  await expect(zoe.locator(".card-title")).toHaveCount(0);
  const ownPatterns = await zoe.evaluate(async () => (await (await fetch("/api/patterns")).json()) as unknown[]);
  expect(ownPatterns).toEqual([]);

  // No admin section in its Settings, and the server refuses admin routes.
  await zoe.goto("/settings");
  await expect(zoe.getByRole("region", { name: "Mon compte" })).toBeVisible();
  await expect(zoe.getByRole("region", { name: "Gestion des profils" })).toHaveCount(0);
  await expect(zoe.getByText("Exporter (.json)")).toHaveCount(0);
  const adminRoute = await zoe.evaluate(async () => (await fetch("/api/users")).status);
  expect(adminRoute).toBe(403);

  // A state-changing request without the app's header is refused, whatever
  // the session cookie (CSRF guard).
  const forged = await zoe.evaluate(async () =>
    (
      await fetch("/api/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name: "Mallory" }),
      })
    ).status,
  );
  expect(forged).toBe(403);

  // "Switch profile" goes back to the picker, with this profile picked.
  await zoe.getByRole("region", { name: "Mon compte" }).getByRole("button", { name: "Changer de profil" }).click();
  await expect(zoe.getByRole("heading", { name: "Qui brode ?" })).toBeVisible();
  await expect(zoe).toHaveURL(/\/$/);
  await expect(zoe.getByRole("button", { name: firstName })).toHaveAttribute("aria-pressed", "true");
  await zoe.context().close();

  // --- The admin deletes the profile (confirmation shows its library size).
  await page.reload();
  let confirmation = "";
  page.once("dialog", (dialog) => {
    confirmation = dialog.message();
    void dialog.accept();
  });
  await panel.getByRole("button", { name: `Supprimer le profil de ${firstName}` }).click();
  await expect(panel.getByText(`${firstName} Testeuse`)).toHaveCount(0);
  expect(confirmation).toContain("0 motif(s)");
  expect((await listUsers(request)).some((user) => user.email === email)).toBe(false);
});

test("the last admin can neither step down nor be deleted", async ({ page, request }) => {
  const admins = (await listUsers(request)).filter((user) => user.role === "admin");
  test.skip(admins.length !== 1, "Only meaningful while the e2e admin is the only admin");

  await page.goto("/settings");
  const panel = page.getByRole("region", { name: "Gestion des profils" });
  await panel.getByRole("button", { name: `Modifier le profil de ${E2E_ADMIN.first_name}` }).click();
  await panel.getByRole("button", { name: "Utilisateur", exact: true }).click();
  await panel.getByRole("button", { name: "Enregistrer" }).click();
  await expect(panel.getByRole("alert")).toContainText("il doit toujours rester au moins un administrateur");

  page.once("dialog", (dialog) => void dialog.accept());
  await panel.getByRole("button", { name: "Annuler" }).click();
  await panel.getByRole("button", { name: `Supprimer le profil de ${E2E_ADMIN.first_name}` }).click();
  await expect(panel.getByRole("alert")).toContainText("il doit toujours rester au moins un administrateur");

  const me = (await (await request.get("/api/auth/me")).json()) as { role: string };
  expect(me.role).toBe("admin");
});
