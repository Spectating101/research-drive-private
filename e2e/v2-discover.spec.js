import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

/**
 * Discover feature E2E.
 * Authority: docs/UI_PRODUCT_AUTHORITY.md (Explore | History).
 * Classify results via docs/DISCOVER_E2E_AUTHORITY_AUDIT.md before product fixes.
 * Pending approvals live on Explore via discover-queue-strip; History is the trail mode.
 */

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
    await expect(page.locator(".rd-v2-discover-list-panel .rd-v2-discover-candidate").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("TWSE");
    await expect(page.locator(".rd-v2-discover-search-summary")).toContainText(/\d+ result/);
    await expect(page.getByTestId("discover-toolbar")).toBeVisible();
    await expect(page.getByTestId("discover-filter-trigger")).toBeVisible();
  });

  test("selecting discover row opens acquisition rail with Add to lab", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("MOPS");
    await page.getByTestId("discover-search-input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" })).toBeVisible();
    await expect(page.getByTestId("rail-judgment")).toBeVisible();
    await expect(page.getByTestId("rail-confirmed")).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Source" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Access" })).toBeVisible();
    await expect(page.getByTestId("discover-destination-select")).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Collection plan");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");
  });

  test("Discover empty Detail is a one-line source prompt", async ({ page }) => {
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByTestId("rail-empty")).toContainText("Select a source to inspect.");
    await expect(rail.getByTestId("rail-empty")).not.toContainText("Search Discover, then select");
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

  // Sticky Detail approve is current; header pending opens Explore queue (not Activity).
  // docs/DISCOVER_E2E_AUTHORITY_AUDIT.md §7
  test("awaiting approval uses sticky approve in rail footer", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("header-pending-link").click();
    await expect(page).not.toHaveURL(/mode=(approvals|activity|history)/);
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    const queue = page.getByTestId("discover-queue-strip");
    await expect(queue).toBeVisible();
    await expect(queue).toContainText("Needs your review");
    await page.getByTestId("discover-queue-row").first().click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByTestId("discover-approve-sticky")).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card").getByRole("button", { name: "Approve collection" })).toHaveCount(0);
  });

  // Not-Resources is current; Explore queue strip replaces Activity panel.
  test("pending approvals open Discover Review queue, not Resources", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByRole("button", { name: /Review queue/ })).toBeVisible();
    await page.getByTestId("header-pending-link").click();
    await expect(page).toHaveURL(/tab=browse/);
    await expect(page).not.toHaveURL(/mode=(approvals|activity|history)/);
    await expect(page).not.toHaveURL(/tab=resources/);
    const queue = page.getByTestId("discover-queue-strip");
    await expect(queue).toBeVisible();
    await expect(queue).toContainText("Needs your review");
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "History" })).toBeVisible();
    await page.getByRole("tab", { name: "History" }).click();
    await expect(page).toHaveURL(/mode=history/);
    await expect(page.getByTestId("discover-history")).toBeVisible();
    await page.getByRole("tab", { name: "Explore" }).click();
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page).not.toHaveURL(/mode=(approvals|activity|history)/);
  });

  // Legacy mode=activity normalizes to Explore; acquisition queue lives in Discover, not Resources.
  test("Discover Review queue shows acquisition jobs separate from Resources", async ({ page }) => {
    await mockV2Api(page);
    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("discover-queue-strip")).toBeVisible();
    await expect(page.getByTestId("discover-queue-strip")).toContainText("Needs your review");
    await expect(page.getByTestId("discover-queue-strip")).not.toContainText(/GiB|Ask usage|REMOTE TABLES/i);
    await expect(page.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
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

    await expect(page.getByTestId("discover-filter-trigger")).toBeVisible();
    await page.getByTestId("discover-filter-trigger").click();
    await page.getByTestId("discover-filter-panel").getByRole("button", { name: "External", exact: true }).click();
    await expect(page.getByTestId("discover-filter-count")).toHaveText("1");

    await page.getByTestId("discover-search-input").fill("no-such-dataset-xyz");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("MOPS");
    await expect(page.getByTestId("discover-filter-count")).toHaveCount(0);
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
    await expect(modal).toContainText("Bounded sample unavailable; Detail explains the next valid action.");
    await expect(modal.locator(".rd-v2-preview-foot").getByRole("button", { name: "Close" })).toBeVisible();
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

  test("Explore polish: Catalog→Research keeps search/filter boxes; In lab filters suggested", async ({
    page,
  }) => {
    const search = page.getByTestId("discover-search-input");
    const filter = page.getByTestId("discover-filter-trigger");
    await expect(page.getByTestId("discover-suggested")).toBeVisible();
    await expect(page.getByTestId("discover-suggested-card")).toHaveCount(4);

    const snapBox = (box) => ({
      x: Math.round(box.x),
      y: Math.round(box.y),
      width: Math.round(box.width),
      height: Math.round(box.height),
    });
    const beforeSearch = snapBox(await search.boundingBox());
    const beforeFilter = snapBox(await filter.boundingBox());

    await page.getByTestId("discover-intent-research").click();
    await expect(search).toHaveAttribute("data-intent", "research");
    expect(snapBox(await search.boundingBox())).toEqual(beforeSearch);
    expect(snapBox(await filter.boundingBox())).toEqual(beforeFilter);

    await filter.click();
    const panel = page.getByTestId("discover-filter-panel");
    await expect(panel).toBeVisible();
    await panel.getByRole("button", { name: "In lab", exact: true }).click();
    await expect(page.getByTestId("discover-filter-chip")).toContainText("In lab");
    await expect(page.getByTestId("discover-filter-count")).toHaveText("1");
    await expect(page.getByTestId("discover-suggested-card")).toHaveCount(1);
    await expect(page.getByTestId("discover-suggested-card")).toContainText("In lab");
  });

  test("toolbar stays spatially stable across Catalog and Research question", async ({ page }) => {
    const toolbar = page.getByTestId("discover-toolbar");
    const search = page.getByTestId("discover-search-input");
    const filter = page.getByTestId("discover-filter-trigger");
    const action = page.getByTestId("discover-search-action");
    await expect(toolbar).toBeVisible();
    await expect(filter).toBeVisible();
    await expect(action).toHaveText("Search catalog");

    const before = await toolbar.evaluate((el) => {
      const searchEl = el.querySelector('[data-testid="discover-search-input"]');
      const filterEl = el.querySelector('[data-testid="discover-filter-trigger"]');
      const actionEl = el.querySelector('[data-testid="discover-search-action"]');
      const intent = el.querySelector('[data-testid="discover-intent-catalog"]');
      const box = el.getBoundingClientRect();
      return {
        height: Math.round(box.height),
        searchTop: Math.round(searchEl.getBoundingClientRect().top),
        filterTop: Math.round(filterEl.getBoundingClientRect().top),
        actionTop: Math.round(actionEl.getBoundingClientRect().top),
        intentTop: Math.round(intent.getBoundingClientRect().top),
      };
    });

    await page.getByTestId("discover-intent-research").click();
    await expect(search).toHaveAttribute("data-intent", "research");
    await expect(action).toHaveText("Search by meaning");
    const after = await toolbar.evaluate((el) => {
      const searchEl = el.querySelector('[data-testid="discover-search-input"]');
      const filterEl = el.querySelector('[data-testid="discover-filter-trigger"]');
      const actionEl = el.querySelector('[data-testid="discover-search-action"]');
      const intent = el.querySelector('[data-testid="discover-intent-research"]');
      const box = el.getBoundingClientRect();
      return {
        height: Math.round(box.height),
        searchTop: Math.round(searchEl.getBoundingClientRect().top),
        filterTop: Math.round(filterEl.getBoundingClientRect().top),
        actionTop: Math.round(actionEl.getBoundingClientRect().top),
        intentTop: Math.round(intent.getBoundingClientRect().top),
      };
    });
    expect(after.height).toBe(before.height);
    expect(after.searchTop).toBe(before.searchTop);
    expect(after.filterTop).toBe(before.filterTop);
    expect(after.actionTop).toBe(before.actionTop);
    expect(after.intentTop).toBe(before.intentTop);

    await page.getByTestId("discover-intent-catalog").click();
    await expect(search).toHaveAttribute("data-intent", "catalog");
    await expect(action).toHaveText("Search catalog");
  });

  test("filter popover applies and clears active access filter", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("TWSE");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.locator(".rd-v2-discover-candidate").first()).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("discover-filter-trigger").click();
    const panel = page.getByTestId("discover-filter-panel");
    await expect(panel).toBeVisible();
    await panel.getByRole("button", { name: "In lab", exact: true }).click();
    await expect(page.getByTestId("discover-filter-count")).toHaveText("1");
    await expect(page.getByTestId("discover-filter-chip")).toContainText("In lab");

    await page.getByTestId("discover-filter-chip").click();
    await expect(page.getByTestId("discover-filter-count")).toHaveCount(0);
    await expect(page.getByTestId("discover-filter-panel")).toBeVisible();
  });

  test("compact working-from context leaves results as the vertical focus", async ({ page }) => {
    await page.goto("/?tab=browse&dataset=gdelt_asia_daily_country_panel", {
      waitUntil: "domcontentloaded",
    });
    await waitForShell(page);
    const context = page.getByTestId("discover-research-context");
    await expect(context).toBeVisible();
    await expect(context).toContainText("Working from");
    await expect(context.locator(".rd-v2-research-evidence")).toHaveCount(0);
    await expect(page.getByTestId("discover-suggested")).toBeVisible();
    const heights = await page.evaluate(() => {
      const ctx = document.querySelector('[data-testid="discover-research-context"]');
      const list = document.querySelector('[data-testid="discover-suggested"]');
      return {
        context: ctx?.getBoundingClientRect().height || 0,
        list: list?.getBoundingClientRect().height || 0,
      };
    });
    expect(heights.list).toBeGreaterThan(heights.context);
  });
});
