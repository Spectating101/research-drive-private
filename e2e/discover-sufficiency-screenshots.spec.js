/** Discover lab-coverage visual authority: related, partial, and unknown never imply equivalence. */
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-sufficiency";
fs.mkdirSync(OUT, { recursive: true });

const LAB_READY = {
  dataset_id: "gdelt_asia_daily_country_panel",
  title: "Asia daily news-risk panel",
  source: "GDELT",
  analysis_readiness: "instant",
  local_root: "research_panels/gdelt",
  coverage: "2018–2024",
  grain: "country_day",
  description: "Lab panel ready for query",
};

function body(candidate) {
  return { sections: [{ title: "Mixed", rows: [LAB_READY, candidate] }], total: 2 };
}

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

async function selectCandidate(page, candidate) {
  await mockV2Api(page, { discoverBody: body(candidate) });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("coverage");
  await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: candidate.title }).click();
  const detail = page.locator("aside.rd-v2-rail").getByTestId("discover-eval-surface");
  await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
  return detail;
}

test.describe("Discover sufficiency screenshots", () => {
  test("coverage states stay explicit in the Detail rail", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    let detail = await selectCandidate(page, {
      title: "GDELT Asia country panel (catalog mirror)",
      source: "GDELT",
      url: "https://example.com/gdelt-asia",
      equivalent_dataset_id: "gdelt_asia_daily_country_panel",
      coverage: "2018–2024",
      grain: "country_day",
      collect_via: "http_fetch",
    });
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText("Exact local match");
    await expect(page.getByTestId("discover-eval-actions")).toContainText("Open local dataset");
    await shot(page, "01-desktop-exact-local");

    detail = await selectCandidate(page, {
      title: "GDELT Asia extended panel",
      source_system: "GDELT news graph",
      source: "GDELT",
      url: "https://example.com/gdelt-ext",
      coverage: "2015–2026",
      grain: "country_day",
      join_keys: ["date", "country_iso3"],
      collect_via: "http_fetch",
    });
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText("Partial local coverage");
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText(/2018|2024|2015|2026/);
    await shot(page, "02-desktop-partial-local");

    detail = await selectCandidate(page, {
      title: "GDELT event excerpts",
      source_system: "GDELT news graph",
      source: "GDELT",
      url: "https://example.com/gdelt-events",
      coverage: "2018–2024",
      grain: "country_day",
      join_keys: ["date", "country_iso3"],
      collect_via: "http_fetch",
    });
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText("Related lab asset");
    await shot(page, "03-desktop-related-local");

    detail = await selectCandidate(page, {
      title: "SEC EDGAR 10-K bulk",
      source: "SEC EDGAR",
      source_system: "SEC EDGAR",
      url: "https://www.sec.gov/edgar",
      grain: "filing",
      collect_via: "http_fetch",
    });
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText("No local alternative found");
    await shot(page, "04-desktop-no-local-alternative");

    detail = await selectCandidate(page, {
      title: "Untitled research dump",
      url: "https://example.com/dump",
      description: "Thin web hit with no comparable identity",
    });
    await expect(detail.getByTestId("discover-lab-coverage")).toContainText(/Comparison unavailable|Local comparison unavailable/i);
    await shot(page, "05-desktop-comparison-unknown");
  });
});
