import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Direct user feedback after real use: on a real paper diagram, backstitch
 * strokes stay visible even on an overview of the grid — the application
 * hid them entirely below the same zoom threshold as symbols
 * (`SYMBOL_MIN_CELL`, `pattern/render.ts`), which matches no paper reference.
 * Fixed by decoupling backstitch/knot rendering from that threshold — the
 * interaction (checking) remains reserved for close zoom
 * (`state/useTracker.ts`), not covered here.
 *
 * Geometry and sampling point taken as is from lot8-special-stitches.spec.ts
 * (derived from `backend/app/seed.py::_build_special_stitches`) — the
 * midpoint of the backstitch diamond's bottom→left segment, already verified
 * empirically by that test as falling on an empty full-stitch cell
 * (otherwise comparing with the fabric colour would make no sense).
 */

const DEMO_PATTERN_ID = "demo-perf-255x180";
// Below `SYMBOL_MIN_CELL` (15, `pattern/render.ts`): exactly the zoom level
// where the bug showed up.
const BELOW_SYMBOL_THRESHOLD = 15;

interface PatternSummary {
  id: string;
  name: string;
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

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

/** Taken from lot8-special-stitches.spec.ts — see that file for the
 * reasoning (the drag applies `dx = pixels / cell` per event). */
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

async function centerOn(page: Page, box: Box, view: View, gx: number, gy: number): Promise<View> {
  await page.getByRole("button", { name: "Déplacer" }).click();
  const desiredX0 = gx - box.width / 2 / view.cell;
  const desiredY0 = gy - box.height / 2 / view.cell;
  const movedX = (view.x0 - desiredX0) * view.cell;
  const movedY = (view.y0 - desiredY0) * view.cell;
  await panByPixels(page, box, movedX, movedY);
  return { x0: desiredX0, y0: desiredY0, cell: view.cell };
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\/case/);
  if (match?.[1] === undefined) throw new Error(`Zoom badge not found in: ${text}`);
  return Number(match[1]);
}

test("backstitch stays visible well below the symbol appearance threshold", async ({
  page,
  request,
}) => {
  const pattern = await fetchDemoPattern(request);
  await page.goto("/");
  await page.getByText(pattern.name).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");

  // Known initial view (`useTracker.ts`, 255×180 pattern) — same value as in
  // lot8-special-stitches.spec.ts. Centre on the backstitch diamond (`_CX,
  // _CY` in `seed.py`) while still above the threshold, the re-centring drag
  // being easier to reason about at this zoom already verified by the other
  // test.
  const initialView: View = { x0: 30, y0: 24, cell: 16 };
  await centerOn(page, box, initialView, 127, 90);

  // The cursor is now exactly at the centre of the canvas, and that screen
  // point matches exactly the pattern's cell (127, 90). A wheel zoom-out
  // centred on the cursor (see wheel-zoom.spec.ts) keeps this same grid point
  // at the centre of the screen whatever the number of notches, which avoids
  // recomputing x0/y0 afterwards — only `cell` changes.
  const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(center.x, center.y);

  let cell = await zoomBadgeSize(page);
  let guard = 0;
  while (cell >= BELOW_SYMBOL_THRESHOLD && guard < 30) {
    await page.mouse.wheel(0, 200);
    cell = await zoomBadgeSize(page);
    guard += 1;
  }
  expect(cell).toBeLessThan(BELOW_SYMBOL_THRESHOLD);

  // Midpoint of the diamond's bottom→left segment: (127,105)→(112,90),
  // already verified by lot8-special-stitches.spec.ts as falling on an empty
  // full-stitch cell at that zoom — so, without the fix, this pixel would
  // have stayed exactly the fabric colour (`--canvas-fabric`).
  const targetGrid = { x: (127 + 112) / 2, y: (105 + 90) / 2 };
  const px = box.width / 2 + (targetGrid.x - 127) * cell;
  const py = box.height / 2 + (targetGrid.y - 90) * cell;

  const rgb = await canvas.evaluate(
    (element, [x, y]) => {
      const el = element as HTMLCanvasElement;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const ctx = el.getContext("2d");
      if (ctx === null) throw new Error("no 2d context");
      const data = ctx.getImageData(Math.round(x * ratio), Math.round(y * ratio), 1, 1).data;
      return [data[0] ?? 0, data[1] ?? 0, data[2] ?? 0] as [number, number, number];
    },
    [px, py] as [number, number],
  );

  const fabric = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--canvas-fabric").trim(),
  );
  const fabricRgb = await page.evaluate((hex) => {
    const clean = hex.replace("#", "");
    return [0, 2, 4].map((i) => Number.parseInt(clean.slice(i, i + 2), 16));
  }, fabric);

  const distance = Math.hypot(
    rgb[0] - (fabricRgb[0] ?? 0),
    rgb[1] - (fabricRgb[1] ?? 0),
    rgb[2] - (fabricRgb[2] ?? 0),
  );
  expect(distance).toBeGreaterThan(30);
});
