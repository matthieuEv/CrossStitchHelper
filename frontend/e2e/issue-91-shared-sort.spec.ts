import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Issue #91: the Library's "Sort" button is also there on the "Shared" tab,
 * and orders the shared patterns by recent activity or by name — a choice
 * remembered apart from the "My patterns" tab's own.
 */

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

/** Puts a copy of the demo pattern, named `name`, in the shared library. */
async function shareCopy(request: APIRequestContext, name: string): Promise<string> {
  const copy = (await (
    await request.post(`/api/patterns/${DEMO_PATTERN_ID}/duplicate`, { data: { name } })
  ).json()) as { id: string };
  const shared = await request.post(`/api/patterns/${copy.id}/share`);
  expect(shared.ok()).toBe(true);
  return ((await shared.json()) as { id: string }).id;
}

async function chooseSort(page: Page, label: string): Promise<void> {
  await page.getByRole("button", { name: "Trier" }).click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await menu.getByRole("menuitemradio", { name: label }).click();
  await expect(menu).toBeHidden();
}

async function sharedOrder(page: Page, names: string[]): Promise<string[]> {
  const titles = await page.locator(".card-title").allTextContents();
  return titles.filter((title) => names.includes(title));
}

test.use({ viewport: { width: 375, height: 812 } });

test("the Shared tab has its own Sort menu: recent activity or name", async ({ page, request }) => {
  const runId = Date.now();
  // Shared in this order: by recent activity "B" comes first, by name "A".
  const first = `A partage tri ${runId}`;
  const second = `B partage tri ${runId}`;
  const sharedIds = [await shareCopy(request, first)];
  // Distinct `updated_at` values, whatever the clock's resolution.
  await page.waitForTimeout(20);
  sharedIds.push(await shareCopy(request, second));

  try {
    await page.goto("/");
    await page.getByRole("tab", { name: "Partagés" }).click();
    await expect(page.locator(".card-title", { hasText: second })).toBeVisible();

    // Only what applies to shared patterns: no progress of their own.
    await page.getByRole("button", { name: "Trier" }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitemradio")).toHaveText(["Activité récente", "Nom (A → Z)"]);
    await page.keyboard.press("Escape");

    await chooseSort(page, "Activité récente");
    expect(await sharedOrder(page, [first, second])).toEqual([second, first]);
    await chooseSort(page, "Nom (A → Z)");
    expect(await sharedOrder(page, [first, second])).toEqual([first, second]);

    // Remembered on this device, apart from "My patterns".
    await page.reload();
    await page.getByRole("tab", { name: "Partagés" }).click();
    await expect(page.locator(".card-title", { hasText: second })).toBeVisible();
    expect(await sharedOrder(page, [first, second])).toEqual([first, second]);
    await page.getByRole("tab", { name: "Mes motifs" }).click();
    await page.getByRole("button", { name: "Trier" }).click();
    await expect(page.getByRole("menuitemradio")).toHaveCount(3);
    await expect(page.getByRole("menuitemradio", { name: "Nom (A → Z)" })).not.toHaveAttribute(
      "aria-checked",
      "true",
    );
  } finally {
    for (const id of sharedIds) await request.delete(`/api/shared/patterns/${id}`);
  }
});
