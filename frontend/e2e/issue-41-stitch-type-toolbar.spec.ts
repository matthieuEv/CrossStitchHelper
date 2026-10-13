import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #41: on the import wizard's Palette step, a stitch-type toolbar
 * (full / 1/2 / 1/4) picks what the brush paints, and the painted 1/2 and
 * 1/4 stitches reach the created pattern. A cell painted by hand holds one
 * stitch type: repainting it as 1/2 replaces its full stitch.
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

test.use({ viewport: { width: 375, height: 812 } });

test("the brush paints full, 1/2 and 1/4 stitches into the created pattern", async ({
  page,
  request,
}) => {
  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "points-partiels.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("4");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const canvas = page.locator("canvas.track-canvas");
  const full = page.getByRole("button", { name: "Point complet" });
  const half = page.getByRole("button", { name: "Point 1/2" });
  const quarter = page.getByRole("button", { name: "Point 1/4" });
  const painted = page.getByText(/\d+ \/ 24 cases peintes/);

  // Colour 1, full stitches (the default): row 0.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await expect(full).toHaveAttribute("aria-pressed", "true");
  await paintArea(page, canvas, at(0, 0), at(5, 0));
  await expect(painted).toHaveText("6 / 24 cases peintes");

  // Colour 2: 1/2 stitches on row 1, 1/4 stitches on row 2.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  await half.click();
  await expect(half).toHaveAttribute("aria-pressed", "true");
  await paintArea(page, canvas, at(0, 1), at(5, 1));
  await quarter.click();
  await paintArea(page, canvas, at(0, 2), at(5, 2));
  await expect(painted).toHaveText("18 / 24 cases peintes");

  // Repainting a full stitch as 1/2 replaces it rather than adding to it.
  await half.click();
  await paintArea(page, canvas, at(0, 0), at(0, 0));
  await expect(painted).toHaveText("18 / 24 cases peintes");

  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();
  await expect(page).toHaveURL(/\/track\//);
  const patternId = page.url().split("/track/")[1]!;

  const detail = (await (await request.get(`/api/patterns/${patternId}`)).json()) as {
    palette: { count_full: number; count_half: number; count_quarter: number }[];
  };
  expect(
    detail.palette.map((entry) => [entry.count_full, entry.count_half, entry.count_quarter]),
  ).toEqual([
    [5, 0, 0],
    [0, 7, 6],
  ]);
});
