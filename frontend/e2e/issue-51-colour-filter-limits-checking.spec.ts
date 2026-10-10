import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Issue #51: with a colour selected (filter), only cells of that colour can
 * be checked — a tap on a dimmed cell of another colour changes nothing,
 * exactly like "Check the area" already did under a filter.
 */

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

interface PatternDetail {
  id: string;
  name: string;
  width: number;
  palette: { index_in_grid: number; code: string }[];
}

interface GridResponse {
  width: number;
  height: number;
  layer_full: string;
}

async function fetchPattern(
  request: APIRequestContext,
): Promise<{ detail: PatternDetail; cells: Uint16Array; width: number; height: number }> {
  const detail = (await (await request.get(`/api/patterns/${DEMO_PATTERN_ID}`)).json()) as PatternDetail;
  const grid = (await (await request.get(`/api/patterns/${DEMO_PATTERN_ID}/grid`)).json()) as GridResponse;
  const bytes = Buffer.from(grid.layer_full, "base64");
  const cells = new Uint16Array(grid.width * grid.height);
  for (let i = 0; i < cells.length; i++) cells[i] = bytes.readUInt16LE(i * 2);
  return { detail, cells, width: grid.width, height: grid.height };
}

async function remainingCount(page: Page): Promise<number> {
  const text = await page.getByText(/restants$/).first().textContent();
  const match = text?.match(/([\d\s ]+)\s*restants/);
  if (match?.[1] === undefined) throw new Error(`"Remaining" counter not found in: ${text}`);
  return Number(match[1].replace(/[\s ]/g, ""));
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\//);
  if (match?.[1] === undefined) throw new Error(`Zoom badge not found in: ${text}`);
  return Number(match[1]);
}

/** View origin, read from the header before the pointer ever hovers the grid. */
async function viewOrigin(page: Page): Promise<{ x0: number; y0: number }> {
  const text = await page.getByText(/Ligne \d+ · Colonne \d+/).textContent();
  const match = text?.match(/Ligne (\d+) · Colonne (\d+)/);
  if (match?.[1] === undefined || match[2] === undefined) throw new Error(`Position not found in: ${text}`);
  return { x0: Number(match[2]) - 1, y0: Number(match[1]) - 1 };
}

test.use({ viewport: { width: 375, height: 812 } });

test("under a colour filter, only cells of that colour can be checked", async ({ page, request }) => {
  const { detail, cells, width, height } = await fetchPattern(request);

  await page.goto(`/track/${DEMO_PATTERN_ID}`);
  // The real pattern's title first: until the library has loaded, a demo
  // pattern may briefly be shown in its place (issue #47).
  await expect(page.getByText(detail.name)).toBeVisible();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  const cellSize = await zoomBadgeSize(page);
  const { x0, y0 } = await viewOrigin(page);

  const colourAt = (x: number, y: number): number =>
    x < 0 || y < 0 || x >= width || y >= height ? 0 : (cells[y * width + x] ?? 0);
  const screenPoint = (x: number, y: number): { x: number; y: number } => ({
    x: box.x + (x - x0 + 0.5) * cellSize,
    y: box.y + (y - y0 + 0.5) * cellSize,
  });

  // The cell at the centre of the canvas gives the filtered colour; a nearby
  // cell of another (non-empty) colour is the one that must stay untouched.
  const centre = {
    x: x0 + Math.floor(box.width / 2 / cellSize),
    y: y0 + Math.floor(box.height / 2 / cellSize),
  };
  const filtered = colourAt(centre.x, centre.y);
  expect(filtered).not.toBe(0);
  let other: { x: number; y: number } | null = null;
  for (let radius = 1; radius <= 6 && other === null; radius++) {
    for (let dy = -radius; dy <= radius && other === null; dy++) {
      for (let dx = -radius; dx <= radius && other === null; dx++) {
        const colour = colourAt(centre.x + dx, centre.y + dy);
        if (colour !== 0 && colour !== filtered) other = { x: centre.x + dx, y: centre.y + dy };
      }
    }
  }
  if (other === null) throw new Error("No cell of another colour near the centre of the canvas");

  const code = detail.palette.find((entry) => entry.index_in_grid === filtered)?.code;
  if (code === undefined) throw new Error(`Palette entry ${filtered} not found`);
  await page.getByRole("button", { name: "Couleurs" }).click();
  await page.getByRole("button", { name: new RegExp(`DMC ${code}\\b`) }).first().click();
  await page.getByRole("button", { name: "Fermer" }).click();
  await expect(page.getByText(`Filtre DMC ${code}`)).toBeVisible();

  // A tap on a dimmed cell of another colour changes nothing.
  const before = await remainingCount(page);
  const otherPoint = screenPoint(other.x, other.y);
  await page.mouse.click(otherPoint.x, otherPoint.y);
  await page.waitForTimeout(300);
  expect(await remainingCount(page)).toBe(before);

  // A tap on a cell of the filtered colour still toggles it — then a second
  // tap puts it back, so the test leaves the database as it found it.
  const centrePoint = screenPoint(centre.x, centre.y);
  await page.mouse.click(centrePoint.x, centrePoint.y);
  await expect.poll(() => remainingCount(page)).not.toBe(before);
  await page.mouse.click(centrePoint.x, centrePoint.y);
  await expect.poll(() => remainingCount(page)).toBe(before);
});
