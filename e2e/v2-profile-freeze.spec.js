/**
 * Profile / Settings freeze — Memory→Works→Lab, Identity→Access→Defaults→Advanced,
 * Detail rails never Loading / EXAMPLE CTA.
 * Run: TMPDIR=$PWD/.tmp-pw npx playwright test e2e/v2-profile-freeze.spec.js --retries=0
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

test.describe("Profile freeze showcase", () => {
  test("bound Memory Works Lab and Detail rail match freeze", async ({ page }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try {
        localStorage.setItem("procure_user_email", "drkong@saturn.yzu.edu.tw");
      } catch {
        /* ignore */
      }
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".rd-v2-profile-name")).toContainText(/Kong/i);
    await expect(page.getByRole("button", { name: /Use my email|Bind example/i })).toHaveCount(0);
    await expect(page.getByText(/^EXAMPLE$/)).toHaveCount(0);

    const memory = page.getByTestId("profile-memory");
    const works = page.getByTestId("profile-works");
    const lab = page.getByTestId("profile-lab");
    await expect(memory).toBeVisible();
    await expect(memory.getByTestId("profile-memory-focus")).toBeVisible();
    await expect(memory.locator(".rd-v2-profile-memory-input")).toHaveCount(0);
    await memory.getByTestId("profile-memory-edit-focus").click();
    await expect(memory.locator(".rd-v2-profile-memory-input")).toHaveCount(1);
    await memory.getByTestId("profile-memory-cancel-focus").click();
    await expect(memory.locator(".rd-v2-profile-memory-input")).toHaveCount(0);
    await expect(works).toBeVisible();
    await expect(works).toContainText(/indexed/i);
    const workBtn = works.locator(".rd-v2-profile-work-row").first();
    await expect(workBtn).toBeVisible();
    await expect(lab).toBeVisible();
    await expect(lab.getByText(/Linked evidence/i)).toBeVisible();
    await expect(lab.getByText(/Evidence gaps/i)).toBeVisible();

    const memoryBox = await memory.boundingBox();
    const worksBox = await works.boundingBox();
    const labBox = await lab.boundingBox();
    expect(memoryBox.y).toBeLessThan(worksBox.y);
    expect(worksBox.y).toBeLessThan(labBox.y);

    const detail = page.getByTestId("profile-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail.getByText(/^Loading/)).toHaveCount(0);
    await expect(detail.getByText(/Judgement/i)).toBeVisible();

    await workBtn.click();
    await expect(detail).toContainText(/Selected work|Publication|Alternative|Momentum/i);
    await expect(detail.getByText(/^Loading/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Ask about this work/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Show research context/i })).toHaveCount(0);

    await expect(page.getByTestId("profile-know")).toHaveCount(0);
    await expect(page.getByTestId("profile-offer")).toHaveCount(0);
    await expect(page.locator(".rd-v2-profile-identity-metrics")).toHaveCount(0);

    await page.screenshot({ path: OUT, fullPage: true });
  });

  test("unbound profile is quiet and not EXAMPLE primary", async ({ page }) => {
    await mockV2Api(page);
    await page.addInitScript(() => {
      try {
        localStorage.removeItem("procure_user_email");
      } catch {
        /* ignore */
      }
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("profile-unbound-badge")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("profile-primary-command")).toHaveText(/Open Settings/i);
    await expect(page.getByTestId("profile-unbound-zero")).toBeVisible();
    await expect(page.getByTestId("profile-memory")).toHaveCount(0);
    await expect(page.getByTestId("profile-works")).toHaveCount(0);
    await expect(page.getByTestId("profile-lab")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Bind example|Use EXAMPLE/i })).toHaveCount(0);
    await expect(page.getByText(/^EXAMPLE$/)).toHaveCount(0);
    await expect(page.getByText(/Kong|drkong@saturn/i)).toHaveCount(0);
    await expect(page.getByTestId("profile-detail-rail")).not.toContainText(/^Loading/);
  });
});

test.describe("Settings Identity → Access → Defaults → Advanced", () => {
  test("sections present; advanced collapsed; Detail never Loading", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("settings-group-identity")).toBeVisible();
    await expect(page.getByTestId("settings-group-access")).toBeVisible();
    await expect(page.getByTestId("settings-group-defaults")).toBeVisible();
    await expect(page.locator(".rd-v2-settings-summary")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Use EXAMPLE/i })).toHaveCount(0);

    const advanced = page.getByTestId("settings-group-advanced");
    await expect(advanced).toBeVisible();
    await expect(advanced).not.toHaveAttribute("open", "");
    await advanced.locator("summary").click();
    await expect(advanced).toHaveAttribute("open", "");
    await expect(page.getByLabel(/Fallback access token/i)).toBeVisible();

    const detail = page.getByTestId("settings-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail.getByText(/^Loading/)).toHaveCount(0);
    await expect(detail.getByText(/Judgement/i)).toBeVisible();
  });
});
