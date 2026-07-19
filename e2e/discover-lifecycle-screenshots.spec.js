/** Discover lifecycle visual authority: history states project into Detail without replacing Explore. */
import { test, expect } from "@playwright/test";
import { MOCK_DISCOVER_HIT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-lifecycle";
fs.mkdirSync(OUT, { recursive: true });
// This fixture's source identity is explicit and must bind exactly; no title matching.
const KEY = "dataset:mops_financial_statements_ext";

function job(status, extra = {}) {
  return {
    id: `job-${status}`,
    status,
    candidate_key: KEY,
    connector_id: "example_com_data",
    registered_dataset_id: extra.registered_dataset_id ?? null,
    output_manifest_id: extra.output_manifest_id ?? null,
    error: extra.error || "",
    updated_at: "2026-07-10T14:32:00Z",
    result: extra.result || {},
    plan: { title: "MOPS financial statements (Taiwan)" },
    request: { candidate_key: KEY, connector_id: "example_com_data" },
  };
}

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

async function openMops(page, jobs) {
  await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT, jobsBody: { jobs } });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("mops");
  await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
  return page.locator("aside.rd-v2-rail").getByTestId("discover-eval-surface");
}

test.describe("Discover lifecycle screenshots", () => {
  test("lifecycle truth remains attached to the selected result", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    let surface = await openMops(page, [job("pending_approval")]);
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("Approval required");
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await shot(page, "01-desktop-approval-required");

    surface = await openMops(page, [job("running", { result: { stage: "Downloading files" } })]);
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("Running");
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("Downloading files");
    await shot(page, "02-desktop-running");

    surface = await openMops(page, [job("failed", { error: "HTTP 403 from source" })]);
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("Failed");
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("HTTP 403");
    await shot(page, "03-desktop-failed");

    surface = await openMops(page, [job("completed", {
      registered_dataset_id: "mops_financial_statements_2026",
      result: { query_ready: true, analysis_readiness: "instant" },
    })]);
    await expect(surface.getByTestId("discover-lifecycle")).toContainText("Query ready");
    await expect(surface.locator('[aria-label="Can I use this"]')).toContainText("In lab · Query ready");
    await expect(page.getByTestId("discover-eval-actions").getByRole("button", { name: "Open in Library" })).toBeVisible();
    await shot(page, "04-desktop-query-ready");

    await page.setViewportSize({ width: 390, height: 1200 });
    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("button", { name: /Show Detail/ }).click();
    await expect(rail.getByTestId("discover-lifecycle")).toContainText("Query ready");
    await shot(page, "05-mobile-query-ready-detail");
  });
});
