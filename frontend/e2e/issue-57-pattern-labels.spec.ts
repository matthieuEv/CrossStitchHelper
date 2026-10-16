import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Issue #57: labels are given to a pattern on the import summary step (the
 * library's existing ones offered with one tap), shown on its card, used to
 * filter the Library ("All" by default), and edited — with the name — from
 * the card's "⋯" actions. An unused label disappears from the filters.
 */

interface PatternSummary {
  id: string;
  name: string;
  labels: string[];
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";
const IMPORTED_NAME = "Koi e2e #57";
const RENAMED = "Koi renommé e2e #57";
// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

async function fetchPatterns(request: APIRequestContext): Promise<PatternSummary[]> {
  return (await (await request.get("/api/patterns")).json()) as PatternSummary[];
}

async function removeLeftovers(request: APIRequestContext): Promise<void> {
  for (const pattern of await fetchPatterns(request)) {
    if (pattern.name === IMPORTED_NAME || pattern.name === RENAMED) {
      await request.delete(`/api/patterns/${pattern.id}`);
    }
  }
}

test.use({ viewport: { width: 375, height: 812 } });

test("labels are chosen at import, filter the library, and can be edited", async ({
  page,
  request,
}) => {
  await removeLeftovers(request);
  // An existing label for the summary step to offer.
  await request.patch(`/api/patterns/${DEMO_PATTERN_ID}`, { data: { labels: ["Mini"] } });

  try {
    // Import a pattern by hand, up to the summary step.
    await page.goto("/import");
    await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
      name: "koi.png",
      mimeType: "image/png",
      buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
    });
    await expect(page.getByText("Colonnes")).toBeVisible();
    const [columnsInput, rowsInput] = await page.locator("input.input").all();
    await columnsInput!.fill("4");
    await rowsInput!.fill("3");
    await page.getByRole("button", { name: "Continuer", exact: true }).click();
    await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
    await page.getByRole("button", { name: "Continuer", exact: true }).click();

    const nameField = page.getByRole("textbox", { name: "Nom du motif" });
    await nameField.fill(IMPORTED_NAME);
    // The existing "Mini" with one tap; "mer" typed, then "MINI" again,
    // which must not make a second "Mini".
    await page.getByRole("button", { name: "Ajouter le label « Mini »" }).click();
    const newLabel = page.getByRole("textbox", { name: "Nouveau label" });
    await newLabel.fill("Mer");
    await newLabel.press("Enter");
    await newLabel.fill("MINI");
    await page.getByRole("button", { name: "Ajouter", exact: true }).click();
    await expect(page.getByRole("button", { name: /Retirer le label/ })).toHaveCount(2);
    await page.getByRole("button", { name: "Ajouter et commencer" }).click();
    await expect(page).toHaveURL(/\/track\//);

    const imported = (await fetchPatterns(request)).find((p) => p.name === IMPORTED_NAME);
    expect(imported?.labels).toEqual(["Mini", "Mer"]);

    // Library: the card shows its labels, the filters list every label.
    await page.getByRole("button", { name: "Motifs", exact: true }).click();
    const filters = page.getByRole("group", { name: "Filtrer par label" });
    const all = filters.getByRole("button", { name: "Tous" });
    await expect(all).toHaveAttribute("aria-pressed", "true");
    await expect(filters.getByRole("button", { name: "Mer" })).toBeVisible();
    const titles = page.locator(".card-title");

    await filters.getByRole("button", { name: "Mer" }).click();
    await expect(titles).toHaveText([IMPORTED_NAME]);
    await filters.getByRole("button", { name: "Mini" }).click();
    await expect(titles).toHaveCount(2);
    await all.click();
    await expect(titles).toHaveCount((await fetchPatterns(request)).length);

    // Edit: rename, and remove "Mer" — the only pattern carrying it.
    await page.getByRole("button", { name: `Actions pour « ${IMPORTED_NAME} »` }).click();
    const sheet = page.getByRole("dialog", { name: `Actions pour « ${IMPORTED_NAME} »` });
    await sheet.getByRole("button", { name: "Modifier" }).click();
    await sheet.getByRole("textbox", { name: "Nom du motif" }).fill(RENAMED);
    await sheet.getByRole("button", { name: "Retirer le label « Mer »" }).click();
    await sheet.getByRole("button", { name: "Enregistrer" }).click();
    await expect(sheet).toBeHidden();

    await expect(page.locator(".card-title", { hasText: RENAMED })).toBeVisible();
    await expect(filters.getByRole("button", { name: "Mer" })).toHaveCount(0);
    const renamed = (await fetchPatterns(request)).find((p) => p.name === RENAMED);
    expect(renamed?.labels).toEqual(["Mini"]);
  } finally {
    await removeLeftovers(request);
    await request.patch(`/api/patterns/${DEMO_PATTERN_ID}`, { data: { labels: [] } });
  }
});
