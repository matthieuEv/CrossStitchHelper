import { expect, test, type Page } from "@playwright/test";

/**
 * Issue #82: on the import wizard's Palette step, backstitches are drawn by
 * tapping one cell corner then another, knots are placed by tapping a cell,
 * the eraser removes either, undo follows the order things were done in
 * (painted areas included), and what was drawn reaches the created pattern.
 * Touch taps at phone size: the reporter stitches from a tablet.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

// The brush opens at 16 px per cell with two cells of margin
// (`useImportPainter`): a grid point (corner coordinates) in canvas pixels.
const point = (x: number, y: number): [number, number] => [32 + 16 * x, 32 + 16 * y];
// The centre of cell (x, y).
const cell = (x: number, y: number): [number, number] => point(x + 0.5, y + 0.5);

test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });

async function tap(page: Page, [x, y]: [number, number]): Promise<void> {
  const box = await page.locator("canvas.track-canvas").boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  await page.touchscreen.tap(box.x + x, box.y + y);
}

test("backstitches and knots drawn by hand reach the created pattern", async ({
  page,
  request,
}) => {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "contours.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("4");
  await page.getByRole("button", { name: "Continuer", exact: true }).tap();

  const addColour = page.getByRole("button", { name: /Ajouter une couleur/ });
  const backstitch = page.getByRole("button", { name: "Point arrière" });
  const knot = page.getByRole("button", { name: "Point de nœud" });
  const eraser = page.getByRole("button", { name: /Gomme/ });
  const undo = page.getByRole("button", { name: "Annuler la dernière modification" });
  const painted = page.getByText(/\d+ \/ 24 cases peintes/);

  // The whole toolbar fits the phone's width (16 px side gutter).
  const bar = await page.getByRole("group", { name: "Type de point" }).boundingBox();
  expect(bar!.x + bar!.width).toBeLessThanOrEqual(375 - 16);

  // Colour 1, backstitch: corner to corner, twice; tapping the start corner
  // again cancels a segment.
  await addColour.tap();
  await backstitch.tap();
  await expect(page.getByText(/Touchez un coin de case/)).toBeVisible();
  await tap(page, point(0, 0));
  await tap(page, point(3, 2));
  await tap(page, point(3, 2));
  await tap(page, point(6, 2));
  await tap(page, point(1, 1));
  await tap(page, point(1, 1));

  // Colour 2, knots on two cells.
  await addColour.tap();
  await knot.tap();
  await tap(page, cell(5, 3));
  await tap(page, cell(0, 3));

  // The eraser removes a knot, then the segment it is tapped on.
  await eraser.tap();
  await tap(page, cell(0, 3));
  await backstitch.tap();
  await tap(page, point(4.5, 2));

  // A full stitch painted last, then undone: undo goes back in the order
  // things were done, so the second undo brings the erased segment back.
  await page.locator("button.badge").nth(1).tap(); // colour 2
  await page.getByRole("button", { name: "Point complet" }).tap();
  await tap(page, cell(0, 0));
  await expect(painted).toHaveText("1 / 24 cases peintes");
  await undo.tap();
  await expect(painted).toHaveText("0 / 24 cases peintes");
  await undo.tap();

  await page.getByRole("button", { name: "Continuer", exact: true }).tap();
  await page.getByRole("button", { name: "Ajouter et commencer" }).tap();
  await expect(page).toHaveURL(/\/track\//);
  const patternId = page.url().split("/track/")[1]!;

  const grid = (await (await request.get(`/api/patterns/${patternId}/grid`)).json()) as {
    backstitch: unknown[];
    french_knots: unknown[];
  };
  expect(grid.backstitch).toEqual([
    { x1: 0, y1: 0, x2: 3, y2: 2, palette_index: 1 },
    { x1: 3, y1: 2, x2: 6, y2: 2, palette_index: 1 },
  ]);
  expect(grid.french_knots).toEqual([{ x: 5.5, y: 3.5, palette_index: 2 }]);

  const detail = (await (await request.get(`/api/patterns/${patternId}`)).json()) as {
    palette: { count_full: number; count_french: number; backstitch_length_cm: number | null }[];
  };
  expect(detail.palette.map((entry) => [entry.count_full, entry.count_french])).toEqual([
    [0, 0],
    [0, 1],
  ]);
  // Default fabric count of the summary step: 14 count.
  expect(detail.palette[0]!.backstitch_length_cm).toBeCloseTo(
    ((Math.hypot(3, 2) + 3) * 2.54) / 14,
  );
});
