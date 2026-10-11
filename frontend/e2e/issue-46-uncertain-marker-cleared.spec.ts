import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * Issue #46: painting over a cell flagged uncertain by automatic detection
 * (Import > Palette) must resolve it — the ⚠ marker and the "N cell(s)
 * marked" count under the brush drop that cell, whatever colour was painted.
 * Before the fix the count never moved, since it was computed from the
 * detection result alone, ignoring the areas painted by hand.
 */

/** Type C fixture whose detection flags uncertain cells. Measured: 611 on
 * main, still 38 once the PDF legend drives the palette (issue #44), whereas
 * botanical-citrus-dmc drops to none. */
const WINTER_WREATH_PATH = fileURLToPath(
  new URL("../../fixtures/winter-wreath-dmc/PATASS117_2C_2.pdf", import.meta.url),
);

const DETECTION_TIMEOUT = 90_000;
/** The brush's uncertainty hint, matched on its count part only: its wording
 *  is not what this test is about. */
const UNCERTAIN_HINT = /case\(s\) marquée\(s\)/;
/** `useImportPainter`'s initial zoom and offset, in px per cell and cells. */
const CELL = 16;
const START_OFFSET = -2;

async function uncertainHintCount(page: Page): Promise<number> {
  const text = await page.getByText(UNCERTAIN_HINT).textContent();
  const match = /(\d+) case/.exec(text ?? "");
  if (match === null) throw new Error(`unexpected hint text: ${text}`);
  return Number(match[1]);
}

test("painting over an uncertain cell removes it from the uncertainty marker count", async ({
  page,
}) => {
  test.setTimeout(120_000);

  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/imports") && response.request().method() === "POST",
  );
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(WINTER_WREATH_PATH);
  const jobId = ((await (await created).json()) as { id: string }).id;

  await expect(page.getByText(/Détection automatique : type C/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  const job = (await (await page.request.get(`/api/imports/${jobId}`)).json()) as {
    config: { columns: number; rows: number; uncertain_cells: number[] | null };
  };
  const { columns, rows } = job.config;
  const uncertain = job.config.uncertain_cells ?? [];
  expect(uncertain.length).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();
  await expect(page.getByText(UNCERTAIN_HINT)).toBeVisible();
  const before = await uncertainHintCount(page);
  expect(before).toBe(uncertain.length);

  // Pan the brush so that the first uncertain cell sits a few cells from the
  // top-left corner of the canvas — same clamping as `useImportPainter.setOffset`.
  const target = uncertain[0]!;
  const cx = target % columns;
  const cy = Math.floor(target / columns);
  const clamp = (value: number, dimension: number): number => {
    const margin = Math.max(6, dimension * 0.1);
    return Math.max(-margin, Math.min(dimension - margin, value));
  };
  const x0 = clamp(cx - 3, columns);
  const y0 = clamp(cy - 3, rows);

  const canvas = page.locator("canvas.track-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;

  await page.getByRole("button", { name: "Déplacer", exact: true }).click();
  // Drags stay inside the canvas (leaving it ends the gesture), so a long
  // pan is split into several shorter ones.
  let remainingX = (x0 - START_OFFSET) * CELL;
  let remainingY = (y0 - START_OFFSET) * CELL;
  const maxStepX = box.width - 40;
  const maxStepY = box.height - 40;
  while (Math.abs(remainingX) > 0.01 || Math.abs(remainingY) > 0.01) {
    const stepX = Math.sign(remainingX) * Math.min(Math.abs(remainingX), maxStepX);
    const stepY = Math.sign(remainingY) * Math.min(Math.abs(remainingY), maxStepY);
    const startX = stepX >= 0 ? box.x + box.width - 20 : box.x + 20;
    const startY = stepY >= 0 ? box.y + box.height - 20 : box.y + 20;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX - stepX, startY - stepY, { steps: 8 });
    await page.mouse.up();
    remainingX -= stepX;
    remainingY -= stepY;
  }

  // Paint that single cell with the first palette colour (selected by
  // default): a tap is a one-cell selection.
  await page.getByRole("button", { name: "Peindre", exact: true }).click();
  // Measured again: the page may have scrolled since (button focus).
  const paintBox = (await canvas.boundingBox())!;
  await page.mouse.click(
    paintBox.x + (cx - x0 + 0.5) * CELL,
    paintBox.y + (cy - y0 + 0.5) * CELL,
  );

  await expect.poll(() => uncertainHintCount(page)).toBe(before - 1);

  // The correction is persisted (sent in the background, hence the poll) as
  // a fill zone over exactly that cell.
  await expect
    .poll(async () => {
      const after = (await (await page.request.get(`/api/imports/${jobId}`)).json()) as {
        config: { fills: { x0: number; y0: number; x1: number; y1: number }[] };
      };
      return after.config.fills.map(({ x0, y0, x1, y1 }) => ({ x0, y0, x1, y1 }));
    })
    .toEqual([{ x0: cx, y0: cy, x1: cx, y1: cy }]);

  expect(pageErrors).toEqual([]);
});
