import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell, MOCK_HEALTH } from "./fixtures/v2MockApi.js";

async function openTab(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

test.describe("Research Drive interaction guidance", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("readiness states open a richer explanation by click and keyboard", async ({ page }) => {
    const help = page.getByRole("button", { name: /^Explain / }).first();
    await expect(help).toBeVisible();

    await help.click();
    const popover = page.getByTestId("rich-context-popover");
    await expect(popover).toBeVisible();
    await expect(popover).toContainText(/Query ready|Registered|Connected source/);
    await expect(popover).toContainText("Safest next step");
    await page.keyboard.press("Escape");
    await expect(popover).toHaveCount(0);

    await help.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("rich-context-popover")).toBeVisible();
  });

  test("rich context help opens by tap and remains inside the mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const help = page.getByRole("button", { name: /^Explain / }).first();
    await help.click();
    const popover = page.getByTestId("rich-context-popover");
    await expect(popover).toBeVisible();
    const box = await popover.boundingBox();
    expect(box).toBeTruthy();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(844);
  });

  test("Settings accepts an active runtime identity when the boolean signal is omitted", async ({ page }) => {
    const health = {
      ...MOCK_HEALTH,
      desk: {
        ...MOCK_HEALTH.desk,
        composer_configured: undefined,
        composer_model: "composer-2.5",
      },
    };
    await page.unroute("**/health*");
    await page.route("**/health*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(health) }),
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await openTab(page, "Settings");

    const summary = page.getByRole("region", { name: "Research desk status" });
    const assistant = summary.locator(".rd-v2-settings-summary-card").filter({ hasText: "Research assistant" });
    await expect(assistant).toContainText("Ready");
    await expect(assistant).toContainText("composer-2.5");
    await expect(assistant).not.toContainText("Needs setup");
  });

  test("motion is present by default and suppressed for reduced-motion users", async ({ page }) => {
    const normalAnimation = await page.locator(".rd-v2-page").evaluate((node) => getComputedStyle(node).animationName);
    expect(normalAnimation).toContain("rd-page-enter");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const reducedAnimation = await page.locator(".rd-v2-page").evaluate((node) => getComputedStyle(node).animationName);
    expect(reducedAnimation).toBe("none");
  });
});
