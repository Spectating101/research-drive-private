/**
 * UX audit — data library workspace (option B).
 */
import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";

async function navTo(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

test.describe("UX audit — data library workspace", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem("rd_recent_datasets", JSON.stringify([{ id: "coingecko_simple_price", at: Date.now() }]));
    });
    await page.reload();
  });

  test("A1 desktop home — library first", async ({ page }) => {
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await page.locator(".rd-catalog-table .rd-title").first().waitFor({ timeout: 30_000 });
    await page.screenshot({ path: `${OUT}/audit-01-home-desktop.png`, fullPage: false });

    await expect(page.locator(".yzu-inspector")).toBeVisible();
    await expect(page.locator(".rd-library-stats")).toBeVisible();
    await expect(page.locator(".rd-quick-tile")).toHaveCount(0);
    await expect(page.locator(".rd-procure-footnote")).toBeVisible();
    await expect(page.locator(".rd-signin-banner")).toHaveCount(0);
  });

  test("A2 details panel default on home — not source chat", async ({ page }) => {
    await page.locator(".rd-catalog-table .rd-title").first().waitFor({ timeout: 30_000 });

    await expect(page.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".rd-inspector-idle, .rd-inspector-compact")).toBeVisible();
    await expect(page.locator(".ds-console-head")).toHaveCount(0);
    const pill = page.locator(".rd-catalog-table .rd-pill").first();
    await expect(pill).toBeVisible();
    const box = await pill.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(24);
  });

  test("A3 dataset detail keeps details rail", async ({ page }) => {
    await page.locator(".rd-catalog-table .rd-title").first().waitFor({ timeout: 30_000 });
    await page.locator(".rd-catalog-table tbody tr").first().click();
    await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
    await page.getByRole("button", { name: "Overview" }).waitFor({ timeout: 15_000 });
    await page.screenshot({ path: `${OUT}/audit-03-dataset-with-rail.png`, fullPage: false });

    await expect(page.locator("aside.yzu-inspector")).toBeVisible();
    await expect(page.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".ds-console-head")).toHaveCount(0);
  });

  test("A4 discover page loads", async ({ page }) => {
    await navTo(page, "Discover");
    await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-grid .rd-discover-card, .rd-discover-grid .rd-discover-empty"),
      { timeout: 30_000 },
    );
    await page.screenshot({ path: `${OUT}/audit-04-discover.png`, fullPage: false });
  });

  test("A5 browse views hide duplicate sign-in banner", async ({ page }) => {
    await navTo(page, "Drive");
    await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
    await page.screenshot({ path: `${OUT}/audit-05-lab-signin-banner.png`, fullPage: false });
    await expect(page.locator(".rd-signin-banner")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Sign in/i })).toBeVisible();
  });

  test("A6 mobile — layout stress", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await page.screenshot({ path: `${OUT}/audit-06-mobile.png`, fullPage: true });
    await expect(page.locator(".rd-catalog-table")).toBeVisible();
  });

  test("Chat nav available but secondary", async ({ page }) => {
    await page.locator("main .rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first().waitFor({ timeout: 20_000 }).catch(async () => {
      await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
      await page.locator("main .rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first().waitFor({ timeout: 20_000 });
    });
    await expect(page.locator(".rd-inspector-idle")).toBeVisible();
    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Source/ }).first().click();
    await expect(page.getByRole("heading", { name: /Source & compare/i })).toBeVisible();
    await page.screenshot({ path: `${OUT}/audit-07-source-tab.png`, fullPage: false });
  });

  test("A8 selection shows details in rail", async ({ page }) => {
    await page.locator(".rd-catalog-table .rd-title").first().waitFor({ timeout: 30_000 });
    await page.locator(".rd-catalog-table tbody tr").first().click();

    await expect(page.locator(".rd-selection-bar")).toBeVisible();
    await expect(page.locator(".rd-inspector-compact h2")).toBeVisible();
    await page.screenshot({ path: `${OUT}/audit-08-selection-toolbar.png`, fullPage: false });

    await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Clear" }).click();
    await expect(page.locator(".rd-selection-bar")).toHaveCount(0);
    await expect(page.locator(".rd-inspector-idle")).toBeVisible();
  });

  test("A9 discover filter chips", async ({ page }) => {
    await navTo(page, "Discover");
    await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
    await expect(page.locator(".rd-discover-toolbar .rd-chip")).toHaveCount(5);
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-grid .rd-discover-card, .rd-discover-grid .rd-discover-empty"),
      { timeout: 30_000 },
    );
    await page.locator(".rd-discover-toolbar .rd-chip").filter({ hasText: "Catalog" }).click();
    await expect(page.locator(".rd-discover-toolbar .rd-chip.active")).toHaveText("Catalog");
    await page.screenshot({ path: `${OUT}/audit-09-discover-filters.png`, fullPage: false });
  });
});
