import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Issue #83: 1/4 and 3/4 stitches have a corner, and one cell may hold
 * several — the usual split cell is a 3/4 stitch plus a 1/4 stitch of
 * another colour in the opposite corner. The demo pattern (`app/seed.py`)
 * has four such cells; cell (124, 68) holds a 3/4 stitch in its top-left
 * corner and a 1/4 stitch in its bottom-right one.
 */

const CELL = { x: 124, y: 68 };

interface PartialStitch {
  x: number;
  y: number;
  corner: "tl" | "tr" | "bl" | "br";
  palette_index: number;
}

async function demoPattern(request: APIRequestContext) {
  const patterns = (await (await request.get("/api/patterns")).json()) as Array<{
    id: string;
    name: string;
    width: number;
  }>;
  const demo = patterns.find((pattern) => pattern.width === 255);
  if (demo === undefined) throw new Error("The 255×180 demo pattern is not seeded");
  return demo;
}

function bitSet(base64: string | null, index: number): boolean {
  if (base64 === null) return false;
  const bytes = Buffer.from(base64, "base64");
  return ((bytes[index >> 3] ?? 0) & (1 << (index & 7))) !== 0;
}

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });

test("a split cell shows both partial stitches, each checked on its own", async ({
  page,
  request,
}) => {
  const demo = await demoPattern(request);
  const grid = (await (await request.get(`/api/patterns/${demo.id}/grid`)).json()) as {
    quarter_stitches: PartialStitch[];
    three_quarter_stitches: PartialStitch[];
  };
  const inCell = (item: PartialStitch): boolean => item.x === CELL.x && item.y === CELL.y;
  const quarterIndex = grid.quarter_stitches.findIndex(inCell);
  const threeQuarterIndex = grid.three_quarter_stitches.findIndex(inCell);
  expect(grid.quarter_stitches[quarterIndex]?.corner).toBe("br");
  expect(grid.three_quarter_stitches[threeQuarterIndex]?.corner).toBe("tl");

  // Known baseline: the cell's 1/4 stitch unchecked (an absolute state,
  // idempotent — see `lot8-special-stitches.spec.ts::setStitched`).
  const reset = await request.post(`/api/patterns/${demo.id}/progress`, {
    data: { base_version: 0, ops: [{ layer: "quarter", index: quarterIndex, stitched: false }] },
  });
  expect(reset.ok()).toBe(true);

  await page.goto("/");
  await page.getByText(demo.name).tap();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  // Zoom in so the cell's two corners are tens of pixels apart.
  const zoomIn = page.getByRole("button", { name: "Zoomer", exact: true });
  for (let i = 0; i < 3; i++) await zoomIn.tap();

  // Bring the cell to the canvas centre from the known view (see
  // `lot8-special-stitches.spec.ts::centerOn`): x0=30, y0=24, 34 px cells.
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  await page.getByRole("button", { name: "Déplacer", exact: true }).tap();
  const cell = 34;
  const dx = (30 + box.width / 2 / cell - (CELL.x + 0.5)) * cell;
  const dy = (24 + box.height / 2 / cell - (CELL.y + 0.5)) * cell;
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + dx, startY + dy, { steps: 10 });
  await page.mouse.up();

  // Two different colours in the two opposite corners of the same cell.
  const sample = (fx: number, fy: number) =>
    canvas.evaluate(
      (element, [x, y]) => {
        const el = element as HTMLCanvasElement;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const data = el
          .getContext("2d")!
          .getImageData(Math.round(x * ratio), Math.round(y * ratio), 1, 1).data;
        return [data[0], data[1], data[2]].join(",");
      },
      [box.width / 2 + (fx - 0.5) * cell, box.height / 2 + (fy - 0.5) * cell] as [number, number],
    );
  const nearTopLeft = await sample(0.2, 0.2);
  const nearBottomRight = await sample(0.9, 0.9);
  expect(nearTopLeft).not.toBe(nearBottomRight);

  // The 1/4 layer, a tap in the bottom-right corner: that stitch is checked.
  await page.getByRole("button", { name: "Cocher", exact: true }).tap();
  await page.getByRole("button", { name: "Point 1/4" }).tap();
  await page.touchscreen.tap(
    box.x + box.width / 2 + 0.35 * cell,
    box.y + box.height / 2 + 0.35 * cell,
  );
  await expect
    .poll(
      async () => {
        const progress = (await (
          await request.get(`/api/patterns/${demo.id}/progress`)
        ).json()) as {
          bitmap_quarter: string | null;
        };
        return bitSet(progress.bitmap_quarter, quarterIndex);
      },
      { timeout: 10_000 },
    )
    .toBe(true);
});
