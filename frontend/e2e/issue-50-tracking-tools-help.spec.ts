import { expect, test } from "@playwright/test";

/**
 * Issue #50: the Tracking toolbars show icons only — a "Tool help" button
 * opens a key giving every toolbar button's name and what it does, in the
 * same order and with the same names as the toolbars themselves.
 */

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

test.use({ viewport: { width: 375, height: 812 } });

test("the tool help names and explains every toolbar button", async ({ page, request }) => {
  const patterns = (await (await request.get("/api/patterns")).json()) as Array<{
    id: string;
    name: string;
  }>;
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");

  await page.goto(`/track/${DEMO_PATTERN_ID}`);
  // The real pattern's title first: until the library has loaded, a demo
  // pattern may briefly be shown in its place and then replaced (issue #47),
  // which would also close a help opened in the meantime.
  await expect(page.getByText(demo.name)).toBeVisible();
  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  // Every button of both toolbars, by its accessible name.
  const toolbarNames = async (name: string): Promise<string[]> =>
    page
      .getByRole("toolbar", { name })
      .getByRole("button")
      .evaluateAll((buttons) => buttons.map((button) => button.getAttribute("aria-label") ?? ""));
  const tools = await toolbarNames("Suivi");
  const layers = await toolbarNames("Catégorie de point");
  expect(tools.length).toBeGreaterThan(5);
  expect(layers).toHaveLength(5);

  await page.getByRole("button", { name: "Aide des outils" }).click();
  const help = page.getByRole("dialog", { name: "À quoi servent les outils" });
  await expect(help).toBeVisible();

  // Each toolbar button has an entry with a non-empty explanation.
  const entries = help.getByRole("listitem");
  await expect(entries).toHaveCount(tools.length + layers.length);
  for (const name of [...tools, ...layers]) {
    const exact = new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
    const entry = entries.filter({ has: page.locator("strong", { hasText: exact }) });
    await expect(entry, name).toHaveCount(1);
    const text = (await entry.textContent()) ?? "";
    expect(text.length, name).toBeGreaterThan(name.length + 20);
  }

  await help.getByRole("button", { name: "Fermer" }).click();
  await expect(help).toBeHidden();
});
