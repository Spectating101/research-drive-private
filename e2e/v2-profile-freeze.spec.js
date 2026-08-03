/**
 * Research context / Workspace preferences freeze —
 * Understanding + Memory→Works→Lab in overlay; browser-local prefs; Detail stays contextual.
 */
import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "../docs/status/generated/profile-freeze-showcase.png");

const PROFILE = {
  found: true,
  profile: {
    name_en: "Kong, De-Rong",
    title: "Assistant Professor",
    discipline: "Finance",
    email: "drkong@saturn.yzu.edu.tw",
    paper_count_parsed: 18,
    specialties: ["empirical asset pricing", "investment", "FinTech", "corporate finance"],
    research_tracks: [
      { id: "token", title: "Token taxonomy — on-chain and off-chain data", phase: "active_grant", weight: 10 },
      { id: "momentum", title: "Taiwan equity momentum with machine learning", weight: 7 },
    ],
    method_tags: ["machine_learning", "panel_data"],
    publication_highlights: [
      "Kong, D.-R. (2021). Alternative investments in the FinTech era.",
      "Bui et al. (2023). Momentum in machine learning: Evidence from the Taiwan stock market.",
      "Kong (2022). NFT liquidity and market quality.",
    ],
    lab_fintech_stack: [
      { id: "coingecko", label: "CoinGecko prices", route: "vault" },
      { id: "stablecoin", label: "USDT on-chain flows", route: "bigquery" },
    ],
    procurement_recommendations: [
      { dataset: "TWSE daily prices", source_route: "vault", search_query: "TWSE daily prices" },
      { dataset: "MOPS financial statements", source_route: "mops", search_query: "MOPS financial statements" },
    ],
  },
};

test.describe("Research context freeze showcase", () => {
  test("bound Understanding Memory Works Lab in overlay; Detail not duplicated", async ({ page }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try { localStorage.setItem("procure_user_email", "drkong@saturn.yzu.edu.tw"); } catch {}
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const overlay = page.getByTestId("research-context-overlay");
    await expect(overlay.getByRole("heading", { name: "Research context" })).toBeVisible({ timeout: 20_000 });
    await expect(overlay.locator(".rd-v2-profile-name")).toContainText(/Kong/i);
    await expect(overlay.getByRole("button", { name: /Use my email|Bind example/i })).toHaveCount(0);

    const understanding = overlay.getByTestId("profile-understanding");
    const memory = overlay.getByTestId("profile-memory");
    const works = overlay.getByTestId("profile-works");
    const lab = overlay.getByTestId("profile-lab");
    await expect(understanding).toBeVisible();
    await expect(understanding.getByTestId("profile-understanding-synthesis")).toBeVisible();
    await expect(understanding.getByTestId("profile-understanding-threads")).toBeVisible();
    await expect(overlay.getByTestId("profile-memory-edit-focus")).toHaveCount(0);
    await expect(memory.getByTestId("profile-memory-statement")).toBeVisible();
    await expect(memory.getByTestId("profile-manage-context")).toBeVisible();
    await expect(works).toContainText(/indexed/i);
    await expect(works.locator(".rd-v2-profile-work-row")).toHaveCount(3);
    await expect(lab.getByRole("heading", { name: "Linked evidence" })).toBeVisible();
    expect(await lab.locator(".rd-v2-profile-lab-block").first().locator("li").count()).toBeLessThanOrEqual(3);
    expect(await lab.locator(".rd-v2-profile-lab-block").nth(1).locator("li").count()).toBeLessThanOrEqual(2);

    await expect(page.getByTestId("profile-detail-rail")).toHaveCount(0);
    await expect(page.getByTestId("settings-detail-rail")).toHaveCount(0);

    await works.locator(".rd-v2-profile-work-row").first().click();
    await expect(overlay.getByRole("button", { name: /Ask about this work/i })).toBeVisible();
    await page.screenshot({ path: OUT, fullPage: true });
  });

  test("unbound research context is quiet and not EXAMPLE primary", async ({ page }) => {
    await mockV2Api(page);
    await page.addInitScript(() => {
      try { localStorage.removeItem("procure_user_email"); } catch {}
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const overlay = page.getByTestId("research-context-overlay");
    await expect(overlay.getByTestId("profile-unbound-badge")).toBeVisible({ timeout: 20_000 });
    await expect(overlay.getByTestId("profile-primary-command")).toHaveText(/Connect faculty email/i);
    await expect(overlay.getByTestId("profile-understanding")).toHaveCount(0);
    await expect(overlay.getByRole("button", { name: /Bind example|Use EXAMPLE/i })).toHaveCount(0);
  });
});

test.describe("Workspace preferences Research context → Workspace → Advanced", () => {
  test("sections present; advanced collapsed; no health admin; Detail not Settings", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const prefs = page.getByTestId("workspace-prefs-overlay");
    await expect(prefs.getByRole("heading", { name: "Workspace preferences" })).toBeVisible({ timeout: 20_000 });
    await expect(prefs.getByTestId("settings-group-context")).toBeVisible();
    await expect(prefs.getByTestId("settings-group-workspace")).toBeVisible();
    await expect(prefs.getByTestId("settings-group-access")).toHaveCount(0);
    await expect(prefs.getByTestId("settings-open-health")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Detail|Focus Identity/i })).toHaveCount(0);
    const advanced = prefs.getByTestId("settings-group-advanced");
    await expect(advanced).not.toHaveAttribute("open", "");
    await advanced.locator("summary").click();
    await expect(prefs.getByTestId("settings-reset-local")).toBeVisible();
    await expect(page.getByTestId("settings-detail-rail")).toHaveCount(0);
  });
});
