import { expect, test } from "@playwright/test";

/**
 * Issue #92: Settings > "Sites reliés" says in plain words what linking two
 * sites is for, with examples and what never leaves the site — behind an
 * "À quoi ça sert ?" opened on demand, so the section stays short otherwise.
 */

test.use({ viewport: { width: 375, height: 812 } });

test("the linked sites section explains what it is for, on demand", async ({ page }) => {
  await page.goto("/settings");
  const section = page.getByRole("region", { name: "Sites reliés" });
  await expect(section).toBeVisible();
  await expect(section.getByText(/Vous n'avez qu'une seule installation/)).toBeVisible();

  const help = section.locator("details", { hasText: "À quoi ça sert ?" });
  await expect(help.getByText(/club de broderie/)).toHaveCount(0);
  await help.getByText("À quoi ça sert ?").click();
  await expect(help.getByText(/club de broderie/)).toBeVisible();
  await expect(help.getByText(/ne quitte jamais votre site/)).toBeVisible();
  await expect(help.getByText(/Inviter un site/)).toBeVisible();
});
