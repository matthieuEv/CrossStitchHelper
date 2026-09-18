import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du sous-chantier "Sauvegarde/restauration
 * des données" du Lot 8 (docs/roadmap.md, cahier des charges §7.5) : depuis
 * les Réglages, exporter un fichier .json téléchargeable, le restaurer (état
 * serveur exact, y compris la progression), activer/désactiver la sauvegarde
 * automatique quotidienne, et effacer toutes les données — contre un vrai
 * backend (`app/backup.py`, `app/api/backup.py`), pas des mocks.
 *
 * Le dernier test est destructeur par nature (« effacer toutes les
 * données ») : il restaure immédiatement l'état capturé juste avant, pour
 * que les autres fichiers de spec de ce dépôt (qui supposent tous le motif
 * de démonstration présent) restent corrects quel que soit l'ordre
 * d'exécution des fichiers — même discipline que « vider avant de remplir »
 * dans lot1-persistence.spec.ts, adaptée à une opération qui détruit plutôt
 * que remplit.
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
  if (demo === undefined) throw new Error("Motif de démonstration introuvable en base");
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
    throw new Error(`Échec de la mise à jour de progression (full#${index}) : ${response.status()}`);
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

test.describe("Lot 8 — sauvegarde/restauration des données", () => {
  test("exporter puis restaurer ramène la progression exacte du motif de démonstration", async ({
    page,
    request,
  }) => {
    const pattern = await fetchDemoPattern(request);
    const snapshot = await fetchBackupDocument(request);

    // Une vraie bascule observable, pas "rien n'a changé par hasard" : on
    // inverse un point loin de tout ce que les autres specs surveillent
    // (dernière case de la grille), puis on vérifie qu'elle est bien
    // inversée avant de compter sur la restauration pour la ramener.
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
    // L'input caché derrière le bouton « Restaurer une sauvegarde » accepte
    // un fichier directement, sans passer par le sélecteur natif de l'OS
    // (non pilotable par Playwright) — `setInputFiles` fonctionne sur un
    // input caché, exactement le mécanisme utilisé par `SettingsScreen.tsx`.
    await page.locator('input[type="file"]').setInputFiles(backupFile);
    await reloaded;

    const after = bitSet(await fetchFullBitmap(request, pattern.id), probeIndex);
    expect(after).toBe(wasStitchedBefore); // revenu à l'état d'avant la sonde.
  });

  test("le bouton d'export pointe vers un vrai téléchargement JSON", async ({ page }) => {
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

  test("la sauvegarde automatique quotidienne se bascule depuis les Réglages", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Réglages", exact: true }).click();
    const toggle = page.getByRole("switch", { name: "Sauvegarde automatique quotidienne" });

    // Activée par défaut (`app/auto_backup.py::is_auto_backup_enabled`) tant
    // qu'aucune autre spec n'a déjà basculé ce réglage serveur global — donc
    // on part de l'état lu, pas d'un « true » supposé, et on revient
    // toujours à cet état de départ en fin de test.
    const initiallyChecked = (await toggle.getAttribute("aria-checked")) === "true";

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", String(!initiallyChecked));
    const afterToggle = await request.get("/api/backup/auto");
    expect(((await afterToggle.json()) as { enabled: boolean }).enabled).toBe(!initiallyChecked);

    await toggle.click(); // remis à l'état de départ pour ne pas affecter d'autres specs.
    await expect(toggle).toHaveAttribute("aria-checked", String(initiallyChecked));
  });

  test("effacer toutes les données vide l'instance (puis restauration de secours)", async ({
    page,
    request,
  }) => {
    const before = await fetchBackupDocument(request);

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
    expect(restoredPatterns).toHaveLength(1);
    expect(restoredPatterns[0]?.id).toBe(DEMO_PATTERN_ID);
  });
});
