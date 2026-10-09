import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Checks Lot 3's "done when" criteria (docs/roadmap.md) still to be covered
 * after Lot 1 (colour filtering and row/column highlighting were already real
 * there): a statistics history derived from real progress data, hiding
 * already stitched cells, and an undo that goes back over several gestures in
 * a row — against a real backend, not mocks.
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

/**
 * Same lookup as lot1-persistence.spec.ts, but by id rather than by size:
 * Lot 4 imports a real pattern of the same dimensions (255×180) into the same
 * database, so `cell_count` alone no longer tells the seeded pattern apart
 * from an imported one.
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
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`"Remaining" counter not found in: ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

async function fillZone(
  page: Page,
  canvas: ReturnType<Page["locator"]>,
  fromFraction: { x: number; y: number },
  toFraction: { x: number; y: number },
  action: "Cocher la zone" | "Décocher la zone",
): Promise<void> {
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const from = { x: box.x + box.width * fromFraction.x, y: box.y + box.height * fromFraction.y };
  const to = { x: box.x + box.width * toFraction.x, y: box.y + box.height * toFraction.y };

  await page.getByRole("button", { name: "Sélectionner une zone" }).click();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  await page.getByRole("button", { name: action, exact: true }).click();
}

test("checking cells shows up in the real statistics activity history", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);

  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Known baseline, like lot1-persistence.spec.ts: clear then fill, for a
  // guaranteed change whatever state a previous run left.
  await fillZone(page, canvas, { x: 0.3, y: 0.3 }, { x: 0.7, y: 0.7 }, "Décocher la zone");
  await fillZone(page, canvas, { x: 0.3, y: 0.3 }, { x: 0.7, y: 0.7 }, "Cocher la zone");

  // Synchronisation is asynchronous (see lot1-persistence.spec.ts): give the
  // server time to write the `progress_events` before querying it.
  await page.waitForTimeout(1500);

  const activity = await request
    .get(`/api/patterns/${pattern.id}/activity`)
    .then((response) => response.json());
  expect(activity.sessions.length).toBeGreaterThan(0);
  expect(activity.sessions[0].stitches).toBeGreaterThan(0);
  expect(activity.sessions[0].hours_ago).toBeLessThan(0.1);

  await page.getByRole("button", { name: "Statistiques" }).click();
  await expect(page.getByRole("heading", { name: "Statistiques" })).toBeVisible();
  // A real recent session, never frozen text from the fake data set (see
  // usePatternActivity.ts: this pattern is not a demo pattern).
  await expect(page.getByText(/il y a (\d+ )?(minute|seconde)/)).toBeVisible();
});

test("hiding already stitched cells visually empties them", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Zoom out to the bound (MIN_CELL) then pan the view to its opposite bound
  // (-panMargin(255) cells, see pattern/render.ts `panMargin` and its use in
  // useTracker.ts `setOffset`): whatever the exact number of clicks/drag
  // distance, we always land at the same place — the pattern's corner, whose
  // border (310 cells, black) is fully stitched from the seed onwards (see
  // `backend/app/seed.py`).
  const zoomOut = page.getByRole("button", { name: "Dézoomer" });
  for (let i = 0; i < 10; i++) await zoomOut.click();

  await page.getByRole("button", { name: "Déplacer" }).click();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  await page.mouse.move(center.x + 3000, center.y + 3000, { steps: 8 });
  await page.mouse.up();

  // Pattern cell (0,0): black border, 100% stitched since the seed. With
  // MIN_CELL = 4px and panMargin(255) = max(6, 255*0.1) = 25.5 cells of
  // overscroll, its top-left corner sits at canvas pixel (25.5*4 = 102, 102)
  // — with no grid lines or symbol at that size (below
  // GRIDLINE_MIN_CELL/SYMBOL_MIN_CELL), a pure flat colour.
  const sample = (): Promise<[number, number, number]> =>
    canvas.evaluate((element) => {
      const ctx = (element as HTMLCanvasElement).getContext("2d");
      if (ctx === null) throw new Error("no 2d context");
      const data = ctx.getImageData(104, 104, 1, 1).data;
      return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0];
    });

  const stitchedColor = await sample();
  // Stitched cell: washed out (black/background mix), hence light — never pure black.
  expect(stitchedColor[0]).toBeGreaterThan(80);

  const hideButton = page.getByRole("button", { name: "Masquer les cases faites" });
  await hideButton.click();
  const hiddenColor = await sample();
  // Hidden: bare fabric colour, noticeably different from the washed-out one.
  expect(Math.abs(hiddenColor[0] - stitchedColor[0])).toBeGreaterThan(20);

  await page.getByRole("button", { name: "Réafficher les cases faites" }).click();
  const shownAgainColor = await sample();
  expect(shownAgainColor).toEqual(stitchedColor);
});

test("undo goes back over several areas checked in a row", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // Two adjacent, disjoint areas, both cleared first for a known baseline
  // (same pattern as the other specs).
  await fillZone(page, canvas, { x: 0.25, y: 0.3 }, { x: 0.45, y: 0.7 }, "Décocher la zone");
  await fillZone(page, canvas, { x: 0.5, y: 0.3 }, { x: 0.7, y: 0.7 }, "Décocher la zone");
  const baseline = await remainingCount(page);

  await fillZone(page, canvas, { x: 0.25, y: 0.3 }, { x: 0.45, y: 0.7 }, "Cocher la zone");
  const afterFirstFill = await remainingCount(page);
  expect(afterFirstFill).toBeLessThan(baseline);

  await fillZone(page, canvas, { x: 0.5, y: 0.3 }, { x: 0.7, y: 0.7 }, "Cocher la zone");
  const afterSecondFill = await remainingCount(page);
  expect(afterSecondFill).toBeLessThan(afterFirstFill);

  const undo = page.getByRole("button", { name: "Annuler" });
  await undo.click();
  await expect.poll(() => remainingCount(page)).toBe(afterFirstFill);

  await undo.click();
  await expect.poll(() => remainingCount(page)).toBe(baseline);
});
