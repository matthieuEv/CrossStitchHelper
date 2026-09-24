import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Zooming in/out with the wheel or trackpad (vertical scroll, deltaY), and
 * panning horizontally with a trackpad swipe (horizontal scroll, deltaX) —
 * rather than only via the +/- buttons, two-finger pinch or mouse drag —
 * explicit user requests, not a roadmap criterion. Verified on both canvases
 * concerned: Tracking (`TrackScreen`) and the import wizard's brush
 * (`ImportGridPainter`), which share the same gesture (`state/useTracker.ts`
 * and `state/useImportPainter.ts`, both via `zoomTo`/`setOffset`).
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\/case/);
  if (match?.[1] === undefined) throw new Error(`Zoom badge not found in: ${text}`);
  return Number(match[1]);
}

async function column(page: Page): Promise<number> {
  const text = await page.getByText(/Colonne \d+/).textContent();
  const match = text?.match(/Colonne (\d+)/);
  if (match?.[1] === undefined) throw new Error(`Position not found in: ${text}`);
  return Number(match[1]);
}

test("the wheel/trackpad zooms Tracking under the cursor", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const initial = await zoomBadgeSize(page);

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, -600); // scroll up: zoom in
  await expect.poll(() => zoomBadgeSize(page)).toBeGreaterThan(initial);
  const zoomedIn = await zoomBadgeSize(page);

  await page.mouse.wheel(0, 600); // scroll down: zoom out
  await expect.poll(() => zoomBadgeSize(page)).toBeLessThan(zoomedIn);

  // The page itself must never scroll behind the canvas — without
  // `preventDefault()` on the native listener, it would.
  const scrollY = await page.evaluate(() => window.scrollY);
  expect(scrollY).toBe(0);
});

test("a horizontal trackpad swipe pans the view without zooming", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const initialZoom = await zoomBadgeSize(page);
  const initialColumn = await column(page);

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(600, 0); // horizontal swipe, not vertical
  await expect.poll(() => column(page)).toBeGreaterThan(initialColumn);

  // Zoom must not have changed — only deltaY zooms.
  expect(await zoomBadgeSize(page)).toBe(initialZoom);
});

test("a diagonal trackpad swipe zooms and pans the view at the same time", async ({
  page,
  request,
}) => {
  // Real bug found in manual testing: on a real trackpad, a swipe is almost
  // never perfectly horizontal or vertical — deltaX and deltaY arrive
  // together in the same event. The pan was silently overwritten by the zoom
  // recomputation of the same event (see `useTracker.ts::zoomTo`: the
  // separate `setOffset` call for the pan started from a position already
  // stale by the time the zoom recomputation ran), which made the app seem to
  // "lock up" as soon as you tried to zoom and pan at the same time.
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  const initialZoom = await zoomBadgeSize(page);
  const initialColumn = await column(page);

  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(300, -400); // diagonal: pan right + zoom in

  await expect.poll(() => zoomBadgeSize(page)).toBeGreaterThan(initialZoom);
  await expect.poll(() => column(page)).toBeGreaterThan(initialColumn);
});

test("the wheel/trackpad also zooms the import wizard's brush", async ({ page }) => {
  // PDF vs photo does not matter here: only the zoom gesture on the painting
  // canvas is at stake, not the content — a minimal image is enough, like
  // lot2-manual-import.spec.ts.
  const TINY_PNG_BASE64 =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles({
      name: "grille-test.png",
      mimeType: "image/png",
      buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
    });

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("10");
  await rowsInput!.fill("8");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

  // No visible zoom indicator here (unlike Tracking's badge): a larger/smaller
  // cell necessarily changes the rendered grid, so a simple canvas capture is
  // enough to prove the gesture has an effect, without having to interpret the
  // pixel content.
  const snapshot = (): Promise<string> => canvas.evaluate((element) => (element as HTMLCanvasElement).toDataURL());

  const before = await snapshot();
  await page.mouse.move(center.x, center.y);
  await page.mouse.wheel(0, -600);
  await expect.poll(snapshot).not.toBe(before);
});
