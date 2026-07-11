import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = "docs/screenshots-review/library-estate";

const ESTATE_DATASETS = {
  datasets: [
    {
      dataset_id: "gdelt_asia_daily_country_panel",
      name: "Asia daily news-risk panel",
      description: "Country-day news intensity and market-risk research panel",
      grain: "country_day",
      analysis_readiness: "instant",
      local_root: "research_panels/gdelt",
      source: "GDELT GKG",
      join_keys: ["date", "country_iso3"],
      coverage: "2018–2024 · 13 Asian economies",
    },
    {
      dataset_id: "refinitiv_estimate_revision_panel",
      name: "Estimate revision panel",
      description: "Point-in-time analyst estimate revision history",
      grain: "ric_day",
      analysis_readiness: "instant",
      local_root: "research_panels/refinitiv",
      source: "Refinitiv",
      coverage: "2017–2026",
    },
    {
      dataset_id: "idn_fry_daily_cross_section",
      name: "Indonesia FRY daily cross section",
      description: "Daily issuer-level Indonesia equity research features",
      grain: "ticker_day",
      analysis_readiness: "instant",
      local_root: "research_panels/idn",
      source: "Indonesia equity pipeline",
      coverage: "2019–2026",
    },
    {
      dataset_id: "mops_financial_statements",
      name: "MOPS financial statements",
      description: "Collected Taiwan listed-company financial statements",
      grain: "issuer_quarter",
      analysis_readiness: "metadata_search",
      domain: "procured",
      local_path: "data_lake/procured/mops_financials.csv",
      source: "MOPS",
      coverage: "2015–2026",
    },
    {
      dataset_id: "refinitiv_entity_market_spine",
      name: "Entity market spine",
      description: "Canonical market identifiers and RIC mapping",
      grain: "ric_snapshot",
      analysis_readiness: "instant",
      local_path: "data_lake/entity_mapping/entity_market_spine.parquet",
      source: "Refinitiv",
    },
    {
      dataset_id: "usdt_bigquery_catalogue",
      name: "USDT BigQuery catalogue",
      description: "Query-time access to public blockchain tables",
      analysis_readiness: "dry_run_before_execution",
      backend: "bigquery_public_dataset",
      source: "Google BigQuery",
    },
    {
      dataset_id: "external_dataset_catalog",
      name: "External dataset catalogue",
      description: "Searchable metadata cards for known acquisition targets",
      analysis_readiness: "metadata_search",
      local_path: "data_lake/dataset_catalog/curated.jsonl",
      source: "Research Drive registry",
    },
    {
      dataset_id: "unclassified_registry_asset",
      name: "Unclassified registry asset",
      description: "Registered asset awaiting readiness classification",
      local_path: "data_lake/misc/unclassified.json",
      source: "Lab registry",
    },
  ],
};

async function setup(page, viewport) {
  await page.setViewportSize(viewport);
  await mockV2Api(page);
  await page.route("**/datasets", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ESTATE_DATASETS) }),
  );
  await page.route("**/datasets/*", (route) => {
    const id = decodeURIComponent(route.request().url().split("/datasets/")[1]?.split("?")[0] || "");
    const row = ESTATE_DATASETS.datasets.find((dataset) => dataset.dataset_id === id) || ESTATE_DATASETS.datasets[0];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row) });
  });
  await page.goto("/?tab=library", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await expect(page.getByTestId("library-estate-browser")).toBeVisible();
}

async function openCollection(page, name) {
  await page.getByRole("button", { name: "Lab", exact: true }).click();
  await page.locator('[data-testid="library-collection"]', { hasText: name }).click();
}

async function openNestedCollection(page, name) {
  const folder = page.locator('[data-testid="library-collection"]', { hasText: name });
  await expect(folder).toBeVisible();
  await folder.click();
}

async function selectAsset(page, title) {
  const row = page.locator('.rd-v2-library-asset[data-kind="dataset"]', { hasText: title });
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.locator("aside.rd-v2-rail")).toContainText(title);
}

test("render Library estate browser and inspector review states", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });

  await setup(page, { width: 1440, height: 900 });
  await page.screenshot({ path: `${OUT}/01-desktop-root.png`, fullPage: false });

  await page.locator('[data-testid="library-collection"]', { hasText: "Research panels" }).click();
  await expect(page.getByTestId("library-estate-browser")).toContainText("Research panels");
  await page.screenshot({ path: `${OUT}/02-desktop-research-panels.png`, fullPage: false });

  await openNestedCollection(page, "gdelt");
  await selectAsset(page, "Asia daily news-risk panel");
  await expect(page.locator("aside.rd-v2-rail")).toContainText("Can I use this?");
  await expect(page.locator("aside.rd-v2-rail")).toContainText("Query ready");
  await page.screenshot({ path: `${OUT}/03-desktop-selected-query-ready.png`, fullPage: false });

  await openCollection(page, "Acquired data");
  await selectAsset(page, "MOPS financial statements");
  await expect(page.locator("aside.rd-v2-rail")).toContainText("Metadata only");
  await expect(page.locator("aside.rd-v2-rail").getByRole("button", { name: "Preview rows" })).toHaveCount(0);
  await page.screenshot({ path: `${OUT}/04-desktop-selected-metadata-only.png`, fullPage: false });

  await openCollection(page, "Connected sources");
  await openNestedCollection(page, "BigQuery");
  await selectAsset(page, "USDT BigQuery catalogue");
  await expect(page.locator("aside.rd-v2-rail")).toContainText("Connected");
  await expect(page.locator("aside.rd-v2-rail")).not.toContainText("You can preview and query this dataset now.");
  await page.screenshot({ path: `${OUT}/05-desktop-selected-connected.png`, fullPage: false });

  await openCollection(page, "Other assets");
  await openNestedCollection(page, "misc");
  await selectAsset(page, "Unclassified registry asset");
  await expect(page.locator("aside.rd-v2-rail")).toContainText("Readiness unknown");
  await expect(page.locator("aside.rd-v2-rail").getByRole("button", { name: "Preview rows" })).toHaveCount(0);
  await page.screenshot({ path: `${OUT}/06-desktop-selected-unknown.png`, fullPage: false });

  await setup(page, { width: 390, height: 1200 });
  await page.screenshot({ path: `${OUT}/07-mobile-root.png`, fullPage: false });

  await page.locator('[data-testid="library-collection"]', { hasText: "Research panels" }).click();
  await openNestedCollection(page, "gdelt");
  await selectAsset(page, "Asia daily news-risk panel");
  await page.screenshot({ path: `${OUT}/08-mobile-selected-query-ready.png`, fullPage: false });
});
