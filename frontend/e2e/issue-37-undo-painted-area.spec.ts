import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #37: on the import wizard's Palette step, an "undo" button removes
 * the last painted area — several levels back — and the saved configuration
 * follows, so the created pattern never contains an undone area.
 */

// Smallest valid PNG (1×1 pixel), as in `lot2-manual-import.spec.ts`.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

async function paintedCount(page: Page): Promise<number> {
  const text = await page.getByText(/\d+ \/ 30 cases peintes/).textContent();
  return Number(text?.match(/(\d+) \/ 30/)?.[1]);
}

async function paintArea(page: Page, canvas: Locator, from: [number, number], to: [number, number]) {
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The painting canvas has no bounding box");
  await page.mouse.move(box.x + from[0], box.y + from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + to[0], box.y + to[1], { steps: 4 });
  await page.mouse.up();
}

test.use({ viewport: { width: 375, height: 812 } });

test("the last painted areas can be undone, and the saved configuration follows", async ({
  page,
  request,
}) => {
  await page.goto("/import");
  const created = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/api\/imports$/.test(response.url()),
  );
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles({
    name: "grille-test.png",
    mimeType: "image/png",
    buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
  });
  const jobId = ((await (await created).json()) as { id: string }).id;

  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const undo = page.getByRole("button", { name: "Annuler la dernière zone" });
  await expect(undo).toBeDisabled();

  // Two separate areas: a small one, then a larger one that adds cells.
  await paintArea(page, canvas, [20, 20], [40, 40]);
  await expect.poll(() => paintedCount(page)).toBeGreaterThan(0);
  const afterFirst = await paintedCount(page);
  await paintArea(page, canvas, [50, 20], [90, 70]);
  await expect.poll(() => paintedCount(page)).toBeGreaterThan(afterFirst);

  // One undo: back to the first area only; a second: nothing painted.
  await undo.click();
  await expect.poll(() => paintedCount(page)).toBe(afterFirst);
  const fillsCount = async (): Promise<number> => {
    const job = (await (await request.get(`/api/imports/${jobId}`)).json()) as {
      config: { fills: unknown[] };
    };
    return job.config.fills.length;
  };
  await expect.poll(fillsCount).toBe(1);

  await undo.click();
  await expect.poll(() => paintedCount(page)).toBe(0);
  await expect(undo).toBeDisabled();
  await expect.poll(fillsCount).toBe(0);
});
