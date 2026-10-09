import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

/**
 * Checks Lot 8's "done when" criterion (docs/roadmap.md): rendering shows the
 * four special stitch categories (1/2, 1/4, backstitch, knot) of the demo
 * pattern, and checking one stitch of each category persists after a reload
 * — against a real backend, not mocks.
 *
 * Geometry of the small decorative motif from `backend/app/seed.py`
 * (`_build_special_stitches`), centred on cell (127, 90) — coordinates taken
 * as is rather than guessed, so as not to depend on an on-screen detection
 * heuristic:
 * - backstitch: four segments in a diamond, corners (127,75) (142,90)
 *   (127,105) (112,90); segments 0 and 1 are already checked by the seed,
 *   segment 2 (bottom→left) is not.
 * - knots: centres (127.5,70.5) (121.5,87.5) (132.5,88.5) (123.5,96.5)
 *   (133.5,97.5) (127.5,110.5); indices 0, 2, 4 are already checked, index 1
 *   is not.
 * - 1/2 stitch (colour 798) and 1/4 stitch (colour 816): cells scattered
 *   around the centre — cell (117,104) carries an unchecked 1/2 stitch, cell
 *   (109,95) an unchecked 1/4 stitch (those closest to the centre are
 *   checked by the seed, see the `_build_special_stitches` comment).
 */

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

/** Centre of the small decorative motif (`backend/app/seed.py::_CX, _CY`). */
const CENTER = { x: 127, y: 90 };

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

type StitchLayer = "full" | "half" | "quarter" | "backstitch" | "knot";

/** Forces an absolute state for an element of a given category — idempotent
 * on the server (§9), hence a reliable known baseline whatever state a
 * previous run of the test left (same principle as lot1-persistence.spec.ts:
 * "clear before filling"). `base_version` does not need to be exact:
 * operations apply unconditionally (see
 * `backend/app/api/patterns.py::sync_progress`), only `missing_ops` (ignored
 * here) depends on it. */
async function setStitched(
  request: APIRequestContext,
  patternId: string,
  layer: StitchLayer,
  index: number,
  stitched: boolean,
): Promise<void> {
  const response = await request.post(`/api/patterns/${patternId}/progress`, {
    data: { base_version: 0, ops: [{ layer, index, stitched }] },
  });
  if (!response.ok()) {
    throw new Error(`Progress update failed (${layer}#${index}): ${response.status()}`);
  }
}

function bitSet(base64: string | null, index: number): boolean {
  if (base64 === null) return false;
  const byte = Buffer.from(base64, "base64")[index >> 3] ?? 0;
  return ((byte >> (index & 7)) & 1) === 1;
}

interface ProgressResponse {
  bitmap_half: string | null;
  bitmap_quarter: string | null;
  bitmap_backstitch: string | null;
  bitmap_knots: string | null;
}

async function fetchProgress(request: APIRequestContext, patternId: string): Promise<ProgressResponse> {
  const response = await request.get(`/api/patterns/${patternId}/progress`);
  return (await response.json()) as ProgressResponse;
}

interface View {
  x0: number;
  y0: number;
  cell: number;
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Pans the view ("Move" tool) by an exact pixel delta — the drag gesture
 * applies `dx = (pixel movement) / cell` on each `pointermove` event (see
 * `TrackScreen.tsx::onPointerMove`), so the sum telescopes exactly to the net
 * movement whatever the number of intermediate steps. Split into several
 * short gestures so the mouse never leaves the test window.
 */
async function panByPixels(page: Page, box: Box, totalDx: number, totalDy: number): Promise<void> {
  const maxStep = 250;
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  let remainingX = totalDx;
  let remainingY = totalDy;
  while (Math.abs(remainingX) > 0.5 || Math.abs(remainingY) > 0.5) {
    const stepX = Math.max(-maxStep, Math.min(maxStep, remainingX));
    const stepY = Math.max(-maxStep, Math.min(maxStep, remainingY));
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX + stepX, startY + stepY, { steps: 6 });
    await page.mouse.up();
    remainingX -= stepX;
    remainingY -= stepY;
  }
}

