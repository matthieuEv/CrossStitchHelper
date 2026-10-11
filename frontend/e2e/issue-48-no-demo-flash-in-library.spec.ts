import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Issue #48: once the server holds patterns, (re)loading the Library must
 * only ever list them — never the built-in demo patterns first, whose sudden
 * disappearance a moment later looks like patterns being deleted.
 */

interface PatternSummary {
  id: string;
  name: string;
}

async function fetchPatternNames(request: APIRequestContext): Promise<string[]> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  if (patterns.length === 0) throw new Error("No pattern in the database");
  return patterns.map((pattern) => pattern.name);
}

test.use({ viewport: { width: 375, height: 812 } });

test("a reload of the Library lists only the server's patterns, from the first paint", async ({
  page,
  request,
}) => {
  const names = await fetchPatternNames(request);

  // Records every card title ever rendered, from the very first paint.
  await page.addInitScript(() => {
    const w = window as unknown as { __cardTitles: Set<string> };
    w.__cardTitles = new Set();
    new MutationObserver(() => {
      document.querySelectorAll(".card-title").forEach((title) => {
        if (title.textContent) w.__cardTitles.add(title.textContent);
      });
    }).observe(document, { childList: true, subtree: true, characterData: true });
  });

  await page.goto("/");
  await expect(page.locator(".card-title").first()).toBeVisible();
  await page.reload();
  await expect(page.locator(".card-title").first()).toBeVisible();
  // Leave time for any late replacement to happen before reading.
  await page.waitForTimeout(500);

  const seen = await page.evaluate(() => [
    ...(window as unknown as { __cardTitles: Set<string> }).__cardTitles,
  ]);
  expect(seen.sort()).toEqual([...new Set(names)].sort());
});
