/**
 * Data library first — Details rail default; rail Assistant and full Chat are opt-in.
 */
import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";

test.describe("Research Drive — library with sourcing", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload();
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await page.getByRole("heading", { name: "Recent" }).waitFor({ timeout: 30_000 });
  });

  test("home is library-first", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
    await expect(page.getByPlaceholder("Search datasets in the library")).toBeVisible();
    await expect(page.locator(".rd-inspector-idle, .rd-inspector-compact")).toBeVisible();
    await expect(page.locator(".rd-quick-tile")).toHaveCount(0);

    await page.screenshot({ path: `${OUT}/source-first-home.png`, fullPage: false });
  });

  test("details panel default — chat is opt-in", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await expect(page.locator(".rd-inspector-idle, .rd-inspector-compact")).toBeVisible();
    await expect(page.locator("main .yzu-procure.main")).toHaveCount(0);

    await page.screenshot({ path: `${OUT}/source-first-details-default.png`, fullPage: false });
  });

  test("selection shows dataset details in rail", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
    await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
    const row = page.locator("main .rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first();
    await row.waitFor({ timeout: 20_000 });
    await row.click();
    await expect(page.locator(".rd-selection-bar")).toBeVisible();
    await expect(page.locator(".rd-inspector-compact h2")).toBeVisible();
  });

  test("header chat routes to chat page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.getByPlaceholder("Search datasets in the library").fill("Taiwan equity panel");
    await page.locator(".rd-search").getByRole("button", { name: "Source" }).click();
    await expect(page.getByRole("heading", { name: /Source & compare/i })).toBeVisible();
    await expect(page.locator(".yzu-chat .user").last()).toContainText("Taiwan equity panel");

    await page.screenshot({ path: `${OUT}/source-first-search-source.png`, fullPage: false });
  });

  test("New sheet offers source and upload", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.getByRole("button", { name: "New", exact: true }).first().click();
    await expect(page.getByRole("heading", { name: "New" })).toBeVisible();
    const sheet = page.getByRole("dialog");
    await expect(sheet.getByText("Source dataset")).toBeVisible();
    await expect(sheet.getByText("Upload file")).toBeVisible();

    await page.screenshot({ path: `${OUT}/source-first-new-sheet.png`, fullPage: false });
    await page.getByRole("button", { name: "Close" }).click();
  });

  test("dataset detail keeps details rail", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
    await expect(page.getByRole("heading", { name: "Drive", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Lab", exact: true }).click();
    const datasetRow = page.locator(".rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first();
    await datasetRow.waitFor({ timeout: 20_000 });
    await datasetRow.click();
    await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
    await page.getByRole("button", { name: "Overview" }).waitFor({ timeout: 20_000 });
    await expect(page.locator("aside.yzu-inspector")).toBeVisible();

    await page.screenshot({ path: `${OUT}/source-first-dataset-rail.png`, fullPage: false });
  });

  test("discover nav page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Discover/ }).first().click();
    await expect(page.getByRole("heading", { name: /^Discover$/ })).toBeVisible();
    await expect(page.locator(".rd-discover-toolbar .rd-chip")).toHaveCount(5);
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-grid .rd-discover-card, .rd-discover-grid .rd-discover-empty"),
      { timeout: 30_000 },
    );
    await expect(page.locator(".rd-discover-meta")).toContainText(/result/i);

    await page.screenshot({ path: `${OUT}/source-first-discover.png`, fullPage: false });
  });
});
