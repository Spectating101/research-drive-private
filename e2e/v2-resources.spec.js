import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import { MOCK_RESOURCES_ROLLUP } from "./fixtures/mockResourcesRollup.js";

test.describe("v2 Resources tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Overview shows key resources", async ({ page }) => {
    await expect(page.locator("main").getByRole("heading", { name: "Resources", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Overview", exact: true })).toBeVisible();
    const main = page.locator("main");
    const inventory = main.getByRole("region", { name: "Key resources" });
    await expect(main.getByRole("region", { name: "Databank inventory" })).toContainText("128 registry");
    await expect(inventory).toContainText("Key resources");
    await expect(inventory).toContainText("Storage");
    await expect(inventory).toContainText("Accounts & limits");
    await expect(inventory).toContainText("Source routes");
    await expect(inventory).not.toContainText("Connectors & sources");
    await expect(inventory).not.toContainText("Work capacity");
    await expect(inventory.locator('[data-kind="usage"]', { hasText: "Drive vault" })).toBeVisible();
    await expect(inventory.locator(".rd-v2-res-inventory-head")).toContainText("source routes");
    const sourceRoutes = inventory.locator(".rd-v2-res-inventory-section", { hasText: "Source routes" });
    await expect(sourceRoutes.locator('[data-kind="source"]', { hasText: "Source routes" })).toBeVisible();
    await expect(sourceRoutes.locator('[data-kind="source"]')).toHaveCount(1);
    await expect(sourceRoutes).toContainText("3 routes configured");
    await expect(sourceRoutes).not.toContainText("GDELT");
    await expect(inventory.locator('[data-kind="metered"]', { hasText: "BigQuery" })).toBeVisible();
    await expect(main.locator(".rd-v2-toolbar-stat")).toContainText("2/12 busy");
    await expect(main.getByText("Current status")).toHaveCount(0);
    await expect(main.getByText("Ask / model turns")).toHaveCount(0);
    await expect(main.getByText("Metered APIs")).toHaveCount(0);
    await expect(main.getByText("Activity ledger")).toHaveCount(0);
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
  });

  test("inventory row opens the matching rail resource", async ({ page }) => {
    const inventory = page.getByRole("region", { name: "Key resources" });
    await inventory.locator('[data-kind="source"]', { hasText: "Source routes" }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Source routes");
    await expect(rail).toContainText("Finance, catalogs, and intake");
    await expect(rail).toContainText("3 routes configured");
    await expect(rail).toContainText("Connector details stay in Activity");
  });

  test("selected inventory resource can be sent to Ask from the rail", async ({ page }) => {
    const inventory = page.getByRole("region", { name: "Key resources" });
    await inventory.locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(page.getByTestId("ask-messages")).toContainText("Explain this metered Resources provider");
  });

  test("right rail starts with Resources guide", async ({ page }) => {
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Resources");
    await expect(rail).toContainText("Select a key resource");
    await expect(rail).toContainText("Main list");
    await expect(rail).not.toContainText("Needs action");
  });

  test("Activity tab shows event log", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await expect(main.locator('[aria-label="Usage report"]')).toContainText("Remote tables");
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("heading", { name: "Run log" })).toBeVisible();
    await expect(main.getByText("USB bulk cache")).toHaveCount(0);
    await expect(main.getByText("get Taiwan gov panel")).toBeVisible();
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("Remote tables 2.4 GiB")).toBeVisible();
  });

  test("Activity filters log categories", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await main.getByRole("button", { name: "Discovery", exact: true }).click();
    await expect(main.getByRole("button", { name: "Discovery", exact: true })).toHaveClass(/on/);
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("get Taiwan gov panel")).toHaveCount(0);
    await main.getByRole("button", { name: "Review", exact: true }).click();
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("heading", { name: "Run log" })).toHaveCount(0);
  });

  test("selecting meter row shows rail drill-down", async ({ page }) => {
    await page.getByRole("region", { name: "Key resources" }).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    await expect(
      page.locator("aside").getByRole("button", { name: "View activity →" }),
    ).toBeVisible();
  });

  test("View activity switches to Activity tab filtered", async ({ page }) => {
    await page.getByRole("region", { name: "Key resources" }).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    await page.locator("aside").getByRole("button", { name: "View activity →" }).click();
    await expect(page.getByRole("button", { name: /Remote table events/ })).toBeVisible();
    await expect(page.getByText("get Taiwan gov panel")).toBeVisible();
  });

  test("Ask about account limit carries Resources context into rail", async ({ page }) => {
    await page.getByRole("region", { name: "Key resources" }).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(rail).toContainText("Explain this metered Resources provider");
  });

  test("approval review row lives in Activity", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("button", { name: /awaiting approval/ })).toBeVisible();
    await expect(main.getByRole("button", { name: /Approval needed/ })).toBeVisible();
  });

  test("activity Jobs filter shows live procurement job status", async ({ page }) => {
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await page.getByRole("button", { name: "Jobs", exact: true }).click();
    const main = page.locator("main");
    await expect(main.locator(".rd-v2-res-activity-row.job", { hasText: "MOPS financial statements" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(main.locator(".rd-v2-res-activity-row.job")).toContainText("Awaiting approval");
  });

  test("procurement job row opens Discover approval rail", async ({ page }) => {
    const inventory = page.getByRole("region", { name: "Key resources" });
    await expect(inventory.getByText("Procurement jobs")).toBeVisible({ timeout: 15_000 });
    await inventory.locator('[data-kind="active"]', { hasText: "MOPS financial statements" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("job-pending-1");
    await rail.getByRole("button", { name: "Review in Discover →" }).click();
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Discover" })).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
    await expect(rail.getByRole("button", { name: "Approve collection" })).toBeVisible();
  });

  test("refresh chip refetches resources rollup", async ({ page }) => {
    let rollupCalls = 0;
    await page.route("**/library/desk/resources*", (route) => {
      rollupCalls += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", hero: {}, spending: {}, activity: { events: [] } }),
      });
    });
    await page.getByRole("button", { name: "Refresh" }).click();
    await page.waitForTimeout(500);
    expect(rollupCalls).toBeGreaterThan(0);
  });
});

test("v2 Resources loading state does not flash account summary", async ({ page }) => {
  let releaseResources;
  const resourcesGate = new Promise((resolve) => {
    releaseResources = resolve;
  });
  await mockV2Api(page);
  await page.route("**/library/desk/resources*", async (route) => {
    await resourcesGate;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_RESOURCES_ROLLUP),
    });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });

  const main = page.locator("main");
  await expect(main).toContainText(/Refreshing inventory|Loading resources/);
  await expect(main.getByText("Current status")).toHaveCount(0);
  await expect(main.getByText("Account summary")).toHaveCount(0);

  releaseResources();
  await waitForShell(page);
  await expect(main.getByRole("region", { name: "Key resources" })).toBeVisible();
});
