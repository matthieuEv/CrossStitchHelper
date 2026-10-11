import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Issue #52: from the Library, a pattern can be duplicated (same chart, empty
 * progress) or deleted — from a "⋯" button on its card or by a long-press on
 * it — deletion asking for confirmation first.
 */

interface PatternSummary {
  id: string;
  name: string;
  stitched_count: number;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchPatterns(request: APIRequestContext): Promise<PatternSummary[]> {
  return (await (await request.get("/api/patterns")).json()) as PatternSummary[];
}

test.use({ viewport: { width: 375, height: 812 } });

test("a pattern can be duplicated, then the copy deleted by a long-press", async ({
  page,
  request,
}) => {
  const demo = (await fetchPatterns(request)).find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  const copyName = `${demo.name} (copie)`;

  // Leftovers of a previous run would make the copy's card ambiguous.
  for (const pattern of await fetchPatterns(request)) {
    if (pattern.name === copyName) await request.delete(`/api/patterns/${pattern.id}`);
  }

  await page.goto("/");
  await expect(page.locator(".card-title", { hasText: demo.name }).first()).toBeVisible();

  // Escape closes the actions without doing anything.
  const more = page.getByRole("button", { name: `Actions pour « ${demo.name} »` });
  const sheet = page.getByRole("dialog", { name: `Actions pour « ${demo.name} »` });
  await more.click();
  await expect(sheet).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();

  // Duplicate from the "⋯" button.
  await more.click();
  await sheet.getByRole("button", { name: "Dupliquer" }).click();
  await expect(sheet).toBeHidden();
  const copyCard = page.locator(".card-title", { hasText: copyName });
  await expect(copyCard).toBeVisible();

  const copy = (await fetchPatterns(request)).find((pattern) => pattern.name === copyName);
  expect(copy).toBeDefined();
  expect(copy!.stitched_count).toBe(0);
  expect(copy!.id).not.toBe(DEMO_PATTERN_ID);

  // Delete the copy by a long-press on its card — and confirm.
  await copyCard.scrollIntoViewIfNeeded();
  const box = await copyCard.boundingBox();
  if (box === null) throw new Error("The copy's card has no bounding box");
  await page.mouse.move(box.x + 10, box.y + 5);
  await page.mouse.down();
  await page.waitForTimeout(800);
  await page.mouse.up();
  const copySheet = page.getByRole("dialog", { name: `Actions pour « ${copyName} »` });
  await expect(copySheet).toBeVisible();
  // The long-press must not also have opened the pattern.
  await expect(page).toHaveURL(/\/$/);

  await copySheet.getByRole("button", { name: "Supprimer", exact: true }).click();
  await expect(copySheet.getByText(/Cette action est définitive/)).toBeVisible();
  await copySheet.getByRole("button", { name: "Supprimer définitivement" }).click();
  await expect(copySheet).toBeHidden();
  await expect(copyCard).toHaveCount(0);
  await expect(page.locator(".card-title", { hasText: demo.name }).first()).toBeVisible();

  expect(await request.get(`/api/patterns/${copy!.id}`).then((response) => response.status())).toBe(404);
  // The source is untouched.
  const source = (await fetchPatterns(request)).find((pattern) => pattern.id === DEMO_PATTERN_ID);
  expect(source?.stitched_count).toBe(demo.stitched_count);
});
