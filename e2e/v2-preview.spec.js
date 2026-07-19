import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("v2 adaptive Preview", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=library", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("owned datasets open as a bounded rows and fields viewer", async ({ page }) => {
    await page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "Research panels" }).click();
    await page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "gdelt" }).click();
    await page.locator('.rd-v2-library-asset[data-kind="dataset"]', { hasText: "Asia daily news-risk panel" }).click();
    await page.locator("aside.rd-v2-rail").getByRole("button", { name: "Preview rows" }).click();

    const preview = page.getByRole("dialog", { name: "Asia daily news-risk panel preview" });
    await expect(preview).toBeVisible();
    await expect(preview).toContainText("Dataset preview");
    await expect(preview.getByRole("button", { name: "Rows", exact: true })).toBeVisible();
    await expect(preview.getByRole("button", { name: "Fields", exact: true })).toBeVisible();
    await expect(preview.getByRole("button", { name: "Query", exact: true })).toHaveCount(0);
    await expect(preview).toContainText("Observed sample");
    await expect(preview.locator("table")).toContainText("country");

    await preview.getByRole("button", { name: "Fields", exact: true }).click();
    await expect(preview).toContainText("Field inventory");
    await expect(preview).toContainText("database-schema guarantee");

    await preview.getByRole("button", { name: "Close preview" }).click();
    await expect(preview).toHaveCount(0);
  });
});
