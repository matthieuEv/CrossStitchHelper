import { expect, test } from "@playwright/test";

/**
 * Vérifie le critère "terminé quand" du Lot 2 (docs/roadmap.md) : n'importe
 * quelle image peut être transformée en motif suivable, entièrement à la
 * main — dépôt, cadrage, dimensions, palette, peinture par zone,
 * enregistrement. Contre une vraie instance, comme lot1-persistence.spec.ts.
 *
 * Une image PNG minimale suffit (pas besoin d'un vrai PDF) : le Lot 2 ne
 * fait aucune analyse du contenu du fichier, seulement de son rendu raster.
 */

// PNG 1x1 valide le plus court possible, encodé en dur : la génération d'un
// PDF minimal dans un test serait plus de code que la charge utile qu'il
// remplace, alors qu'un PNG tient dans une chaîne base64 courte.
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

test("importer une image à la main crée un motif suivable", async ({ page }) => {
  await page.goto("/");
  // Le bouton "Importer" de la barre de navigation est toujours présent,
  // contrairement au bouton "+ Importer un motif" de la bibliothèque,
  // réservé à la disposition étroite (frontend/src/screens/LibraryScreen.tsx).
  await page.getByRole("button", { name: "Importer", exact: true }).click();

  await page
    .locator('input[type="file"][accept*="pdf"]')
    .setInputFiles({
      name: "grille-test.png",
      mimeType: "image/png",
      buffer: Buffer.from(TINY_PNG_BASE64, "base64"),
    });

  // Étape Cadrage : l'aperçu raster réel doit se charger, puis les dimensions.
  await expect(page.getByText("Colonnes")).toBeVisible();
  const [columnsInput, rowsInput] = await page.locator("input.input").all();
  await columnsInput!.fill("6");
  await rowsInput!.fill("5");
  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Palette : une couleur, puis peinture d'une zone.
  await page.getByRole("button", { name: /Ajouter une couleur/ }).click();
  const canvas = page.locator("canvas.track-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (box === null) throw new Error("Le canvas de peinture n'a pas de boîte englobante");

  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + 80, box.y + 60, { steps: 4 });
  await page.mouse.up();

  await expect(page.getByText(/\d+ \/ 30 cases peintes/)).toBeVisible();
  const filledText = await page.getByText(/\d+ \/ 30 cases peintes/).textContent();
  const filled = Number(filledText?.match(/(\d+) \/ 30/)?.[1]);
  expect(filled).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Continuer", exact: true }).click();

  // Étape Récap : nom, puis validation.
  const nameInput = page.getByLabel("Nom du motif");
  await nameInput.fill(`e2e import ${Date.now()}`);
  await expect(page.getByText(`${filled}`, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter et commencer" }).click();

  // Doit atterrir sur l'écran de suivi du motif fraîchement créé, avec
  // exactement les cases peintes comme cases restantes (rien de coché).
  await expect(page.locator("canvas.track-canvas")).toBeVisible();
  await expect(page.getByText(`${filled} restants`)).toBeVisible();
});
