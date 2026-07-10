import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";

test.describe("Research Drive view parity", () => {
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

  test("home composition", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
    await expect(page.getByPlaceholder("Search datasets in the library")).toBeVisible();
    await page.screenshot({ path: `${OUT}/desk-parity-home.png`, fullPage: false });
  });

  test("library table opens dataset tabs", async ({ page }) => {
    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
    await expect(page.getByRole("heading", { name: "Drive", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Lab", exact: true }).click();
    await page.locator(".rd-catalog-table tbody tr:has(.rd-file)").first().click();
    await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
    await expect(page.getByRole("button", { name: "Overview" })).toBeVisible();
    await page.locator("main").getByRole("button", { name: "Preview", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: `${OUT}/desk-parity-dataset-preview.png`, fullPage: false });
  });

  test("more menu pages", async ({ page }) => {
    await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Pipeline/ }).first().click();
    await expect(page.getByRole("heading", { name: /^Activity$/ })).toBeVisible();
    await page.screenshot({ path: `${OUT}/desk-parity-activity.png`, fullPage: false });
  });
});
