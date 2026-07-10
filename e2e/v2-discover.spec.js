import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

test.describe("v2 Discover tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page, { jobsBody: { jobs: [] } });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("default Discover is GDS-first with bottom suggested cards", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByTestId("discover-pending-banner")).toHaveCount(0);
    await expect(page.getByTestId("discover-suggested")).toBeVisible();
    await expect(page.getByTestId("discover-suggested")).toContainText("Suggested for your lab");
    await expect(page.getByTestId("discover-suggested-card").first()).toBeVisible();
    await expect(page.getByTestId("discover-suggested-card")).toHaveCount(4);
    await expect(page.getByTestId("discover-suggested").locator(".rd-v2-discover-candidate")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "TWSE governance" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Discover external datasets" })).toHaveCount(0);
  });

  test("suggestion chip fills Discover search and shows demo results", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE governance");
    await expect(page.getByTestId("header-ask-only")).toBeVisible();
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("TWSE OpenAPI");
    await expect(page.locator(".rd-v2-discover-search-summary")).toContainText("1 result");
    await expect(page.locator(".rd-v2-discover-search-summary")).toContainText(/Local suggestions|Demo catalog/);
    await expect(page.locator(".rd-v2-toolbar.inline")).toBeVisible();
    await expect(page.getByTestId("discover-result-filters")).toBeVisible();
  });

  test("selecting discover row opens acquisition rail with Add to lab", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("MOPS");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Source" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Access" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Probe" })).toBeVisible();
    await expect(page.getByTestId("discover-destination-select")).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Collection plan");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");
  });

  test("search auto-selects the top candidate in Detail without starting Ask", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.locator(".rd-v2-rail-selection")).toContainText("MOPS financial statements");
    await expect(rail.getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" })).toBeVisible();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(page.getByTestId("ask-messages")).not.toContainText("Find datasets for");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText("mops_financial_statements_ext");
    await expect(page.getByTestId("ask-messages")).toContainText("Assess this Discover candidate for procurement");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS financial statements");
  });

  test("Probe source shows connector summary in rail", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("button", { name: "Add to lab" })).toBeDisabled();
    await expect(rail).toContainText("Collection plan");
    await expect(rail).toContainText("Probe source first");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toContainText("direct_file");
    await expect(rail.locator(".rd-v2-discover-probe-result .rd-v2-detail-label", { hasText: "Connector" })).toBeVisible();
    await expect(rail).toContainText("Queues collection job");
    await expect(rail).toContainText("Required before worker runs");
    await expect(rail.getByRole("button", { name: "Add to lab" })).toBeEnabled();
  });

  test("destination picker updates collection plan vault path", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByTestId("discover-destination-select").selectOption("Lab root");
    await expect(rail).toContainText("Lab root");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.getByTestId("discover-destination-select")).toHaveValue("Lab root");
  });

  test("compare panel shows lab overlap without restating the result list", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              ...MOCK_DISCOVER_HIT.sections[0].rows,
              {
                dataset_id: "twse_governance_ext",
                title: "TWSE OpenAPI governance",
                source: "TWSE",
                collect_via: "twse",
                url: "https://openapi.twse.com.tw/example",
                coverage: "2020–2026",
                grain: "issuer-day",
                description: "Taiwan exchange governance feed",
              },
            ],
          },
        ],
        total: 2,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByTestId("discover-compare")).toBeVisible();
    await expect(rail.getByTestId("discover-compare")).toContainText("How this compares");
    await expect(rail.getByTestId("discover-compare")).not.toContainText("Alternatives in this search");
    await expect(rail.getByTestId("discover-compare-alt")).toHaveCount(0);
  });

  test("awaiting approval uses sticky approve in rail footer", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("header-pending-link").click();
    await expect(page).toHaveURL(/mode=(approvals|activity)/);
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await page.locator('.rd-v2-catalog button.row[data-state="awaiting"]').first().click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByTestId("discover-approve-sticky")).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card").getByRole("button", { name: "Approve collection" })).toHaveCount(0);
  });

  test("pending approvals open Discover Review queue, not Resources", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByRole("button", { name: /Review queue/ })).toBeVisible();
    await page.getByTestId("header-pending-link").click();
    await expect(page).toHaveURL(/mode=(approvals|activity)/);
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-activity")).toContainText("Review queue");
    await expect(page.getByTestId("discover-bulk-approve-safe")).toBeVisible();
    await page.getByRole("tab", { name: "Search" }).click();
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page).not.toHaveURL(/mode=(approvals|activity)/);
  });

  test("Discover Review queue shows acquisition jobs separate from Resources", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-activity-filters")).toBeVisible();
    await expect(page.getByTestId("discover-activity")).toContainText("Review queue");
    await expect(page.getByTestId("discover-activity")).not.toContainText(/GiB|Ask usage|REMOTE TABLES/i);
  });

  test("Add to lab after probe queues collection job on Detail rail", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.route("**/library/jobs*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          jobs: [
            {
              id: "job-pending-1",
              status: "pending_approval",
              type: "procure",
              plan: { title: "MOPS financial statements" },
            },
            {
              id: "job-discover-collect-1",
              status: "pending_approval",
              plan: { title: "MOPS financial statements" },
            },
          ],
        }),
      }),
    );
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toBeVisible();
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" }).click();
    const decision = rail.getByTestId("procurement-decision-card");
    await expect(decision).toBeVisible({ timeout: 15_000 });
    await expect(decision).toContainText("job-discover-collect-1");
    await expect(rail.getByTestId("discover-approve-sticky")).toBeVisible();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(page.getByTestId("ask-messages")).not.toContainText("to the lab vault");
  });

  test("new Discover query replaces stale selected candidate and resets filters", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("MOPS");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");

    await expect(page.getByTestId("discover-result-filters")).toBeVisible();
    await page.getByTestId("discover-result-filters").getByRole("button", { name: "External" }).click();

    await page.getByTestId("discover-search-input").fill("no-such-dataset-xyz");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("MOPS");
    await expect(page.getByTestId("discover-result-filters").getByRole("button", { name: "All" })).toHaveClass(/on/);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Example open dataset");
  });

  test("Preview ext opens external metadata modal", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("TWSE");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview source" }).click();
    const modal = page.locator(".rd-v2-preview-modal");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("Publisher");
    await expect(modal).toContainText("Row preview is available after Add to lab");
    await expect(modal.locator(".rd-v2-preview-foot").getByRole("button", { name: "Close" })).toBeVisible();
  });
  });

  test("index-only candidate does not claim probe or connector readiness", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                dataset_id: "datacite_index_only",
                title: "DataCite index-only record",
                source: "Collection Index",
                collect_via: "datacite",
                description: "Metadata record without a DOI or source URL.",
              },
            ],
          },
        ],
        total: 1,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("datacite index only");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator(".rd-v2-discover-candidate", { hasText: "DataCite index-only record" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Source link required");
    await expect(rail.getByRole("button", { name: "Probe source" })).toHaveCount(0);
    await expect(rail.getByRole("button", { name: "Add to lab" })).toBeDisabled();
    await expect(page.locator(".rd-v2-discover-candidate").first()).toContainText("External");
  });

  test.describe("v2 Discover API integration", () => {
  test("live discover API rows render in list", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("discover-search-input").fill("mops");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.locator(".rd-v2-discover-search-summary")).toContainText(/Discover API|1 result/);
    await expect(page.locator(".rd-v2-chip", { hasText: "Offline sample" })).toHaveCount(0);
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("MOPS financial statements");
  });
});
