/**
 * Discover Evaluation Surface screenshots (E3).
 * Run: CI=true YZU_PAGES=false TMPDIR=$PWD/.tmp-pw npx playwright test e2e/discover-evaluation-screenshots.spec.js
 */
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-evaluation";
fs.mkdirSync(OUT, { recursive: true });

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

const MIXED = {
  sections: [
    {
      title: "Evaluation surface",
      rows: [
        {
          dataset_id: "gdelt_asia_daily_country_panel",
          title: "Asia daily news-risk panel",
          source: "GDELT",
          analysis_readiness: "instant",
          local_root: "research_panels/gdelt",
          coverage: "2018–2026 · Asia countries",
          description: "Country-day news-risk panel already in the lab vault",
          grain: "country-day",
        },
        {
          title: "Bare public CSV index",
          source: "Web",
          url: "https://example.com/index.csv",
          coverage: "Coverage not described",
          description: "Public index with no collection route yet",
        },
        {
          dataset_id: "mops_financial_statements_ext",
          candidate_key: "dataset:mops_financial_statements_ext",
          title: "MOPS financial statements (Taiwan)",
          source: "MOPS",
          collect_via: "mops_tw",
          url: "https://mops.twse.com.tw/example",
          coverage: "2015–2026",
          geographic_coverage: "Taiwan listed issuers",
          grain: "issuer-quarter",
          description: "Listed-company financial statements",
        },
        {
          title: "Refinitiv Asia equity fundamentals",
          source: "Refinitiv",
          manual_access: true,
          access_mode: "licensed",
          license: "Proprietary — commercial license",
          coverage: "2000–2026 · Asia equities",
          description: "Vendor fundamentals requiring entitlement",
        },
      ],
    },
  ],
  total: 4,
};

test.describe("Discover evaluation screenshots", () => {
  test("desktop + tablet + mobile evaluation states", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MIXED });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("evaluation");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await expect(page.locator(".rd-v2-discover-candidate")).toHaveCount(4);

    // 1. external before probe
    await page.locator(".rd-v2-discover-candidate", { hasText: "Bare public CSV index" }).click();
    await expect(page.getByTestId("discover-eval-surface")).toContainText("Available to inspect");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText("Probe source");
    await shot(page, "01-desktop-external-before-probe");

    // 2. after successful probe
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
    await shot(page, "02-desktop-external-after-probe");

    // 3. acquisition-available
    await page.locator(".rd-v2-discover-candidate", { hasText: "MOPS financial statements" }).click();
    await expect(page.getByTestId("discover-eval-surface")).toContainText("Acquisition available");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText("Add to lab");
    await shot(page, "03-desktop-acquisition-available");

    // 4. licensed/manual
    await page.locator(".rd-v2-discover-candidate", { hasText: "Refinitiv Asia equity" }).click();
    await expect(page.getByTestId("discover-eval-surface")).toContainText("Licensed / manual access");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText(
      "Review access requirements",
    );
    await shot(page, "04-desktop-licensed-manual");

    // 5. local query-ready
    await page.locator(".rd-v2-discover-candidate", { hasText: "Asia daily news-risk panel" }).click();
    await expect(page.getByTestId("discover-eval-surface")).toContainText("Query ready");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText("Open in Library");
    await shot(page, "05-desktop-local-query-ready");

    // 6. tablet after probe
    await page.setViewportSize({ width: 900, height: 1200 });
    await page.locator(".rd-v2-discover-candidate", { hasText: "Bare public CSV index" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
    await shot(page, "06-tablet-external-after-probe");

    // 7–9 mobile
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.locator(".rd-v2-discover-candidate", { hasText: "Bare public CSV index" }).click();
    await shot(page, "07-mobile-selected-row");
    // open detail if collapsed
    const grip = page.locator(".rd-v2-rail-mobile-grip");
    if (await grip.isVisible()) {
      await grip.click();
    }
    await expect(page.getByTestId("discover-eval-surface")).toBeVisible();
    await shot(page, "08-mobile-detail-after-probe");
    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).click();
    await expect(page.locator(".rd-v2-ask-ctx")).toContainText("Bare public CSV");
    await shot(page, "09-mobile-detail-ask-context");
  });
});
