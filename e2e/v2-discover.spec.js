import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

test.describe("v2 Discover tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("empty state shows suggestions before search", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Discover external datasets" })).toBeVisible();
    await expect(page.getByRole("button", { name: "TWSE governance" })).toBeVisible();
  });

  test("suggestion chip fills header search and shows demo results", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator(".rd-v2-search-pill input")).toHaveValue("TWSE governance");
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("TWSE OpenAPI");
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Search");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Ready to check" })).toBeVisible();
  });

  test("selecting discover row opens acquisition rail with Add to lab", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Source" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Access" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Probe" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Destination" })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Acquisition state");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Registry");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Probe");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
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
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toContainText("direct_file");
    await expect(rail.locator(".rd-v2-detail-label", { hasText: "Connector" })).toBeVisible();
  });

  test("Add to lab after probe queues structured Ask", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toBeVisible();
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("ask-messages")).toContainText("Add to lab vault");
    await expect(page.getByTestId("ask-messages")).toContainText("example_com_data");
  });

  test("new Discover query clears stale selected candidate and resets filters", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Queued" }).click();
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Queued" })).toHaveClass(/on/);

    await page.locator(".rd-v2-search-pill input").fill("no-such-dataset-xyz");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "All" })).toHaveClass(/on/);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("No candidate selected");
  });

  test("Preview ext opens external metadata modal", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("TWSE");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview source" }).click();
    const modal = page.locator(".rd-v2-preview-modal");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("Publisher");
    await expect(modal).toContainText("Row preview is available after Add to lab");
    await expect(modal.locator(".rd-v2-preview-foot").getByRole("button", { name: "Close" })).toBeVisible();
  });
});

test.describe("v2 Discover API integration", () => {
  test("live discover API rows render in list", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await v2Nav(page, "Discover");
    await expect(page.locator(".rd-v2-chip", { hasText: "Discover API" })).toBeVisible();
    await expect(page.locator(".rd-v2-chip", { hasText: "Offline sample" })).toHaveCount(0);
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("MOPS financial statements");
  });
});
