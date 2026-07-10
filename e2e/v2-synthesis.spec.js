import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const MOCK_SYNTHESIS = {
  profiles: [
    {
      id: "stablecoin_trust_engagement",
      title: "Stablecoin trust ↔ engagement",
      type: "trust_engagement",
      description: "Skynet + GDELT + DeFiLlama entity panels.",
      sources: ["Skynet", "GDELT", "DeFiLlama"],
      join_keys: ["entity_id", "date"],
      research_questions: ["Which entities lack on-chain coverage?"],
    },
    {
      id: "skynet_etherscan_stablecoin",
      title: "Skynet + Etherscan",
      type: "skynet_etherscan",
      description: "Join security scores with token scrapes.",
    },
  ],
  latest: {
    stablecoin_trust_engagement: {
      generated_at: "2026-07-08T12:00:00Z",
      summary: { entity_count: 42 },
    },
  },
  count: 2,
};

const MOCK_SYNTHESIS_DETAIL = {
  found: true,
  profile_id: "stablecoin_trust_engagement",
  generated_at: "2026-07-08T12:00:00Z",
  gap_count: 3,
  summary: { entity_count: 42 },
  preview_rows: [{ entity_id: "usdt", trust_score: 0.91, engagement: 0.77 }],
  manifest: {
    gaps: [
      { entity_id: "fdusd", missing_source: "etherscan", reason: "no scrape" },
      { entity_id: "tusd", missing_source: "gdelt", reason: "thin news" },
    ],
  },
};

test.describe("v2 Synthesis tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page, {
      synthesisProfiles: MOCK_SYNTHESIS,
      synthesisDetail: MOCK_SYNTHESIS_DETAIL,
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("sidebar opens synthesis showcase", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Synthesis", exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "How synthesis works" })).toBeVisible();
    await expect(
      page.locator(".rd-v2-home-synthesis").getByRole("heading", { name: "Stablecoin trust ↔ engagement" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Refresh panel|Build panel/ })).toBeVisible();
  });

  test("profile list and gaps render", async ({ page }) => {
    await expect(page.getByRole("region", { name: "How synthesis works" })).toContainText("Inputs");
    await expect(page.getByRole("region", { name: "Built research panels" })).toContainText("Already built");
    await expect(page.getByRole("region", { name: "Built research panels" })).toContainText("Stablecoin trust ↔ engagement");
    await expect(page.locator(".rd-v2-synthesis-list .rd-v2-synthesis-card")).toHaveCount(1);
    await expect(page.locator(".rd-v2-synthesis-list")).toContainText("Skynet + Etherscan");
    await expect(page.getByText("fdusd")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sample rows" })).toBeVisible();
  });

  test("ask about gaps switches to Ask rail", async ({ page }) => {
    await page.getByRole("button", { name: "Ask about gaps →" }).click();
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("ask-messages")).toContainText("stablecoin_trust_engagement");
  });

  test("synthesis explains the complete input-to-output chain", async ({ page }) => {
    const flow = page.getByTestId("synthesis-flow");
    await expect(flow).toContainText("Inputs");
    await expect(flow).toContainText("Join / transform");
    await expect(flow).toContainText("Coverage check");
    await expect(flow).toContainText("Registered output");
    await expect(flow).toContainText("Skynet");
    await expect(flow).toContainText("GDELT");
    await expect(flow).toContainText("DeFiLlama");
    await expect(flow).toContainText("entity_id");
    await expect(flow).toContainText("42 entities");
    await expect(flow).toContainText("3 gaps");
    expect(await flow.evaluate((element) => element.clientHeight)).toBeGreaterThan(100);

    await page.setViewportSize({ width: 1024, height: 768 });
    expect(await flow.evaluate((element) => element.clientHeight)).toBeGreaterThan(150);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Synthesis workspace");
  });
});
