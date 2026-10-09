import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Issue #56: the Library's "Sort" button opens a menu (recent activity, name,
 * progress) that really reorders the patterns, and the choice survives a
 * reload on this device.
 */

interface PatternSummary {
  id: string;
  name: string;
  updated_at: string;
}

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

async function fetchPatterns(request: APIRequestContext): Promise<PatternSummary[]> {
  return (await (await request.get("/api/patterns")).json()) as PatternSummary[];
}

/** Imports a small hand-painted pattern through the wizard (Lot 2 flow). */
async function importPattern(page: Page, name: string): Promise<void> {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "grille-test.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("4");
  await rowsInput!.fill("4");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  await page.mouse.move(box.x + 10, box.y + 10);
  await page.mouse.down();
  await page.mouse.move(box.x + 60, box.y + 60, { steps: 4 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByLabel("Nom du motif").fill(name);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
}

/**
 * Waits for the server's patterns: until the library has loaded, the built-in
 * demo patterns may briefly be listed instead (issue #48).
 */
async function waitForLibrary(page: Page, patterns: PatternSummary[]): Promise<void> {
  await expect(page.locator(".card-title")).toHaveCount(patterns.length);
  for (const pattern of patterns) {
    await expect(page.locator(".card-title", { hasText: pattern.name }).first()).toBeVisible();
  }
}

async function cardTitles(page: Page): Promise<string[]> {
  return page.locator(".card-title").allTextContents();
}

async function cardPercents(page: Page): Promise<number[]> {
  const texts = await page.locator(".card-title + *").allTextContents();
  return texts.map((text) => Number(text.replace("%", "")));
}

async function chooseSort(page: Page, label: string): Promise<void> {
  await page.getByRole("button", { name: "Trier" }).click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await menu.getByRole("menuitemradio", { name: label }).click();
  await expect(menu).toBeHidden();
}

test.use({ viewport: { width: 375, height: 812 } });

test("the Sort menu reorders the library and remembers the choice", async ({ page, request }) => {
  // At least two patterns. The imported one is the most recent, but its name
  // sorts last: the "name" and "recent" orders then really differ.
  if ((await fetchPatterns(request)).length < 2) {
    await importPattern(page, "Zzz issue 56");
  }
  const patterns = await fetchPatterns(request);
  expect(patterns.length).toBeGreaterThanOrEqual(2);

  await page.goto("/");
  await waitForLibrary(page, patterns);

  // Escape closes the menu without changing anything.
  await page.getByRole("button", { name: "Trier" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();

  // Name: alphabetical, in the interface language's collation.
  await chooseSort(page, "Nom (A → Z)");
  const collator = new Intl.Collator("fr-FR", { sensitivity: "base", numeric: true });
  const byName = patterns.map((pattern) => pattern.name).sort((a, b) => collator.compare(a, b));
  expect(await cardTitles(page)).toEqual(byName);

  // The choice survives a reload, and is shown as the checked option.
  await page.reload();
  await waitForLibrary(page, patterns);
  expect(await cardTitles(page)).toEqual(byName);
  await page.getByRole("button", { name: "Trier" }).click();
  await expect(page.getByRole("menuitemradio", { name: "Nom (A → Z)" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.keyboard.press("Escape");

  // Progress: most advanced first.
  await chooseSort(page, "Avancement");
  const percents = await cardPercents(page);
  expect(percents).toEqual([...percents].sort((a, b) => b - a));

  // Recent activity: most recently updated first.
  await chooseSort(page, "Activité récente");
  const byRecent = [...patterns]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .map((pattern) => pattern.name);
  expect(await cardTitles(page)).toEqual(byRecent);
});
