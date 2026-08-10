import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import { MOCK_RESOURCES_ROLLUP } from "./fixtures/mockResourcesRollup.js";

function capacityInventory(page) {
  return page.getByRole("region", { name: "Capacity and access" });
}

async function openSourceRoutes(page) {
  await capacityInventory(page).locator(".rd-v2-res-routes > summary").click();
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
    await expect(inventory).toContainText("Accounts & limits");
    await expect(inventory).toContainText("Declared source routes");
    await expect(inventory).not.toContainText("Work capacity");
    await expect(inventory.locator('[data-kind="usage"]', { hasText: "Drive vault" })).toBeVisible();
    await expect(inventory.locator('[data-kind="source"]')).toHaveCount(5);
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Market & filings" })).not.toBeVisible();
    await openSourceRoutes(page);
    await expect(inventory.locator('[data-kind="source"]', { hasText: "GDELT" })).toHaveCount(0);
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Market & filings" })).toBeVisible();
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Catalog APIs" })).toBeVisible();
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Discovery & intake" })).toBeVisible();
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Open web" })).toBeVisible();
    await expect(inventory.locator('[data-kind="source"]', { hasText: "Remote tables" })).toBeVisible();
    await expect(inventory.locator('[data-kind="metered"]', { hasText: "BigQuery" })).toBeVisible();
    await expect(main.locator(".rd-v2-toolbar-stat")).toContainText("2/12 busy");
    await expect(main.getByText("Current status")).toHaveCount(0);
    await expect(main.getByText("Ask / model turns")).toHaveCount(0);
    await expect(main.getByText("Metered APIs")).toHaveCount(0);
    await expect(main.getByText("Activity ledger")).toHaveCount(0);
    await expect(main.getByRole("heading", { name: "Review queue" })).toHaveCount(0);

    const ledger = page.getByTestId("resources-source-ledger");
    await expect(ledger).toContainText("DataCite");
    await expect(ledger).toContainText("Live API route");
    await expect(ledger).toContainText("ROUTE DEFINED");
    await expect(ledger).toContainText("BigQuery");
    await expect(ledger).toContainText("Credentials required");
    await expect(ledger).toContainText("UNAVAILABLE");
    await expect(ledger).toContainText("WRDS");
    await expect(ledger).toContainText("Licensed access unavailable");
  });

  test("inventory row opens the matching rail resource", async ({ page }) => {
    const inventory = capacityInventory(page);
    await openSourceRoutes(page);
    await inventory.locator('[data-kind="source"]', { hasText: "Catalog APIs" }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Catalog APIs");
    await expect(rail).toContainText("DataCite");
    await expect(rail).toContainText("Academic metadata and dataset APIs");
    await expect(rail).toContainText("DOI lookup and dataset import");
  });

  test("reported source access carries through to the Detail rail", async ({ page }) => {
    const ledger = page.getByTestId("resources-source-ledger");
    await ledger.getByRole("button", { name: /BigQuery/ }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("BigQuery");
    await expect(rail).toContainText("Credentials required");
    await expect(rail).toContainText("Unavailable");
    await expect(rail).toContainText("Not available on this desk");
    await expect(rail).not.toContainText("Available for discovery/procurement");
  });

  test("selected inventory resource can be sent to Ask from the rail", async ({ page }) => {
    const inventory = capacityInventory(page);
    await inventory.locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();

    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(page.getByTestId("ask-messages")).toContainText("Explain this metered Resources provider");
  });

  test("right rail starts with lab capacity context", async ({ page }) => {
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Resources");
    await expect(rail).toContainText("Lab capacity");
    await expect(rail).toContainText("Current capacity");
    await expect(rail).toContainText(/items? need attention|Desk ready|collection.*running/i);
    await expect(rail).toContainText("Access states are reported for 3 desk routes.");
    await expect(rail).not.toContainText("source routes are reachable");
    await expect(rail.getByRole("button", { name: "Open activity" })).toBeVisible();
    await expect(rail).not.toContainText("Select a key resource");
  });

  test("Usage tab shows event log", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    await expect(main.locator('[aria-label="Usage report"]')).toContainText("Remote tables");
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("heading", { name: "Run log" })).toBeVisible();
    await expect(main.getByText("USB bulk cache")).toHaveCount(0);
    await expect(main.getByText("get Taiwan gov panel")).toBeVisible();
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("Remote tables 2.4 GiB")).toBeVisible();
  });

  test("Usage filters log categories", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    await main.getByRole("button", { name: "Discovery", exact: true }).click();
    await expect(main.getByRole("button", { name: "Discovery", exact: true })).toHaveClass(/on/);
    await expect(main.getByText("taiwan equity")).toBeVisible();
    await expect(main.getByText("get Taiwan gov panel")).toHaveCount(0);
    await main.getByRole("button", { name: "Review", exact: true }).click();
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("heading", { name: "Run log" })).toHaveCount(0);
  });

  test("selecting meter row shows rail drill-down", async ({ page }) => {
    await capacityInventory(page).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    await expect(
      page.locator("aside").getByRole("button", { name: "View activity →" }),
    ).toBeVisible();
  });

  test("View activity switches to Usage tab filtered", async ({ page }) => {
    await capacityInventory(page).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    await page.locator("aside").getByRole("button", { name: "View activity →" }).click();
    await expect(page.getByRole("button", { name: /Remote table events/ })).toBeVisible();
    await expect(page.getByText("get Taiwan gov panel")).toBeVisible();
  });

  test("Ask about account limit carries Resources context into rail", async ({ page }) => {
    await capacityInventory(page).locator('[data-kind="metered"]', { hasText: "BigQuery" }).click();
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await rail.getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Resources · BigQuery");
    await expect(rail).toContainText("Explain this metered Resources provider");
  });

  test("approval review row lives in Usage", async ({ page }) => {
    const main = page.locator("main");
    await page.getByRole("button", { name: "Usage", exact: true }).click();
    await expect(main.getByRole("heading", { name: "Review queue" })).toBeVisible();
    await expect(main.getByRole("button", { name: /awaiting approval/ })).toBeVisible();
    await expect(main.getByRole("button", { name: /Approval needed/ })).toBeVisible();
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
  await expect(main.getByRole("status")).toContainText("Loading resources");
  await expect(main.getByText("Current status")).toHaveCount(0);
  await expect(main.getByText("Account summary")).toHaveCount(0);

  releaseResources();
  await waitForShell(page);
  await expect(main.getByRole("region", { name: "Capacity and access" })).toBeVisible();
});

test("v2 Resources API failure reports unknown capability instead of a healthy fallback", async ({ page }) => {
  await mockV2Api(page);
  await page.route("**/library/desk/resources*", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "unavailable" }) }),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });

  const main = page.locator("main");
  await expect(main.getByRole("status", { name: "Resources status unavailable" })).toContainText(
    "Live desk capability data could not be read",
  );
  await expect(main.getByRole("region", { name: "Capacity and access" })).toHaveCount(0);
  await expect(main.getByText("Declared source routes")).toHaveCount(0);
  await expect(main.getByText("Composer + MCP")).toHaveCount(0);
  await expect(main.getByText("ADC ok")).toHaveCount(0);
  const rail = page.getByRole("complementary", { name: "Inspector" });
  await expect(rail).toContainText("Live capability data unavailable");
  await expect(rail).not.toContainText("Lab capacity");
});
