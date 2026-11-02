import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #102: the import wizard's work is never lost. Coming back to the
 * dimensions to change them keeps what is painted afterwards, and reloading
 * the page in the middle of an import brings the wizard back where it was.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

async function paintedCount(page: Page, total: number): Promise<number> {
  const text = await page.getByText(new RegExp(`\\d+ / ${total} cases peintes`)).textContent();
  return Number(text?.match(/(\d+) \//)?.[1]);
}

async function paintArea(page: Page, canvas: Locator, from: [number, number], to: [number, number]) {
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  await page.mouse.move(box.x + from[0], box.y + from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + to[0], box.y + to[1], { steps: 4 });
  await page.mouse.up();
}

async function startImport(page: Page): Promise<string> {
  await page.goto("/import");
  const created = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/api\/imports$/.test(response.url()),
  );
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "grille-102.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  const jobId = ((await (await created).json()) as { id: string }).id;
  await expect(page.getByText("Colonnes")).toBeVisible();
  return jobId;
}

async function setDimensions(page: Page, columns: string, rows: string): Promise<void> {
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill(columns);
  await rowsInput!.fill(rows);
}

test.use({ viewport: { width: 375, height: 812 } });

test("changing the dimensions afterwards keeps what is painted next, up to the created pattern", async ({
  page,
  request,
}) => {
  await startImport(page);
  await setDimensions(page, "6", "5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await paintArea(page, canvas, [20, 20], [40, 40]);
  await expect.poll(() => paintedCount(page, 30)).toBeGreaterThan(0);

  // Rows and columns were swapped: back to the dimensions, then paint more.
  await page.getByRole("button", { name: "Retour", exact: true }).click();
  await setDimensions(page, "5", "6");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await expect(canvas).toBeVisible();
  // The view starts two cells (2 × 16 px) before the grid: from its first
  // cell to its last.
  await paintArea(page, canvas, [34, 34], [110, 126]);
  await expect.poll(() => paintedCount(page, 30)).toBe(30);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  const name = `Issue 102 ${Date.now()}`;
  await page.getByLabel(/Nom du motif/).fill(name);
  const committed = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/commit$/.test(response.url()),
  );
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();
  const patternId = ((await (await committed).json()) as { pattern_id: string }).pattern_id;

  const grid = (await (await request.get(`/api/patterns/${patternId}/grid`)).json()) as {
    width: number;
    height: number;
    layer_full: string;
  };
  expect([grid.width, grid.height]).toEqual([5, 6]);
  // Uint16 per cell, 0 = empty: every one of the 30 cells is painted.
  const bytes = Buffer.from(grid.layer_full, "base64");
  const cells = Array.from({ length: bytes.length / 2 }, (_, i) => bytes.readUInt16LE(i * 2));
  expect(cells.filter((cell) => cell > 0)).toHaveLength(30);
});

test("reloading the page in the middle of an import brings the wizard back where it was", async ({
  page,
}) => {
  const jobId = await startImport(page);
  await setDimensions(page, "6", "5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await paintArea(page, canvas, [20, 20], [40, 40]);
  await expect.poll(() => paintedCount(page, 30)).toBeGreaterThan(0);
  const painted = await paintedCount(page, 30);
  // The painted area is saved in the background: wait for it to reach the job.
  await expect
    .poll(async () => {
      const job = (await (await page.request.get(`/api/imports/${jobId}`)).json()) as {
        config: { fills: unknown[] };
      };
      return job.config.fills.length;
    })
    .toBe(1);

  await page.reload();
  await expect(canvas).toBeVisible();
  await expect.poll(() => paintedCount(page, 30)).toBe(painted);
});

test("cancelling the import forgets it: the next import starts from the file again", async ({
  page,
}) => {
  await startImport(page);
  await setDimensions(page, "6", "5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await expect(page.getByRole("button", { name: /Ajouter une couleur/ })).toBeVisible();

  await page.getByRole("button", { name: "Annuler", exact: true }).first().click();
  await page.goto("/import");
  await expect(page.locator('input[type="file"][accept*="pdf"]')).toBeAttached();
  await expect(page.getByText("Colonnes")).toHaveCount(0);
});
