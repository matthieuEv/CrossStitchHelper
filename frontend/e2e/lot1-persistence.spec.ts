import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Checks Lot 1's "done when" criterion (docs/roadmap.md): cells can be
 * checked and progress is found again after a reload — against a real
 * backend, not mocks. Assumes an already running instance with at least one
 * pattern in the database (see e2e/README.md for the local procedure, and
 * .github/workflows/ci.yml for the CI one).
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

/**
 * The seeded demo pattern, identified by its stable id
 * (`backend/app/seed.py::DEMO_PATTERN_ID`) rather than by its size: other
 * specs (Lot 2, Lot 4) create their own patterns in the same database,
 * potentially of the same dimensions (255×180, Lot 4's type A fixture lands
 * there too) — sorting by `cell_count` is no longer enough to remove the
 * ambiguity since that coincidence exists.
 */
async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

async function remainingCount(page: Page): Promise<number> {
  const text = await page.getByText(/restants$/).first().textContent();
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`"Remaining" counter not found in: ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

test("the library shows a pattern loaded from the server", async ({ page, request }) => {
  const response = await request.get("/api/patterns");
  expect(response.ok()).toBeTruthy();

  const demo = await fetchDemoPattern(request);
  await page.goto("/");
  await expect(page.getByText(demo.name)).toBeVisible();
});

test("checking an area of cells persists after a reload", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);

  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");

  // An area large enough to be sure to contain stitchable cells, in the
  // dense part of the demo pattern (centre of the canvas).
  const from = { x: box.x + box.width * 0.3, y: box.y + box.height * 0.3 };
  const to = { x: box.x + box.width * 0.7, y: box.y + box.height * 0.7 };

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();

  // Known baseline: clear the area first, so the next fill produces a
  // guaranteed change, whatever state a previous run of the test left.
  await page.getByRole("button", { name: "Décocher la zone", exact: true }).click();
  const emptied = await remainingCount(page);

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Cocher la zone", exact: true }).click();
  const filled = await remainingCount(page);

  expect(filled).toBeLessThan(emptied);

  // Synchronisation is asynchronous (IndexedDB queue + debounced send): give
  // `useSyncedTracker` time to confirm before reloading, otherwise the reload
  // could happen before the server write.
  await page.waitForTimeout(2000);

  await page.reload();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  await expect.poll(() => remainingCount(page)).toBe(filled);
});
