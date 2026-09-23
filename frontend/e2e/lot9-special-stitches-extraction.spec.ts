import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 9 (docs/roadmap.md) : la
 * détection automatique type A extrait aussi les points spéciaux (1/2, 1/4,
 * point arrière, nœud) — contre une vraie instance, avec le vrai fichier de
 * référence, jusqu'au bout du parcours d'import réel (pas seulement les
 * tests unitaires de `backend/tests/test_type_a.py`, qui vérifient la
 * justesse de l'extraction elle-même mais pas le parcours utilisateur).
 *
 * Valeurs de vérité terrain : page 11 « Usage Summary » de la fixture,
 * reprises telles quelles (voir `backend/tests/test_type_a.py::
 * _expected_usage_by_code` pour le nouveau re-parsing indépendant à la
 * source de ces mêmes chiffres).
 */

const FIXTURE_PATH = fileURLToPath(
  new URL(
    "../../fixtures/cafe-brasserie-charting-export/CaffeBrasseriecoloursymbols.pdf",
    import.meta.url,
  ),
);

/** Voir le commentaire équivalent dans `lot4-automatic-detection.spec.ts`. */
const DETECTION_TIMEOUT = 90_000;

interface PatternSummary {
  id: string;
  name: string;
}

interface PatternPaletteEntry {
  code: string;
  count_half: number;
  count_quarter: number;
  count_french: number;
  backstitch_length_cm: number | null;
}

interface PatternDetail {
  palette: PatternPaletteEntry[];
}

async function fetchPatternByName(
  request: APIRequestContext,
  name: string,
): Promise<PatternDetail> {
  const list = await request.get("/api/patterns");
  const patterns = (await list.json()) as PatternSummary[];
  const found = patterns.find((pattern) => pattern.name === name);
  if (found === undefined) throw new Error(`Motif "${name}" introuvable en base`);
  const detail = await request.get(`/api/patterns/${found.id}`);
  return (await detail.json()) as PatternDetail;
}

test("l'import type A pré-remplit le compte de toile et les points spéciaux se retrouvent dans le motif créé", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.locator('input[type="file"][accept*="pdf"]').setInputFiles(FIXTURE_PATH);

  await expect(page.getByText(/Détection automatique : type A/)).toBeVisible({
    timeout: DETECTION_TIMEOUT,
  });
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  await expect(page.getByPlaceholder("Code").first()).toBeVisible();
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Récap : le compte de toile (Aida 16, lu dans le texte du PDF) est
  // déjà rempli — jamais imposé, une saisie manuelle l'emporterait toujours
  // (voir `manualFabricEditRef` dans `ImportScreen.tsx`), mais ici on
  // vérifie justement qu'on n'a rien tapé.
  const fabricInput = page.getByLabel("Toile (fils au pouce)");
  await expect(fabricInput).toHaveValue("16");

  const patternName = `e2e points spéciaux ${Date.now()}`;
  await page.getByLabel("Nom du motif").fill(patternName);
  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  await expect(page.locator("canvas.track-canvas")).toBeVisible();

  const detail = await fetchPatternByName(request, patternName);
  const palette = Object.fromEntries(detail.palette.map((entry) => [entry.code, entry]));

  // DMC 3031 : les 4 points 1/4 signalés page 11 (voir Key Technical
  // Concepts — glyphes non centrés, distincts du point entier 3031).
  expect(palette["3031"]?.count_quarter).toBe(4);

  // DMC 742 : les 3 nœuds, tous sur la page 1 de la fixture.
  expect(palette["742"]?.count_french).toBe(3);

  // DMC 310 : longueur de point arrière convertie en cm à partir du compte
  // de toile qu'on vient de valider (16) — jamais `null` puisque le champ
  // était rempli à la validation.
  expect(palette["310"]?.backstitch_length_cm).not.toBeNull();
  expect(palette["310"]!.backstitch_length_cm!).toBeGreaterThan(100);
});
