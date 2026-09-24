import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Checks the "done when" criterion of Lot 8's "Data backup/restore"
 * sub-project (docs/roadmap.md, specification §7.5): from Settings, export a
 * downloadable .json file, restore it (exact server state, progress
 * included), toggle the daily automatic backup, and clear all data — against
 * a real backend (`app/backup.py`, `app/api/backup.py`), not mocks.
 *
 * The last test is destructive by nature ("clear all data"): it immediately
 * restores the state captured just before, so that the repository's other
 * spec files (which all assume the demo pattern is present) stay correct
 * whatever the order in which files run — the same "clear before filling"
 * discipline as in lot1-persistence.spec.ts, adapted to an operation that
 * destroys rather than fills.
 */

const DEMO_PATTERN_ID = "demo-perf-255x180";

interface PatternSummary {
  id: string;
  name: string;
  cell_count: number;
}

async function fetchDemoPattern(request: APIRequestContext): Promise<PatternSummary> {
  const response = await request.get("/api/patterns");
  const patterns = (await response.json()) as PatternSummary[];
  const demo = patterns.find((pattern) => pattern.id === DEMO_PATTERN_ID);
  if (demo === undefined) throw new Error("Demo pattern not found in the database");
  return demo;
}

async function setStitched(
  request: APIRequestContext,
  patternId: string,
  index: number,
  stitched: boolean,
): Promise<void> {
  const response = await request.post(`/api/patterns/${patternId}/progress`, {
    data: { base_version: 0, ops: [{ layer: "full", index, stitched }] },
  });
  if (!response.ok()) {
    throw new Error(`Progress update failed (full#${index}): ${response.status()}`);
  }
}

function bitSet(base64: string, index: number): boolean {
  const byte = Buffer.from(base64, "base64")[index >> 3] ?? 0;
  return ((byte >> (index & 7)) & 1) === 1;
}

async function fetchFullBitmap(request: APIRequestContext, patternId: string): Promise<string> {
  const response = await request.get(`/api/patterns/${patternId}/progress`);
  const body = (await response.json()) as { bitmap: string };
  return body.bitmap;
}

async function fetchBackupDocument(request: APIRequestContext): Promise<unknown> {
  const response = await request.get("/api/backup");
  return response.json();
}

function writeTempJson(name: string, data: unknown): string {
  const filePath = path.join(os.tmpdir(), name);
  fs.writeFileSync(filePath, JSON.stringify(data));
  return filePath;
}

test.describe("Lot 8 — data backup/restore", () => {
  test("exporting then restoring brings back the demo pattern's exact progress", async ({
    page,
    request,
  }) => {
    const pattern = await fetchDemoPattern(request);
    const snapshot = await fetchBackupDocument(request);

    // A real observable toggle, not "nothing changed by chance": flip a
    // stitch far from anything the other specs watch (the grid's last cell),
    // then check it is indeed flipped before relying on the restore to bring
    // it back.
    const probeIndex = pattern.cell_count - 1;
    const wasStitchedBefore = bitSet(await fetchFullBitmap(request, pattern.id), probeIndex);
    await setStitched(request, pattern.id, probeIndex, !wasStitchedBefore);
    expect(bitSet(await fetchFullBitmap(request, pattern.id), probeIndex)).toBe(!wasStitchedBefore);

    const backupFile = writeTempJson("csh-e2e-backup-restore.json", snapshot);

    await page.goto("/");
    await page.getByRole("button", { name: "Réglages", exact: true }).click();
    await expect(page.getByRole("link", { name: "Exporter (.json)" })).toBeVisible();

    const reloaded = page.waitForEvent("load");
    page.once("dialog", (dialog) => void dialog.accept());
    // The hidden input behind the "Restaurer une sauvegarde" (Restore a
    // backup) button accepts a file directly, without going through the OS's
    // native picker (not drivable by Playwright) — `setInputFiles` works on a
    // hidden input, exactly the mechanism used by `SettingsScreen.tsx`.
    await page.locator('input[type="file"]').setInputFiles(backupFile);
    await reloaded;

    const after = bitSet(await fetchFullBitmap(request, pattern.id), probeIndex);
    expect(after).toBe(wasStitchedBefore); // back to the state before the probe.
  });

  test("the export button points to a real JSON download", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Réglages", exact: true }).click();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Exporter (.json)" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);

    const downloadPath = await download.path();
    expect(downloadPath).not.toBeNull();
    const content = JSON.parse(fs.readFileSync(downloadPath as string, "utf-8")) as {
      format: string;
      format_version: number;
    };
    expect(content.format).toBe("csh-backup");
    expect(content.format_version).toBe(1);
  });

  test("the daily automatic backup can be toggled from Settings", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Réglages", exact: true }).click();
    const toggle = page.getByRole("switch", { name: "Sauvegarde automatique quotidienne" });

    // Enabled by default (`app/auto_backup.py::is_auto_backup_enabled`) as
    // long as no other spec has already toggled this global server setting —
    // so start from the state read, not from an assumed "true", and always
    // return to that starting state at the end of the test.
    const initiallyChecked = (await toggle.getAttribute("aria-checked")) === "true";

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", String(!initiallyChecked));
    const afterToggle = await request.get("/api/backup/auto");
    expect(((await afterToggle.json()) as { enabled: boolean }).enabled).toBe(!initiallyChecked);

    await toggle.click(); // back to the starting state so other specs are unaffected.
    await expect(toggle).toHaveAttribute("aria-checked", String(initiallyChecked));
  });

  test("clearing all data empties the instance (then a safety restore)", async ({
    page,
    request,
  }) => {
    // Captured just before clearing, not assumed: the repository's other spec
    // files (type A/B/C/E imports, recipes…) may already have created patterns
    // other than the demo on this same shared database — exactly how many
    // depends on the order in which files run, so never a hard-coded value
    // here.
    const before = (await fetchBackupDocument(request)) as { patterns: Array<{ id: string }> };

    await page.goto("/");
    await page.getByRole("button", { name: "Réglages", exact: true }).click();

    const reloaded = page.waitForEvent("load");
    page.once("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: "Effacer toutes les données" }).click();
    await reloaded;

    const emptied = await request.get("/api/patterns");
    expect(await emptied.json()).toEqual([]);

    const restoreResponse = await request.post("/api/backup/restore", { data: before });
    expect(restoreResponse.ok()).toBe(true);
    const restoredPatterns = (await (await request.get("/api/patterns")).json()) as PatternSummary[];
    expect(restoredPatterns.map((pattern) => pattern.id).sort()).toEqual(
      before.patterns.map((pattern) => pattern.id).sort(),
    );
    expect(restoredPatterns.some((pattern) => pattern.id === DEMO_PATTERN_ID)).toBe(true);
  });
});
