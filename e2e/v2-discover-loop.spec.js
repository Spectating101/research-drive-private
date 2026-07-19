import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

/**
 * Discover Explore | History gates for the main-converge tree.
 * Classification: docs/DISCOVER_E2E_AUTHORITY_AUDIT.md
 * Primary viewport 1920×1080.
 */
test.describe("v2 Discover Explore|History (main converge)", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Discover exposes Explore and History as stable modes", async ({ page }) => {
    const modes = page.getByRole("tablist", { name: "Discover mode" });
    await expect(modes.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(modes.getByRole("tab", { name: "History" })).toBeVisible();
    await expect(modes.getByRole("tab", { name: /Activity/ })).toHaveCount(0);

    await modes.getByRole("tab", { name: "History" }).click();
    await expect(page).toHaveURL(/mode=history/);
    await expect(page.getByTestId("discover-history")).toBeVisible();

    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
  });

  test("header pending opens the exact History request when jobs await approval", async ({ page }) => {
    await mockV2Api(page, {
      jobsBody: {
        jobs: [{ id: "pending", status: "pending_approval", plan: { title: "TWSE governance" } }],
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const pending = page.getByTestId("header-pending-link");
    await expect(pending).toBeVisible({ timeout: 10_000 });
    await pending.click();
    await expect(page).toHaveURL(/mode=history/);
    await expect(page.getByRole("tab", { name: /History/ })).toHaveAttribute("aria-selected", "true");
    const rail = page.getByRole("complementary", { name: "Inspector" });
    await expect(rail).toContainText("TWSE governance");
    await expect(rail).toContainText("Approval required");
  });

  test("LEGACY: Activity workspace is not a Discover mode", async ({ page }) => {
    // LEGACY EXPECTATION guard — must stay red/absent, never revive Activity tab.
    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByRole("tab", { name: /Activity/ })).toHaveCount(0);
    await expect(page.getByTestId("discover-activity")).toHaveCount(0);
  });
});