/**
 * Exact pan to bring grid point `(gx, gy)` to the centre of the canvas,
 * starting from a known view (`view`) — see the `panByPixels` comment.
 * Returns the new view, to reuse for the next call.
 */
async function centerOn(page: Page, box: Box, view: View, gx: number, gy: number): Promise<View> {
  await page.getByRole("button", { name: "Déplacer" }).click();
  const desiredX0 = gx - box.width / 2 / view.cell;
  const desiredY0 = gy - box.height / 2 / view.cell;
  const movedX = (view.x0 - desiredX0) * view.cell;
  const movedY = (view.y0 - desiredY0) * view.cell;
  await panByPixels(page, box, movedX, movedY);
  return { x0: desiredX0, y0: desiredY0, cell: view.cell };
}

/** Tap at the centre of the canvas — a single press, with no movement, to
 * stay under `DRAG_THRESHOLD` and be treated as a check, not a drag (see
 * `TrackScreen.tsx`). */
async function tapCenter(page: Page, box: Box): Promise<void> {
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.up();
}

async function openTrackScreen(page: Page, patternName: string): Promise<Locator> {
  await page.goto("/");
  await page.getByText(patternName).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  return canvas;
}

test("rendering shows the demo pattern's special stitches", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  const canvas = await openTrackScreen(page, pattern.name);

  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");

  // Known initial view (`useTracker.ts`, 255×180 pattern): x0=30, y0=24,
  // cell=16 — without touching zoom or pan. Cell=16 is already above
  // `SYMBOL_MIN_CELL` (15): backstitch and knots are therefore rendered (see
  // `pattern/render.ts`).
  const initialView: View = { x0: 30, y0: 24, cell: 16 };
  const view = await centerOn(page, box, initialView, CENTER.x, CENTER.y);

  const fabric = await page.evaluate(() =>
    getComputedStyle(document.querySelector("canvas.track-canvas")!)
      .getPropertyValue("--canvas-fabric")
      .trim(),
  );
  const fabricRgb = await page.evaluate((hex) => {
    const clean = hex.replace("#", "");
    return [0, 2, 4].map((i) => Number.parseInt(clean.slice(i, i + 2), 16));
  }, fabric);

  const sample = (gx: number, gy: number): Promise<[number, number, number]> =>
    canvas.evaluate(
      (element, [x, y]) => {
        const el = element as HTMLCanvasElement;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const ctx = el.getContext("2d");
        if (ctx === null) throw new Error("no 2d context");
        const data = ctx.getImageData(Math.round(x * ratio), Math.round(y * ratio), 1, 1).data;
        return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0] as [number, number, number];
      },
      [gx, gy] as [number, number],
    );

  // Coordinates **relative to the canvas** (never the page): `getImageData`
  // always addresses the canvas's own pixel buffer, not the window — unlike
  // the mouse coordinates used elsewhere in this file
  // (`panByPixels`/`tapCenter`), which must include `box.x`/`box.y`.
  const toLocalPixel = (gx: number, gy: number): [number, number] => [
    (gx - view.x0) * view.cell,
    (gy - view.y0) * view.cell,
  ];

  const distance = (rgb: [number, number, number]): number =>
    Math.hypot(rgb[0] - (fabricRgb[0] ?? 0), rgb[1] - (fabricRgb[1] ?? 0), rgb[2] - (fabricRgb[2] ?? 0));

  // 1/4 stitch (cell (109,95), top-left corner of the triangle — see
  // `fillQuarterTriangle`).
  {
    const [px, py] = toLocalPixel(109 + 0.15, 95 + 0.15);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // 1/2 stitch (cell (117,104), top-left diagonal triangle).
  {
    const [px, py] = toLocalPixel(117 + 0.25, 104 + 0.25);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // Backstitch (bottom→left segment, its midpoint).
  {
    const [px, py] = toLocalPixel((127 + 112) / 2, (105 + 90) / 2);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }

  // Knot (centre of the index 1 knot, unchecked).
  {
    const [px, py] = toLocalPixel(121.5, 87.5);
    const rgb = await sample(px, py);
    expect(distance(rgb)).toBeGreaterThan(30);
  }
});

