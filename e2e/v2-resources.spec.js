import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import { MOCK_RESOURCES_ROLLUP } from "./fixtures/mockResourcesRollup.js";

function capacityInventory(page) {
  return page.getByRole("region", { name: "Sources overview" });
}

function capacityGrid(page) {
  return page.getByTestId("resources-capacity-grid");
}

function sourceLedger(page) {
  return page.getByTestId("resources-source-ledger");
}

test.describe("v2 Resources tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Sources shows capacity, value, and progressive source routes", async ({ page }) => {
    await expect(page.locator("main").getByRole("heading", { name: "Resources", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sources", exact: true })).toBeVisible();
    const main = page.locator("main");
    const inventory = capacityInventory(page);
    await expect(inventory).toContainText("Capacity & access");
    await expect(inventory).toContainText("Storage");
    await expect(inventory).toContainText("Services");
    await expect(inventory).toContainText("Desk");
    await expect(inventory).not.toContainText("Work capacity");
    await expect(capacityGrid(page).getByRole("button", { name: /GDrive vault/ })).toBeVisible();
    await expect(capacityGrid(page).getByRole("button", { name: /BigQuery/ })).toBeVisible();
    await expect(sourceLedger(page)).toContainText("Licensed / institutional");
    await expect(sourceLedger(page)).toContainText("Public market & filings");
    await expect(sourceLedger(page)).toContainText("Research & open data");
    // VC-4: one collector vocabulary and denominator across toolbar, card, and rail.
    await expect(main).toContainText("12 registered · 3 connected · 2 running");
    await expect(main).not.toContainText("joined");
    await expect(main).not.toContainText("collectors available");
    await expect(main.getByText("Current status")).toHaveCount(0);
    await expect(main.getByText("Ask / model turns")).toHaveCount(0);
    await expect(main.getByText("Metered APIs")).toHaveCount(0);
    await expect(main.getByText("Activity ledger")).toHaveCount(0);
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
  });

  test("inventory row opens the matching rail resource", async ({ page }) => {
    await sourceLedger(page).getByRole("button", { name: /DataCite/ }).first().click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toContainText("DataCite");
    await expect(rail).toContainText("DataCite");
    await expect(rail).toContainText(/metadata|dataset|DOI|harvest/i);
  });

  test("selected inventory resource can be sent to Ask from the rail", async ({ page }) => {
    await capacityGrid(page).getByRole("button", { name: /BigQuery/ }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(page.getByTestId("ask-messages")).toContainText(/Explain this Resources .*BigQuery/);
  });

  test("right rail starts with lab capacity context", async ({ page }) => {
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Resources");
    await expect(rail).toContainText("Lab capacity");
    await expect(rail).toContainText("Current capacity");
    await expect(rail).toContainText(/awaiting your approval|capacity warning|source routes/i);
    await expect(rail.getByRole("button", { name: "Open activity" })).toBeVisible();
    await expect(rail).not.toContainText("Select a key resource");
  });

  test("Usage tab shows event log", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    await expect(main.locator('[aria-label="Usage report"]')).toContainText("Remote tables");
    await expect(main).toContainText("Approvals stay on Discover History");
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
    await expect(main.getByRole("heading", { name: "Run log" })).toBeVisible();
    await expect(main.getByText("USB bulk cache")).toHaveCount(0);
    await expect(main.getByText("get Taiwan gov panel")).toBeVisible();
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("Remote tables 2.4 GiB")).toBeVisible();
  });

  test("Usage filters log categories", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    const discoveryFilter = main.getByRole("button", { name: "Filter usage: Discovery" });
    await discoveryFilter.click();
    await expect(discoveryFilter).toHaveClass(/on/);
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("get Taiwan gov panel")).toHaveCount(0);
    await main.getByRole("button", { name: "Filter usage: Review" }).click();
    await expect(main.getByText("No usage rows in this period.")).toBeVisible();
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
    await expect(main.getByRole("heading", { name: "Run log" })).toHaveCount(0);
  });

  test("selecting meter row shows rail drill-down", async ({ page }) => {
    await capacityGrid(page).getByRole("button", { name: /BigQuery/ }).click();
    const rail = page.locator("aside");
    await expect(rail.getByRole("region", { name: "Decision summary" })).toBeVisible();
    await expect(rail.getByRole("button", { name: "Ask about this →" })).toBeVisible();
  });

  test("Open activity switches the Resources overview to Usage", async ({ page }) => {
    await page.locator("aside").getByRole("button", { name: "Open activity" }).click();
    await expect(page.getByRole("button", { name: "Usage", exact: true })).toHaveClass(/on/);
    await expect(page.getByRole("heading", { name: "Run log" })).toBeVisible();
    await expect(page.getByText("get Taiwan gov panel")).toBeVisible();
  });

  test("Ask about account limit carries Resources context into rail", async ({ page }) => {
    await capacityGrid(page).getByRole("button", { name: /BigQuery/ }).click();
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(rail).toContainText(/Explain this Resources .*BigQuery/);
  });

  test("approval review stays in Discover rather than the usage ledger", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    await expect(main).toContainText("Approvals stay on Discover History");
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);
    await expect(main.getByRole("button", { name: /awaiting approval/ })).toHaveCount(0);
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
  await expect(main.getByRole("status")).toContainText("Syncing");
  await expect(main.getByText("Current status")).toHaveCount(0);
  await expect(main.getByText("Account summary")).toHaveCount(0);

  releaseResources();
  await waitForShell(page);
  await expect(main.getByRole("region", { name: "Sources overview" })).toBeVisible();
});
