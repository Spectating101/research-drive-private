import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("v2 Cluster tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=cluster", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("timeline and overlap render for default compare", async ({ page }) => {
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Cluster" })).toBeVisible();
    await expect(page.locator(".rd-v2-timeline .rd-v2-bar-row")).toHaveCount(2);
    await expect(page.locator(".rd-v2-overlap-badge")).toBeVisible();
    await expect(page.locator(".rd-v2-venn-set")).toHaveCount(3);
  });

  test("save compare persists pinned pair", async ({ page }) => {
    await page.getByRole("button", { name: "Save compare" }).click();
    const pinned = await page.evaluate(() => {
      try {
        return JSON.parse(localStorage.getItem("rd_v2_pinned_compares") || "[]");
      } catch {
        return [];
      }
    });
    expect(pinned.length).toBeGreaterThan(0);
  });

  test("export join keys is actionable", async ({ page }) => {
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export join keys" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/join-keys/);
  });

  test("cluster rail shows overlap detail when compare selected", async ({ page }) => {
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Overlap");
    await expect(rail).toContainText("Shared keys");
  });
});
