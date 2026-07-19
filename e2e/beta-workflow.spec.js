/**
 * Live beta workflow — requires desk API on :8765 and UI on :5178.
 * Run: bash drive/scripts/run_yzu_cluster.sh && npm run test:beta-workflow
 */
import { test, expect } from "@playwright/test";

const API = process.env.YZU_API_URL || "http://127.0.0.1:8765";
const FACULTY_EMAIL = process.env.DESK_TEST_EMAIL || "drkong@saturn.yzu.edu.tw";

let apiLive = false;
let datasetCount = 0;

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ request }) => {
  try {
    const health = await request.get(`${API}/health?live=1`, { timeout: 45_000 });
    if (!health.ok()) return;
    const body = await health.json();
    apiLive = body.status === "ok";
    datasetCount = Number(body.datasets || 0);
    if (!datasetCount) {
      const ds = await request.get(`${API}/datasets`, { timeout: 30_000 });
      if (ds.ok()) {
        const payload = await ds.json();
        datasetCount = (payload.datasets || []).length;
      }
    }
  } catch {
    apiLive = false;
  }
});

test.beforeEach(async ({ page }) => {
  test.skip(!apiLive, `Desk API not live at ${API} — start with bash drive/scripts/run_yzu_cluster.sh`);
  await page.addInitScript((email) => {
    localStorage.setItem("procure_user_email", email);
    localStorage.setItem("rd_v2_settings", JSON.stringify({ defaultTab: "home", onSelect: "detail", email }));
  }, FACULTY_EMAIL);
  await page.setViewportSize({ width: 1440, height: 900 });
});

async function v2Nav(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

test.describe("beta workflow @ live-desk", () => {
  test("1 — header shows live registry, not demo seed", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.locator(".rd-v2-trust-badge", { hasText: "Demo catalog" })).toHaveCount(0);
    await expect(page.locator(".rd-v2-header-meta-count", { hasText: /\d+ datasets/ })).toBeVisible();
    const countText = await page.locator(".rd-v2-header-meta-count").innerText();
    const n = parseInt(countText, 10);
    expect(n).toBeGreaterThan(10);
  });

  test("2 — library lists registry datasets", async ({ page }) => {
    await page.goto("/?tab=library&folder=research_panels/gdelt", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    const rows = page.locator('.rd-v2-library-asset[data-kind="dataset"]');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    expect(await rows.count()).toBeGreaterThan(0);
  });

  test("3 — profile loads faculty from registry", async ({ page }) => {
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(page.locator(".rd-v2-profile-name")).not.toHaveText("Research profile", { timeout: 15_000 });
    await expect(page.locator(".rd-v2-profile-hint", { hasText: FACULTY_EMAIL })).toBeVisible();
  });

  test("4 — discover search and evidence evaluation", async ({ page }) => {
    await page.goto("/?tab=browse&q=TWSE", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Discover" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Discover result summary" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("region", { name: "Sources beyond your lab" })).toBeVisible();
  });

  test("5 — resources desk connection", async ({ page }) => {
    await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Resources" })).toBeVisible();
    await expect(page.locator(".rd-v2-res-status-strip").first()).toBeVisible({ timeout: 20_000 });
  });

  test("6 — dataset detail and preview", async ({ page }) => {
    await page.goto("/?tab=library&folder=research_panels/gdelt", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    const row = page.locator('.rd-v2-library-asset[data-kind="dataset"]').first();
    await row.waitFor({ state: "visible", timeout: 30_000 });
    await row.click();
    await expect(page.locator(".rd-v2-rail-toggle button.on", { hasText: "Detail" })).toBeVisible();
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview rows" }).click();
    await expect(page.getByRole("dialog", { name: /preview/i })).toBeVisible({ timeout: 20_000 });
    await page.keyboard.press("Escape");
  });

  test("7 — settings reflects live desk", async ({ page }) => {
    await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Settings" })).toBeVisible();
    const emailInput = page.locator('.rd-v2-input[type="email"]');
    await expect(emailInput).toHaveValue(FACULTY_EMAIL);
  });
});
