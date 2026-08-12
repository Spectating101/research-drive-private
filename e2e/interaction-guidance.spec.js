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
    await page.goto("/?tab=library", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByRole("textbox", { name: "Search library holdings" }).fill("Asia");

    const help = page.getByRole("button", { name: /^Explain / }).first();
    await expect(help).toBeVisible();
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

  test("Settings does not claim Ready when the assistant is configured but unverified", async ({ page }) => {
    // Regression: /health.desk.composer_runtime distinguishes configured from
    // verified-live (this is also exactly why /health.status can flip to
    // "degraded" while composer_configured stays true). Settings must not
    // collapse that distinction back into a bare "Ready" — its own tooltip
    // says "never invents Ready."
    const health = {
      ...MOCK_HEALTH,
      status: "degraded",
      desk: {
        ...MOCK_HEALTH.desk,
        composer_configured: true,
        composer_model: "composer-2.5",
        composer_runtime: {
          status: "unverified",
          configured: true,
          verified: false,
          checked_at: null,
          model: "",
        },
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
    await expect(assistant).not.toContainText("Ready");
    await expect(assistant).toContainText("Unverified");
  });

  test("Settings shows Ready when composer_runtime confirms a live-verified probe", async ({ page }) => {
    const health = {
      ...MOCK_HEALTH,
      desk: {
        ...MOCK_HEALTH.desk,
        composer_configured: true,
        composer_model: "composer-2.5",
        composer_runtime: {
          status: "ready",
          configured: true,
          verified: true,
          checked_at: "2026-08-12T10:00:00Z",
          model: "composer-2.5",
        },
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
    await expect(assistant).toContainText("confirmed live");
  });

  test("Settings does not claim Ready for a degraded (failed-probe) runtime, even though verified is true", async ({ page }) => {
    // Regression (caught in review): record_composer_failure() sets
    // verified: true because a real probe DID run — it just failed.
    // Branching on `verified` alone renders a failed provider as Ready.
    const health = {
      ...MOCK_HEALTH,
      status: "degraded",
      desk: {
        ...MOCK_HEALTH.desk,
        composer_configured: true,
        composer_model: "composer-2.5",
        composer_runtime: {
          status: "degraded",
          configured: true,
          verified: true,
          checked_at: "2026-08-12T10:00:00Z",
          error_category: "timeout",
        },
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
    await expect(assistant).not.toContainText("Ready");
    await expect(assistant).toContainText("Degraded");
  });

  test("Settings distinguishes a stale runtime observation from never-probed", async ({ page }) => {
    const health = {
      ...MOCK_HEALTH,
      status: "degraded",
      desk: {
        ...MOCK_HEALTH.desk,
        composer_configured: true,
        composer_model: "composer-2.5",
        composer_runtime: {
          status: "stale",
          configured: true,
          verified: false,
          age_seconds: 999,
          error_category: "stale_observation",
        },
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
    await expect(assistant).not.toContainText("Ready");
    await expect(assistant).toContainText("Needs recheck");
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
