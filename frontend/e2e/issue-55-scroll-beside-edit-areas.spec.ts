import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

/**
 * Issue #55: on a phone, the import wizard's editing areas (Cropping stage,
 * Palette painting canvas) capture every touch — so a finger placed on them
 * to scroll the page moves the area instead. A strip is kept free on their
 * right, where a vertical swipe scrolls the page, while a swipe on the area
 * itself still belongs to the area.
 *
 * The swipes are real touch scroll gestures (Chromium's
 * `Input.synthesizeScrollGesture`), which honour `touch-action` like a finger
 * does — a mouse wheel would not tell the two apart.
 */

// Smallest valid PNG (1×1 pixel): the dropped file's content does not matter
// here, only the wizard steps it leads to.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";


/** Vertical touch swipe (upwards: scrolls the page down) starting at (x, y). */
async function swipeUp(page: Page, x: number, y: number): Promise<void> {
  const client = await page.context().newCDPSession(page);
  await client.send("Input.synthesizeScrollGesture", {
    x,
    y,
    yDistance: -150,
    gestureSourceType: "touch",
    speed: 600,
  });
  await client.detach();
}

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
 * A swipe on the area does not scroll the page; one in the strip on its right
 * — 30 px from the edge of the screen, on the area itself before the fix —
 * does.
 */
async function expectScrollGutter(page: Page, area: Locator): Promise<void> {
  await pageScrollTop(area, 0);
  // Let the step settle first: focusing a newly added field may still nudge
  // the scroll position by a few pixels, with no gesture involved.
  await page.waitForTimeout(600);
  const baseline = await pageScrollTop(area);

  const box = await area.boundingBox();
  if (box === null) throw new Error("The editing area has no bounding box");
  const viewportWidth = page.viewportSize()?.width ?? 375;
  const y = box.y + Math.min(box.height / 2, 60);

  await swipeUp(page, box.x + box.width / 2, y);
  expect(await pageScrollTop(area)).toBe(baseline);

  await swipeUp(page, viewportWidth - 30, y);
  await expect.poll(() => pageScrollTop(area)).toBeGreaterThan(baseline);
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
