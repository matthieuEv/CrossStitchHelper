import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #83, part 2: the import brush paints 3/4 stitches, and 1/4 and 3/4
 * stitches in a chosen corner — a split cell (a 3/4 and a 1/4 of another
 * colour in its free corner) reaches the created pattern as such.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

// The brush opens at 16 px per cell with two cells of margin
// (`useImportPainter`): the centre of cell (x, y) in canvas pixels.
const at = (x: number, y: number): [number, number] => [32 + 16 * x + 8, 32 + 16 * y + 8];

async function paintArea(page: Page, canvas: Locator, from: [number, number], to: [number, number]) {
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  await page.mouse.move(box.x + from[0], box.y + from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + to[0], box.y + to[1], { steps: 4 });
  await page.mouse.up();
}

interface PartialStitch {
  x: number;
  y: number;
  corner: string;
  palette_index: number;
}

test.use({ viewport: { width: 375, height: 812 } });

test("the brush paints 1/4 and 3/4 stitches in a corner, split cells included", async ({
  page,
  request,
}) => {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "coins.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("3");
  await rowsInput!.fill("1");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const canvas = page.locator("canvas.track-canvas");
  const corners = page.getByRole("group", { name: "Coin du point" });
  const painted = page.getByText(/\d+ \/ 3 cases peintes/);

  // No corner to pick for a full stitch.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await expect(corners).toHaveCount(0);

  // Colour 1: 3/4 stitches in the top-left corner (the default), cells 0–1.
  await page.getByRole("button", { name: "Point 3/4" }).click();
  await expect(corners).toBeVisible();
  await expect(corners.getByRole("button", { name: "Coin en haut à gauche" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText(/le coin de sa petite jambe/)).toBeVisible();
  await paintArea(page, canvas, at(0, 0), at(1, 0));
  await expect(painted).toHaveText("2 / 3 cases peintes");

  // Colour 2: a 1/4 in the free (bottom-right) corner of cell 0 — a split
  // cell — and a 1/4 top-right on cell 2.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await page.getByRole("button", { name: "Point 1/4" }).click();
  await expect(page.getByText(/le coin de sa petite jambe/)).toHaveCount(0);
  await corners.getByRole("button", { name: "Coin en bas à droite" }).click();
  await paintArea(page, canvas, at(0, 0), at(0, 0));
  await corners.getByRole("button", { name: "Coin en haut à droite" }).click();
  await paintArea(page, canvas, at(2, 0), at(2, 0));
  await expect(painted).toHaveText("3 / 3 cases peintes");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();
  await expect(page).toHaveURL(/\/track\//);
  const patternId = page.url().split("/track/")[1]!;

  const grid = (await (await request.get(`/api/patterns/${patternId}/grid`)).json()) as {
    quarter_stitches: PartialStitch[];
    three_quarter_stitches: PartialStitch[];
  };
  expect(grid.three_quarter_stitches).toEqual([
    { x: 0, y: 0, corner: "tl", palette_index: 1 },
    { x: 1, y: 0, corner: "tl", palette_index: 1 },
  ]);
  expect(grid.quarter_stitches).toEqual([
    { x: 0, y: 0, corner: "br", palette_index: 2 },
    { x: 2, y: 0, corner: "tr", palette_index: 2 },
  ]);
});
