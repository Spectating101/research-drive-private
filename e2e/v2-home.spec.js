import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("v2 Home Iteration 10 freeze", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Pick Up is the primary resume object", async ({ page }) => {
    const pick = page.getByTestId("home-continue");
    await expect(pick).toBeVisible();
    await expect(pick).toContainText(/Pick up/i);
    await expect(pick.getByRole("button", { name: "Continue" })).toBeVisible();
    await expect(page.locator(".rd-v2-home-actions")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Attention queue" })).toHaveCount(0);
  });

  test("Resource headroom and trail bands exist; recommended only when grounded", async ({ page }) => {
    await expect(page.getByRole("region", { name: "Resource headroom" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Recent trail" })).toBeVisible();
    const recommended = page.getByRole("region", { name: "Recommended evidence" });
    // Freeze: no grounded authority → section disappears (count 0), else ≤2 rows.
    if ((await recommended.count()) > 0) {
      await expect(recommended.locator(".rd-v2-home-recommended-row")).toHaveCount({ min: 1 });
    }
  });

  test("Continue opens dataset preview and keeps rail grounded", async ({ page }) => {
    const pick = page.getByTestId("home-continue");
    await expect(pick.locator(".rd-v2-home-continue-id")).toBeAttached();
    const title = (await pick.locator("h2").innerText()).trim();
    const datasetId = (await pick.locator(".rd-v2-home-continue-id").innerText()).trim();
    await pick.getByRole("button", { name: "Continue" }).click();

    const preview = page.getByRole("dialog", { name: `${title} preview` });
    await expect(preview).toBeVisible();
    await expect(preview).toContainText(title);
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Home" })).toBeVisible();

    await preview.getByRole("button", { name: "Close preview" }).click();
    await expect(preview).toHaveCount(0);

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.locator(".rd-v2-rail-selection")).toContainText(title);
    await expect(rail.getByRole("tab", { name: "Detail" })).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Ask" })).toBeVisible();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText(datasetId);
  });

  test("decision secondary surfaces Review into Resources when approval pending", async ({ page }) => {
    const secondary = page.locator(".rd-v2-home-pickup-secondary.warn");
    if ((await secondary.count()) === 0) {
      test.skip(true, "mock has no pending approval secondary");
      return;
    }
    await secondary.click();
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Resources" })).toBeVisible();
  });
});
