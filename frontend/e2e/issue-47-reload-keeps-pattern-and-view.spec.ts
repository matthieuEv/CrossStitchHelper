import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Issue #47: reloading the Tracking page must reopen the same pattern at the
 * same spot and zoom, without another pattern showing up in between.
 *
 * Before the fix, the client-side demo patterns were shown while the library
 * was loading (one tracking canvas mounted, then replaced by the real
 * pattern's), and the view always restarted from the default position.
 */

interface PatternSummary {
  id: string;
  name: string;
}

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

async function zoomBadgeSize(page: Page): Promise<number> {
  const text = await page.locator(".track-badges .badge").first().textContent();
  const match = text?.match(/(\d+)\s*px\//);
  if (match?.[1] === undefined) throw new Error(`Zoom badge not found in: ${text}`);
  return Number(match[1]);
}

/** "Ligne 34 · Colonne 38" (or its English counterpart), as shown in the header. */
async function position(page: Page): Promise<string> {
  const text = await page.getByText(/(Ligne|Row) \d+/).textContent();
  if (text === null) throw new Error("Position not found");
  return text;
}

test.use({ viewport: { width: 375, height: 812 } });

test("a reload shows only the requested pattern, never a demo one first", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);

  // Counts every tracking canvas inserted from the very first paint: a
  // pattern shown then replaced by another one inserts two.
  await page.addInitScript(() => {
    const w = window as unknown as { __trackCanvasMounts: number };
    w.__trackCanvasMounts = 0;
    new MutationObserver((records) => {
      for (const record of records) {
        record.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          if (node.matches("canvas.track-canvas")) w.__trackCanvasMounts += 1;
          w.__trackCanvasMounts += node.querySelectorAll("canvas.track-canvas").length;
        });
      }
    }).observe(document, { childList: true, subtree: true });
  });

  await page.goto(`/track/${encodeURIComponent(pattern.id)}`);
  await expect(page.getByText(pattern.name).first()).toBeVisible();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  // Leave time for any late replacement to happen before counting.
  await page.waitForTimeout(500);

  const mounts = await page.evaluate(
    () => (window as unknown as { __trackCanvasMounts: number }).__trackCanvasMounts,
  );
  expect(mounts).toBe(1);
});

test("a reload keeps the zoom level and the position in the pattern", async ({ page, request }) => {
  const pattern = await fetchDemoPattern(request);
  const canvas = page.locator("canvas.track-canvas");

  // The header shows the view's position only while the pointer hovers no
  // cell (otherwise it shows the hovered cell): every reading below is taken
  // right after a load, before the pointer ever touches the grid.
  const readAfterLoad = async (): Promise<{ zoom: number; position: string }> => {
    await expect(canvas).toBeVisible();
    return { zoom: await zoomBadgeSize(page), position: await position(page) };
  };

  await page.goto(`/track/${encodeURIComponent(pattern.id)}`);
  const before = await readAfterLoad();

  // Move away from wherever a previous run left the view (zoom, then pan),
  // in whichever direction is not already at its bound, so the stored view
  // is always the one from this run.
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("The tracking canvas has no bounding box");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, before.zoom > 16 ? 300 : -300);
  await expect.poll(() => zoomBadgeSize(page)).not.toBe(before.zoom);
  const column = Number(before.position.match(/(\d+)\D*$/)?.[1] ?? 0);
  await page.mouse.wheel(column > 100 ? -400 : 400, 0);

  // Reloaded right after the gesture, within the save debounce delay: the
  // last move must not be lost.
  await page.reload();
  const afterReload = await readAfterLoad();
  expect(afterReload.zoom).not.toBe(before.zoom);
  expect(afterReload.position).not.toBe(before.position);

  // And it stays put across further reloads.
  await page.reload();
  expect(await readAfterLoad()).toEqual(afterReload);
});
