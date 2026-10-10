import { fileURLToPath } from "node:url";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Issue #45: the cells flagged uncertain by automatic detection must be easy
 * to find on the import brush — an example of the marker next to its
 * explanation, a "Show next" button that brings each flagged cell into view,
 * and a marker that is still drawn once zoomed all the way out (it used to
 * disappear below a few pixels per cell, i.e. on the overview of a large
 * grid).
 */

/** Type C fixture whose detection flags uncertain cells. Measured: 611 on
 * main, still 38 once the PDF legend drives the palette (issue #44), whereas
 * botanical-citrus-dmc drops to none. */
const FIXTURE_PATH = fileURLToPath(
  new URL("../../fixtures/winter-wreath-dmc/PATASS117_2C_2.pdf", import.meta.url),
);
const DETECTION_TIMEOUT = 120_000;

/** RGB of the canvas pixel at `(x, y)` CSS pixels from the canvas's top-left corner. */
async function pixelAt(canvas: Locator, x: number, y: number): Promise<[number, number, number]> {
  return canvas.evaluate(
    (element, [cssX, cssY]) => {
      const node = element as HTMLCanvasElement;
      const scale = node.width / node.getBoundingClientRect().width;
      const data = node
        .getContext("2d")!
        .getImageData(Math.round(cssX * scale), Math.round(cssY * scale), 1, 1).data;
      return [data[0]!, data[1]!, data[2]!] as [number, number, number];
    },
    [x, y] as const,
  );
}

async function accentColour(page: Page): Promise<[number, number, number]> {
  return page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.color = "var(--color-accent)";
    document.body.append(probe);
    const match = getComputedStyle(probe).color.match(/\d+/g) ?? [];
    probe.remove();
    return [Number(match[0]), Number(match[1]), Number(match[2])] as [number, number, number];
  });
}

function isClose(a: [number, number, number], b: [number, number, number]): boolean {
  return a.every((value, i) => Math.abs(value - b[i]!) <= 6);
}

test.use({ viewport: { width: 375, height: 812 } });

test("uncertain cells are shown by example, reachable one by one, and visible zoomed out", async ({
  page,
}) => {
  test.setTimeout(180_000);

  await page.goto("/import");
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);
  await expect(page.getByText(/Détection automatique/)).toBeVisible({ timeout: DETECTION_TIMEOUT });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();

  // An example of the marker sits next to its explanation.
  await expect(page.getByText(/case\(s\) marquée\(s\) de ce repère/)).toBeVisible();
  await expect(page.locator(".uncertain-sample")).toBeVisible();

  const accent = await accentColour(page);
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The brush canvas has no bounding box");
  const centre = { x: box.width / 2, y: box.height / 2 };

  // "Show next" centres a flagged cell, zoomed in: its corner triangle (top
  // right of the centred cell) is drawn in the accent colour — read a few
  // pixels inside it, away from the anti-aliased edges a flagged neighbour's
  // marker may overlap.
  await page.getByRole("button", { name: "Voir la suivante" }).click();
  await page.waitForTimeout(200);
  const cellSize = 20; // `useImportPainter.ts::FOCUS_MIN_CELL`, from the initial 16 px.
  await expect
    .poll(async () =>
      isClose(await pixelAt(canvas, centre.x + cellSize / 2 - 4, centre.y - cellSize / 2 + 3), accent),
    )
    .toBe(true);

  // Zoomed all the way out with the "−" button (the pointer never hovers
  // the canvas: the cursor overlay is drawn in the accent colour too). The
  // button keeps the view's origin, so the cell centred at 20 px ends up at
  // a tenth of the canvas once at the minimum 4 px — where the marker, larger
  // than the cell, must still be drawn.
  const zoomOut = page.getByRole("button", { name: "Dézoomer" });
  for (let i = 0; i < 6; i++) await zoomOut.click();
  await page.waitForTimeout(200);
  await expect
    .poll(async () =>
      isClose(await pixelAt(canvas, (centre.x * 4) / cellSize, (centre.y * 4) / cellSize), accent),
    )
    .toBe(true);
});
