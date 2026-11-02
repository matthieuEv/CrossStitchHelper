import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Issue #90: the Library's "Sort" menu can order the patterns by label —
 * patterns sharing a label side by side, in alphabetical order of their first
 * label, the ones without any label last.
 */

interface PatternSummary {
  id: string;
  name: string;
}

/** A copy of an existing pattern, under `name`, carrying `labels`. */
async function labelledCopy(
  request: APIRequestContext,
  sourceId: string,
  name: string,
  labels: string[],
): Promise<void> {
  const copy = (await (
    await request.post(`/api/patterns/${sourceId}/duplicate`, { data: { name } })
  ).json()) as { id: string };
  const updated = await request.patch(`/api/patterns/${copy.id}`, { data: { labels } });
  expect(updated.ok()).toBe(true);
}

async function chooseSort(page: Page, label: string): Promise<void> {
  await page.getByRole("button", { name: "Trier" }).click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await menu.getByRole("menuitemradio", { name: label }).click();
  await expect(menu).toBeHidden();
}

test.use({ viewport: { width: 375, height: 812 } });

test("sorting by label groups patterns by their first label, unlabelled ones last", async ({
  page,
  request,
}) => {
  const [source] = (await (await request.get("/api/patterns")).json()) as PatternSummary[];
  if (source === undefined) throw new Error("The instance needs at least one pattern");
  // Names in the opposite order of their labels: the label must win.
  const run = Date.now();
  const unlabelled = `A sans étiquette ${run}`;
  const christmas = `B Noël ${run}`;
  const animals = `C Animaux ${run}`;
  await labelledCopy(request, source.id, unlabelled, []);
  await labelledCopy(request, source.id, christmas, ["Noël"]);
  // Its first label in alphabetical order is "Animaux", not "Zoo".
  await labelledCopy(request, source.id, animals, ["Zoo", "Animaux"]);

  await page.goto("/");
  await expect(page.locator(".card-title", { hasText: animals })).toBeVisible();
  await chooseSort(page, "Étiquette (A → Z)");

  const titles = await page.locator(".card-title").allTextContents();
  const position = (name: string): number => titles.indexOf(name);
  expect(position(animals)).toBeGreaterThanOrEqual(0);
  expect(position(animals)).toBeLessThan(position(christmas));
  expect(position(christmas)).toBeLessThan(position(unlabelled));

  // The choice is remembered on this device, like the other sorts.
  await page.reload();
  await expect(page.locator(".card-title", { hasText: animals })).toBeVisible();
  const reloaded = await page.locator(".card-title").allTextContents();
  expect(reloaded).toEqual(titles);
});
