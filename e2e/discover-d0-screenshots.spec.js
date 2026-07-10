/**
 * D0 identity evidence — no restyle; prove selection/rail/probe/queue integrity.
 * Run: CI=true YZU_PAGES=false TMPDIR=$PWD/.tmp-pw npx playwright test e2e/discover-d0-screenshots.spec.js
 */
import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  waitForShell,
} from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-d0";
fs.mkdirSync(OUT, { recursive: true });

async function shot(page, label) {
  const file = path.join(OUT, `${label}.png`);
  await page.screenshot({ path: file, fullPage: false });
}

const TWO_ROWS = {
  sections: [
    {
      title: "Registry",
      rows: [
        {
          dataset_id: "mops_financial_statements_ext",
          candidate_key: "dataset:mops_financial_statements_ext",
          title: "MOPS financial statements (Taiwan)",
          source: "MOPS",
          url: "https://mops.twse.com.tw/example",
        },
        {
          dataset_id: "twse_openapi_governance_ext",
          candidate_key: "dataset:twse_openapi_governance_ext",
          title: "TWSE OpenAPI governance disclosures",
          source: "TWSE",
          url: "https://openapi.twse.com.tw/example",
        },
      ],
    },
  ],
  total: 2,
};

const SIMILAR_TITLES = {
  sections: [
    {
      title: "Registry",
      rows: [
        {
          candidate_key: "url:https://mops.twse.com.tw/a",
          title: "MOPS financial statements",
          source: "MOPS",
          url: "https://mops.twse.com.tw/a",
        },
        {
          candidate_key: "url:https://mops.twse.com.tw/b",
          title: "MOPS financial statements extended",
          source: "MOPS",
          url: "https://mops.twse.com.tw/b",
        },
      ],
    },
  ],
  total: 2,
};

test("D0 desktop identity + exact queue + probe switch", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  await mockV2Api(page, {
    discoverBody: SIMILAR_TITLES,
    jobsBody: {
      jobs: [
        {
          id: "job-exact-a",
          status: "pending_approval",
          candidate_key: "url:https://mops.twse.com.tw/a",
          connector_id: null,
          registered_dataset_id: null,
          output_manifest_id: null,
          request: { candidate_key: "url:https://mops.twse.com.tw/a" },
          plan: { title: "MOPS financial statements" },
        },
      ],
    },
  });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("MOPS");
  await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(2);
  const rowA = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
    hasText: "MOPS financial statements",
  }).first();
  const rowB = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
    hasText: "MOPS financial statements extended",
  });
  await expect(rowA.locator(".rd-v2-pill", { hasText: "Queued" })).toHaveCount(1);
  await expect(rowB.locator(".rd-v2-pill", { hasText: "Queued" })).toHaveCount(0);
  await rowA.click();
  await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS financial statements");
  await shot(page, "desktop-1440x900__selected-row-rail-parity");
  await shot(page, "desktop-1440x900__similar-titles-exact-queue-only");

  await mockV2Api(page, { discoverBody: TWO_ROWS });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("governance");
  const mops = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
    hasText: "MOPS financial statements",
  });
  const twse = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
    hasText: "TWSE OpenAPI governance",
  });
  await mops.click();
  const rail = page.locator("aside.rd-v2-rail");
  await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
  await expect(rail.locator(".rd-v2-discover-probe-result")).toBeVisible();
  await shot(page, "desktop-1440x900__probe-candidate-a");
  await twse.click();
  await expect(rail).toContainText("TWSE OpenAPI");
  await expect(rail.locator(".rd-v2-discover-probe-result")).toHaveCount(0);
  await shot(page, "desktop-1440x900__probe-switch-b-no-stale-a");
});

test("D0 tablet selected row and rail parity", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 1200 });
  await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("mops");
  await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
  await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS financial statements");
  await shot(page, "tablet-900x1200__selected-row-rail-parity");
});

test("D0 mobile selected row + manual Detail sheet", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1200 });
  await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("mops");
  await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
  await shot(page, "mobile-390x1200__selected-row");
  const openDetail = page.getByRole("button", { name: /Detail|Open detail|View detail/i }).first();
  if (await openDetail.isVisible().catch(() => false)) {
    await openDetail.click();
  } else {
    // Fallback: mobile sheet toggle used in existing Discover tests
    const toggle = page.locator(".rd-v2-mobile-rail-toggle, [data-testid='open-detail']").first();
    if (await toggle.count()) await toggle.click();
  }
  const sheet = page.locator(".rd-v2-rail-sheet, aside.rd-v2-rail");
  await expect(sheet).toContainText("MOPS financial statements");
  await expect(sheet).not.toContainText("No candidate selected");
  await shot(page, "mobile-390x1200__manual-detail-selected-candidate");
});
