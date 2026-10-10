import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

/**
 * Issue #55: on a phone, the import wizard's editing areas (Cropping stage,
 * Palette painting canvas) capture every touch — so a finger placed on them
 * to scroll the page moves the area instead. A strip is kept free on their
 * right, where a vertical swipe scrolls the page, while a swipe on the area
 * itself still belongs to the area.
 *
 * What a finger does is read from the browser's own rules rather than from a
 * synthesised gesture: the element it lands on (hit testing), and whether
 * `touch-action` lets a vertical swipe from there reach the scrolling pane.
 * Chromium's synthesised touch gestures (`Input.synthesizeScrollGesture`)
 * scroll on macOS but not on CI's headless Linux, where they left the page
 * still with the strip measured free — a test that passed or failed with the
 * platform, not with the fix. A mouse wheel would not tell the two apart.
 */

// Smallest valid PNG (1×1 pixel): the dropped file's content does not matter
// here, only the wizard steps it leads to.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

/** A thumb-wide strip: Apple's minimum touch target. */
const STRIP = 44;

/**
 * Scroll position of the area's scrolling ancestor (the wizard's content
 * pane), set to `reset` first when given.
 */
async function pageScrollTop(area: Locator, reset?: number): Promise<number> {
  return area.evaluate((element, value) => {
    let node = element.parentElement;
    while (node !== null && !["auto", "scroll"].includes(getComputedStyle(node).overflowY)) {
      node = node.parentElement;
    }
    if (node === null) throw new Error("No scrolling ancestor");
    if (value !== undefined) node.scrollTop = value;
    return node.scrollTop;
  }, reset);
}

/**
 * Where a finger put down at (x, y) lands, and whether a vertical swipe from
 * there scrolls the page: no element between that point and its scrolling
 * container (`overflow-y: auto`) forbids vertical panning (`touch-action`).
 * Whether that container currently overflows is left out: it depends on the
 * rest of the step's layout, not on the strip.
 */
async function touchAt(
  area: Locator,
  x: number,
  y: number,
): Promise<{ inArea: boolean; scrollsPage: boolean }> {
  return area.evaluate(
    (element, [px, py]) => {
      const hit = document.elementFromPoint(px, py);
      if (hit === null) throw new Error(`Nothing at (${px}, ${py})`);
      let pansVertically = true;
      let node: Element | null = hit;
      while (node !== null) {
        const style = getComputedStyle(node);
        const action = style.touchAction;
        if (action !== "auto" && action !== "manipulation" && !action.includes("pan-y")) {
          pansVertically = false;
        }
        if (["auto", "scroll"].includes(style.overflowY)) break;
        node = node.parentElement;
      }
      return { inArea: element.contains(hit), scrollsPage: pansVertically && node !== null };
    },
    [x, y] as const,
  );
}

/**
 * A finger on the area belongs to the area; a strip at least a thumb wide is
 * left free on its right, inside the screen, where a swipe scrolls the page.
 * Before the fix the area stretched to 20 px from the edge of the screen.
 */
async function expectScrollGutter(page: Page, area: Locator): Promise<void> {
  await pageScrollTop(area, 0);
  // Let the step settle first: focusing a newly added field may still nudge
  // the scroll position by a few pixels.
  await page.waitForTimeout(600);

  const box = await area.boundingBox();
  if (box === null) throw new Error("The editing area has no bounding box");
  const viewportWidth = page.viewportSize()?.width ?? 375;
  const y = box.y + Math.min(box.height / 2, 60);

  expect(await touchAt(area, box.x + box.width / 2, y)).toEqual({
    inArea: true,
    scrollsPage: false,
  });

  const right = box.x + box.width;
  expect(right + STRIP).toBeLessThanOrEqual(viewportWidth);
  expect(await touchAt(area, right + STRIP / 2, y)).toEqual({ inArea: false, scrollsPage: true });
}

/**
 * Two touch devices on which the wizard really scrolls (measured): a phone
 * with Safari's bars shown, and an iPad in landscape — the wide layout, where
 * the areas used to leave only 20 px free on their right.
 */
const DEVICES = [
  { name: "phone", viewport: { width: 375, height: 560 } },
  { name: "iPad landscape", viewport: { width: 1180, height: 820 } },
] as const;

async function newTouchPage(browser: Browser, viewport: { width: number; height: number }): Promise<Page> {
  const context = await browser.newContext({ viewport, hasTouch: true });
  return context.newPage();
}

for (const device of DEVICES) {
  test(`the page scrolls from the strip beside the Cropping and Palette areas (${device.name})`, async ({
    browser,
  }) => {
    const page = await newTouchPage(browser, device.viewport);
    await page.goto("/import");
    await page
      .locator('input[type="file"][accept*="pdf"]')
      .setInputFiles({
        name: "grille-test.png",
        mimeType: "image/png",
        buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
      });

    // Cropping step.
    await expect(page.getByText("Colonnes")).toBeVisible();
    await expectScrollGutter(page, page.locator(".crop-stage"));

    const [columnsInput, rowsInput] = await page.locator("input.input").all();
    await columnsInput!.fill("6");
    await rowsInput!.fill("5");
    await page.getByRole("button", { name: "Continuer", exact: true }).click();

    // Palette step: the painting canvas only appears once a colour exists.
    await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
    await expect(page.locator("canvas.track-canvas")).toBeVisible();
    await expectScrollGutter(page, page.locator(".track-canvas-wrap"));

    await page.context().close();
  });
}