test("checking a 1/2, 1/4, backstitch and knot stitch persists after a reload", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);

  // Known baseline, whatever the previous run: the four targeted elements
  // start unchecked.
  const QUARTER_INDEX = 95 * 255 + 109; // cell (109, 95)
  const HALF_INDEX = 104 * 255 + 117; // cell (117, 104)
  const BACKSTITCH_INDEX = 2; // segment bas→gauche
  const KNOT_INDEX = 1; // knot (121.5, 87.5)

  await setStitched(request, pattern.id, "quarter", QUARTER_INDEX, false);
  await setStitched(request, pattern.id, "half", HALF_INDEX, false);
  await setStitched(request, pattern.id, "backstitch", BACKSTITCH_INDEX, false);
  await setStitched(request, pattern.id, "knot", KNOT_INDEX, false);

  const before = await fetchProgress(request, pattern.id);
  expect(bitSet(before.bitmap_quarter, QUARTER_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_half, HALF_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_backstitch, BACKSTITCH_INDEX)).toBe(false);
  expect(bitSet(before.bitmap_knots, KNOT_INDEX)).toBe(false);

  const canvas = await openTrackScreen(page, pattern.name);
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");

  // Zoom to the maximum (buttons, not the wheel: `zoomIn` rounds to an exact
  // integer, unlike pinch/trackpad — needed so the centring computation below
  // stays exact). Three clicks are enough to reach MAX_CELL (16 → 23 → 33 →
  // 34); zooming never changes `x0`/`y0` (see `useTracker.ts::zoomIn`).
  const zoomInButton = page.getByRole("button", { name: "Zoomer", exact: true });
  for (let i = 0; i < 3; i++) await zoomInButton.click();
  let view: View = { x0: 30, y0: 24, cell: 34 };

  // Point 1/4.
  view = await centerOn(page, box, view, 109.5, 95.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  await page.getByRole("button", { name: "Point 1/4" }).click();
  await tapCenter(page, box);

  // Point 1/2.
  view = await centerOn(page, box, view, 117.5, 104.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  await page.getByRole("button", { name: "Point 1/2" }).click();
  await tapCenter(page, box);

  // Backstitch (midpoint of the bottom→left segment: (127,105)-(112,90)).
  view = await centerOn(page, box, view, (127 + 112) / 2, (105 + 90) / 2);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  const backstitchButton = page.getByRole("button", { name: "Point arrière" });
  await expect(backstitchButton).toBeEnabled();
  await backstitchButton.click();
  await tapCenter(page, box);

  // Knot (centre (121.5, 87.5)).
  view = await centerOn(page, box, view, 121.5, 87.5);
  await page.getByRole("button", { name: "Cocher", exact: true }).click();
  const knotButton = page.getByRole("button", { name: "Nœud" });
  await expect(knotButton).toBeEnabled();
  await knotButton.click();
  await tapCenter(page, box);

  // Synchronisation is asynchronous (IndexedDB queue + debounced send, see
  // lot1-persistence.spec.ts): give `useSyncedTracker` time to confirm before
  // querying the server or reloading.
  await expect
    .poll(async () => {
      const progress = await fetchProgress(request, pattern.id);
      return [
        bitSet(progress.bitmap_quarter, QUARTER_INDEX),
        bitSet(progress.bitmap_half, HALF_INDEX),
        bitSet(progress.bitmap_backstitch, BACKSTITCH_INDEX),
        bitSet(progress.bitmap_knots, KNOT_INDEX),
      ];
    }, { timeout: 10_000 })
    .toEqual([true, true, true, true]);

  await page.reload();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  const after = await fetchProgress(request, pattern.id);
  expect(bitSet(after.bitmap_quarter, QUARTER_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_half, HALF_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_backstitch, BACKSTITCH_INDEX)).toBe(true);
  expect(bitSet(after.bitmap_knots, KNOT_INDEX)).toBe(true);
});
