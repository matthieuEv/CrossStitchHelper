import { expect, test } from "@playwright/test";

/**
 * A library card says when the pattern was last stitched. Three things went
 * wrong:
 * - the server sent its times without a time zone, so a browser in Paris
 *   read them two hours off ("2 hours ago" for a pattern just changed). CI
 *   runs in UTC, where this does not show: this spec runs the browser on
 *   Paris time on purpose;
 * - under an hour, the card could only say "1 hour ago";
 * - the age was frozen when the library loaded, and stitching did not move
 *   it on.
 */

/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

test.use({ viewport: { width: 375, height: 812 }, locale: "fr-FR", timezoneId: "Europe/Paris" });

test("a pattern changed a moment ago reads « il y a 1 minute », whatever the time zone", async ({
  page,
  request,
}) => {
  const name = `e2e âge ${Date.now() % 100000}`;
  const created = await request.post(`/api/patterns/${DEMO_PATTERN_ID}/duplicate`, { data: { name } });
  expect(created.ok()).toBe(true);
  const copy = (await created.json()) as { id: string };

  try {
    // The time carries its offset: no browser can read it as its own local time.
    const summaries = (await (await request.get("/api/patterns")).json()) as Array<{
      id: string;
      updated_at: string;
    }>;
    expect(summaries.find((summary) => summary.id === copy.id)?.updated_at).toMatch(
      /(Z|[+-]\d{2}:\d{2})$/,
    );

    await page.goto("/");
    const card = page.locator(".library-card", { hasText: name });
    await expect(card).toContainText("il y a 1 minute");
  } finally {
    await request.delete(`/api/patterns/${copy.id}`);
  }
});

test("stitching moves the card's age on, and an age is worked out when shown", async ({
  page,
  request,
}) => {
  const name = `e2e âge brodé ${Date.now() % 100000}`;
  const created = await request.post(`/api/patterns/${DEMO_PATTERN_ID}/duplicate`, { data: { name } });
  expect(created.ok()).toBe(true);
  const copy = (await created.json()) as { id: string };

  try {
    // The browser believes it is 3 hours later: the copy was made 3 hours ago.
    await page.clock.setFixedTime(Date.now() + 3 * 3_600_000);
    await page.goto("/");
    const card = page.locator(".library-card", { hasText: name });
    await expect(card).toContainText("il y a 3 heures");

    await card.click();
    const canvas = page.locator("canvas.track-canvas");
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    if (box === null) throw new Error("The tracking canvas has no bounding box");
    await page.getByRole("button", { name: "Sélectionner une zone" }).click();
    await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.7, { steps: 5 });
    await page.mouse.up();
    await page.getByRole("button", { name: "Cocher la zone", exact: true }).click();

    // Back to the library, which is not reloaded: the card follows anyway.
    await page.getByRole("button", { name: "Retour" }).click();
    await expect(card).toContainText("il y a 1 minute");
  } finally {
    await request.delete(`/api/patterns/${copy.id}`);
  }
});
