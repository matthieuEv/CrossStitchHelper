import { expect, request as playwrightRequest, test, type APIRequestContext } from "@playwright/test";

/**
 * Issue #78, second stage (Lot 11b): two real instances linked. The instance
 * under test (`baseURL`) hosts a shared library; a second instance joins it
 * with an invitation code, shows its shared patterns, copies one, and asks
 * for its removal — the host's admin grants it, and the outcome comes back.
 *
 * Needs a second instance next to the first, the way `.github/workflows/ci.yml`
 * starts one:
 * - `E2E_PEER_URL`: where the browser reaches the second instance;
 * - `E2E_HOST_INTERNAL_URL`: where the second instance's *server* reaches
 *   the first one (both containers on one Docker network).
 * Skipped without them.
 */

const PEER_URL = process.env.E2E_PEER_URL;
const HOST_INTERNAL_URL = process.env.E2E_HOST_INTERNAL_URL;

/** Test-only credentials of the second instance's first admin. */
const PEER_ADMIN = {
  email: "e2e-peer@example.test",
  first_name: "Pia",
  last_name: "Peer",
  password: "e2e-peer-password",
};
const CLIENT_HEADERS = { "X-CSH-Client": "e2e" };
/** `backend/app/seed.py` — stable id, never regenerated. */
const DEMO_PATTERN_ID = "demo-perf-255x180";

async function peerAdmin(): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL: PEER_URL!, extraHTTPHeaders: CLIENT_HEADERS });
  const status = (await (await api.get("/api/auth/status")).json()) as { setup_required: boolean };
  if (status.setup_required) {
    expect((await api.post("/api/auth/setup", { data: PEER_ADMIN })).ok()).toBe(true);
  } else {
    const profiles = (await (await api.get("/api/auth/profiles")).json()) as Array<{ id: string; first_name: string }>;
    const me = profiles.find((profile) => profile.first_name === PEER_ADMIN.first_name);
    if (me === undefined) throw new Error("The second instance was set up without the e2e peer admin");
    expect((await api.post("/api/auth/login", { data: { user_id: me.id, password: PEER_ADMIN.password } })).ok()).toBe(true);
  }
  return api;
}

test.skip(PEER_URL === undefined || HOST_INTERNAL_URL === undefined, "No second instance (E2E_PEER_URL)");
test.use({ viewport: { width: 375, height: 812 } });

test("a second instance joins, mirrors, copies, and its removal request is decided by the host", async ({
  page,
  request,
  browser,
}) => {
  const runId = Date.now() % 100000;
  const sharedName = `e2e entre sites ${runId}`;

  // --- The host: a shared pattern, a name, an invitation.
  await request.put("/api/federation/instance", { data: { name: "e2e Site A" } });
  const duplicated = (await (
    await request.post(`/api/patterns/${DEMO_PATTERN_ID}/duplicate`, { data: { name: sharedName } })
  ).json()) as { id: string };
  expect((await request.post(`/api/patterns/${duplicated.id}/share`, { data: {} })).ok()).toBe(true);
  const invitation = (await (
    await request.post("/api/federation/invitations", {
      data: { public_url: HOST_INTERNAL_URL, trust_admins: false },
    })
  ).json()) as { code: string };

  const peerApi = await peerAdmin();
  await peerApi.put("/api/federation/instance", { data: { name: "e2e Site B" } });
  const peerContext = await browser.newContext({
    baseURL: PEER_URL!,
    locale: "fr-FR",
    viewport: { width: 375, height: 812 },
    storageState: await peerApi.storageState(),
  });
  const peer = await peerContext.newPage();

  try {
    // --- The second instance joins from its Settings.
    await peer.goto("/settings");
    const links = peer.getByRole("region", { name: "Sites reliés" });
    await links.getByLabel("Code d'invitation reçu").fill(invitation.code);
    await links.getByRole("button", { name: "Rejoindre", exact: true }).click();
    await expect(links.getByText(/Site relié/)).toBeVisible();
    await expect(links.getByText("e2e Site A")).toBeVisible();
    await expect(links.getByText("Nous affichons sa bibliothèque partagée")).toBeVisible();

    // --- Its Shared tab shows the host's pattern; untrusted, it only asks.
    await peer.goto("/");
    await peer.getByRole("tab", { name: "Partagés" }).click();
    const card = peer.getByRole("button", { name: new RegExp(sharedName) });
    await expect(card).toBeVisible();
    await expect(card.getByText("De e2e Site A")).toBeVisible();
    await card.click();
    const sheet = peer.getByRole("dialog", { name: `Actions pour « ${sharedName} »` });
    await expect(sheet.getByRole("button", { name: "Supprimer" })).toHaveCount(0);
    await sheet.getByRole("button", { name: "Copier dans ma bibliothèque" }).click();
    await expect(peer.locator(".card-title", { hasText: sharedName })).toBeVisible();

    await peer.getByRole("tab", { name: "Partagés" }).click();
    await card.click();
    await sheet.getByRole("button", { name: "Demander la suppression" }).click();
    await sheet.getByRole("button", { name: "Envoyer la demande" }).click();
    const requests = peer.getByRole("heading", { name: "Mes demandes" }).locator("..");
    await expect(requests.getByText("En attente")).toBeVisible();

    // --- The host's admin decides.
    await page.goto("/");
    await page.getByRole("tab", { name: /Partagés/ }).click();
    const queued = page.locator(".panel", { hasText: `demande la suppression de « ${sharedName} »` });
    await expect(queued.getByText(/Pia Peer · e2e Site B/)).toBeVisible();
    await queued.getByRole("button", { name: "Supprimer le motif" }).click();
    await expect(queued).toHaveCount(0);

    // --- The outcome comes back with the next pull (opening the tab).
    await expect(async () => {
      await peer.getByRole("tab", { name: "Mes motifs" }).click();
      await peer.getByRole("tab", { name: "Partagés" }).click();
      await expect(requests.getByText("Acceptée")).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 30_000 });
    await expect(card).toHaveCount(0);
    // The copy stays in the second instance's library.
    await peer.getByRole("tab", { name: "Mes motifs" }).click();
    await expect(peer.locator(".card-title", { hasText: sharedName })).toBeVisible();
  } finally {
    // Leave both instances as found: the second one leaves the link, its
    // copy goes, the host's pattern of this run goes.
    const overview = (await (await peerApi.get("/api/federation")).json()) as { peers: Array<{ id: string }> };
    for (const link of overview.peers) await peerApi.delete(`/api/federation/peers/${link.id}`);
    const own = (await (await peerApi.get("/api/patterns")).json()) as Array<{ id: string; name: string }>;
    for (const pattern of own.filter((p) => p.name === sharedName)) await peerApi.delete(`/api/patterns/${pattern.id}`);
    await request.delete(`/api/patterns/${duplicated.id}`);
    const library = (await (await request.get("/api/shared")).json()) as { patterns: Array<{ id: string; name: string }> };
    for (const pattern of library.patterns.filter((p) => p.name === sharedName)) {
      await request.delete(`/api/shared/patterns/${pattern.id}`);
    }
    await peerContext.close();
    await peerApi.dispose();
  }
});
