/**
 * D1 taxonomy evidence — honest result kinds + simplified row anatomy.
 * Run: CI=true YZU_PAGES=false TMPDIR=$PWD/.tmp-pw npx playwright test e2e/discover-d1-screenshots.spec.js
 */
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-d1";
fs.mkdirSync(OUT, { recursive: true });

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

const MIXED = {
  sections: [
    {
      title: "Mixed taxonomy",
      rows: [
        {
          dataset_id: "gdelt_asia_daily_country_panel",
          title: "Asia daily news-risk panel",
          source: "GDELT",
          analysis_readiness: "instant",
          local_root: "research_panels/gdelt",
          coverage: "2018–2026 · Asia countries",
          description: "Country-day news-risk panel already in the lab vault",
        },
        {
          dataset_id: "registry_card_only",
          title: "Registry metadata card",
          source: "Lab registry",
          in_lab: true,
          coverage: "Coverage not described",
          description: "Registered metadata without a connected query path",
        },
        {
          title: "MOPS financial statements (Taiwan)",
          source: "MOPS",
          url: "https://mops.twse.com.tw/example",
          coverage: "2015–2026 · Taiwan listed issuers",
          description: "Listed-company filings · open government source",
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

const PROBEABLE = {
  sections: [
    {
      title: "Probe",
      rows: [
        {
          title: "Bare public CSV index",
          source: "Web",
          url: "https://example.com/index.csv",
          coverage: "Coverage not described",
          description: "Public index with no collection route yet",
        },
      ],
    },
  ],
  total: 1,
};

test.describe("Discover D1 screenshots", () => {
  test("desktop mixed + probed + licensed", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockV2Api(page, { discoverBody: MIXED });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("taxonomy");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await expect(page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate")).toHaveCount(4);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-query-ready"]')).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"]')).toHaveCount(1);
    await shot(page, "desktop-1440x900-mixed-taxonomy");

    await page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"]').click();
    await shot(page, "desktop-1440x900-licensed-manual");

    await mockV2Api(page, { discoverBody: PROBEABLE });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("csv");
    await page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate").first().click();
    await page.getByTestId("discover-eval-actions").getByRole("button", { name: "Probe source" }).click();
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-probed"]')).toHaveCount(1);
    await shot(page, "desktop-1440x900-external-probed");
  });

  test("tablet mixed taxonomy", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 1200 });
    await mockV2Api(page, { discoverBody: MIXED });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("taxonomy");
    await expect(page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate")).toHaveCount(4);
    await shot(page, "tablet-900x1200-mixed-taxonomy");
  });

  test("mobile mixed scanning only", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await mockV2Api(page, { discoverBody: MIXED });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("taxonomy");
    await expect(page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate")).toHaveCount(4);
    await shot(page, "mobile-390x1200-mixed-scanning");
  });
});
