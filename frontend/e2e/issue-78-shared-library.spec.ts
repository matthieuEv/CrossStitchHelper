import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

/**
 * Issue #78, first stage (Lot 11a): the shared library on one instance. An
 * admin shares a pattern; a regular profile copies it into its own library
 * and asks for its removal; the admin, warned by the counter on the "Shared"
 * tab, grants it — the copy stays. Then an admin replaces a shared pattern's
 * content: the profile's copy shows "Update", and updating keeps it.
 */

interface PatternSummary {
  id: string;
  name: string;
  origin_pattern_id?: string | null;
  update_available?: boolean;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";
/** Test-only password of the profile this spec creates. */
const PROFILE_PASSWORD = "lou-e2e-password";

async function myPatterns(request: APIRequestContext): Promise<PatternSummary[]> {
  return (await (await request.get("/api/patterns")).json()) as PatternSummary[];
}

async function loginAs(browser: Browser, baseURL: string | undefined, firstName: string): Promise<Page> {
  const context = await browser.newContext({
    ...(baseURL !== undefined && { baseURL }),
    locale: "fr-FR",
    viewport: { width: 375, height: 812 },
    storageState: { cookies: [], origins: [] },
  });
  const page = await context.newPage();
  await page.goto("/");
  await page.getByRole("button", { name: firstName, exact: true }).click();
  await page.getByLabel(`Mot de passe de ${firstName}`).fill(PROFILE_PASSWORD);
  await page.getByRole("button", { name: "Entrer" }).click();
  await expect(page.getByRole("tab", { name: "Mes motifs" })).toBeVisible();
  return page;
}

test.use({ viewport: { width: 375, height: 812 } });

test("share, copy, removal request granted by an admin; replaced content updates the copy", async ({
  page,
  request,
  browser,
  baseURL,
}) => {
  const runId = Date.now() % 100000;
  const firstName = `Lou${runId}`;
  const sharedName = `e2e partage ${runId}`;

  // A pattern of the admin's own, to share (never the demo itself: other
  // specs rely on it staying a plain personal pattern).
  const duplicated = await request.post(`/api/patterns/${DEMO_PATTERN_ID}/duplicate`, {
    data: { name: sharedName },
  });
  expect(duplicated.ok()).toBe(true);
  const created = await request.post("/api/users", {
    data: {
      email: `lou${runId}@example.test`,
      first_name: firstName,
      last_name: "Testeuse",
      password: PROFILE_PASSWORD,
    },
  });
  expect(created.ok()).toBe(true);
  const profileId = ((await created.json()) as { id: string }).id;

  try {
    // --- The admin shares it from the card's "⋯".
    await page.goto("/");
    await page.getByRole("button", { name: `Actions pour « ${sharedName} »` }).click();
    const sheet = page.getByRole("dialog", { name: `Actions pour « ${sharedName} »` });
    await sheet.getByRole("button", { name: "Partager", exact: true }).click();
    await expect(sheet.getByText(/Ne partagez que des motifs/)).toBeVisible();
    await sheet.getByRole("button", { name: "Partager", exact: true }).click();
    await expect(sheet).toBeHidden();

    // --- The profile copies it, then asks for its removal.
    const lou = await loginAs(browser, baseURL, firstName);
    await lou.getByRole("tab", { name: "Partagés" }).click();
    await lou.getByRole("button", { name: new RegExp(sharedName) }).click();
    const louSheet = lou.getByRole("dialog", { name: `Actions pour « ${sharedName} »` });
    await louSheet.getByRole("button", { name: "Copier dans ma bibliothèque" }).click();
    await expect(lou.getByRole("tab", { name: "Mes motifs" })).toHaveAttribute("aria-selected", "true");
    await expect(lou.locator(".card-title", { hasText: sharedName })).toBeVisible();

    await lou.getByRole("tab", { name: "Partagés" }).click();
    await lou.getByRole("button", { name: new RegExp(sharedName) }).click();
    await louSheet.getByRole("button", { name: "Demander la suppression" }).click();
    await louSheet.getByLabel("Message (facultatif)").fill("Doublon");
    await louSheet.getByRole("button", { name: "Envoyer la demande" }).click();
    const louRequests = lou.getByRole("heading", { name: "Mes demandes" }).locator("..");
    await expect(louRequests.getByText(`Suppression de « ${sharedName} »`)).toBeVisible();
    await expect(louRequests.getByText("En attente")).toBeVisible();

    // --- The admin sees the counter, then grants the removal.
    await page.reload();
    const sharedTab = page.getByRole("tab", { name: /Partagés/ });
    await expect(sharedTab.locator(".tab-badge")).toBeVisible();
    await sharedTab.click();
    const queued = page.locator(".panel", { hasText: `demande la suppression de « ${sharedName} »` });
    await expect(queued.getByText("« Doublon »")).toBeVisible();
    await queued.getByRole("button", { name: "Supprimer le motif" }).click();
    await expect(queued).toHaveCount(0);
    await expect(page.getByRole("button", { name: new RegExp(sharedName) })).toHaveCount(0);

    // The profile learns the outcome; its copy stays, unlinked.
    await lou.reload();
    await lou.getByRole("tab", { name: "Partagés" }).click();
    await expect(louRequests.getByText("Acceptée")).toBeVisible();
    const louOwn = await lou.evaluate(
      async () => (await (await fetch("/api/patterns")).json()) as Array<{ name: string; origin_pattern_id: string | null }>,
    );
    expect(louOwn.find((pattern) => pattern.name === sharedName)?.origin_pattern_id).toBeNull();

    // --- Replaced content: the copy shows "Update", and updating clears it.
    await page.getByRole("tab", { name: "Mes motifs" }).click();
    await page.getByRole("button", { name: `Actions pour « ${sharedName} »` }).click();
    // The admin's own pattern lost its link with the removal: share it again.
    await sheet.getByRole("button", { name: "Partager", exact: true }).click();
    await sheet.getByRole("button", { name: "Partager", exact: true }).click();
    await expect(sheet).toBeHidden();

    await lou.getByRole("tab", { name: "Partagés" }).click();
    await lou.reload();
    await lou.getByRole("tab", { name: "Partagés" }).click();
    await lou.getByRole("button", { name: new RegExp(sharedName) }).click();
    await louSheet.getByRole("button", { name: "Copier dans ma bibliothèque" }).click();
    await expect(lou.locator(".card-title", { hasText: sharedName })).toHaveCount(2);

    await page.getByRole("tab", { name: /Partagés/ }).click();
    await page.getByRole("button", { name: new RegExp(sharedName) }).click();
    const adminSheet = page.getByRole("dialog", { name: `Actions pour « ${sharedName} »` });
    await adminSheet.getByRole("button", { name: "Remplacer par un de mes motifs" }).click();
    await adminSheet.getByLabel("Motif de ma bibliothèque").selectOption({ label: sharedName });
    await adminSheet.getByRole("button", { name: "Remplacer", exact: true }).click();
    await expect(adminSheet).toBeHidden();

    await lou.reload();
    const badge = lou.locator(".update-dot");
    await expect(badge).toHaveCount(1);
    const updatedCard = lou.locator("div", { has: badge }).filter({ has: lou.locator(".library-card-more") }).last();
    await updatedCard.locator(".library-card-more").click();
    await lou.getByRole("button", { name: "Mettre à jour" }).click();
    await expect(lou.locator(".update-dot")).toHaveCount(0);

    await lou.context().close();
  } finally {
    // Leave the instance as found: the profile goes with its library; shared
    // patterns of this run are removed.
    await request.delete(`/api/users/${profileId}`);
    const library = (await (await request.get("/api/shared")).json()) as {
      patterns: Array<{ id: string; name: string }>;
    };
    for (const pattern of library.patterns.filter((p) => p.name === sharedName)) {
      await request.delete(`/api/shared/patterns/${pattern.id}`);
    }
    for (const pattern of (await myPatterns(request)).filter((p) => p.name === sharedName)) {
      await request.delete(`/api/patterns/${pattern.id}`);
    }
  }
});
