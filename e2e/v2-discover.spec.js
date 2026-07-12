import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

test.describe("v2 Discover tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("empty state shows suggestions before search", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Discover external datasets" })).toBeVisible();
    await expect(page.getByRole("button", { name: "TWSE governance" })).toBeVisible();
  });

  test("suggestion chip fills header search and shows demo results", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator(".rd-v2-search-pill input")).toHaveValue("TWSE governance");
    await expect(page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate')).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-browse-groups")).toContainText("TWSE OpenAPI");
    await expect(page.getByTestId("discover-result-summary")).toContainText(/1 result/i);
    await expect(page.getByTestId("discover-filter-menu")).toBeVisible();
    await expect(page.getByTestId("discover-browse-mode")).not.toContainText(/process overview/i);
  });

  test("selecting discover row opens evaluation surface with decision hierarchy", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
    const surface = page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface");
    await expect(surface).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-title")).toContainText("MOPS financial statements");
    await expect(surface).toContainText("Can I use this?");
    await expect(surface).toContainText("Useful for");
    await expect(surface).toContainText("Still unknown");
    await expect(surface.locator(".rd-v2-eval-tech")).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await expect(page.locator('[data-testid="discover-eval-actions"] .rd-v2-btn.primary', { hasText: "Add to lab" })).toBeVisible();
    await expect(page.getByTestId("discover-focus-workspace")).toBeVisible();
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface")).not.toContainText("What we know");
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface")).not.toContainText("Possession");
  });

  test("mobile Discover Focus owns the viewport until Ask is opened explicitly", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();

    const shell = page.locator(".rd-v2-shell");
    const rail = page.locator("aside.rd-v2-rail");
    const actions = page.getByTestId("discover-eval-actions");

    await expect(page.getByTestId("discover-focus-workspace")).toBeVisible();
    await expect(shell).toHaveClass(/no-rail/);
    await expect(rail).toHaveClass(/rd-v2-rail-collapsed/);
    await expect(rail).not.toBeVisible();
    await expect(actions.locator(".rd-v2-btn.primary")).toHaveCount(1);

    const focusGeometry = await page.evaluate(() => {
      const main = document.querySelector(".yzu-main");
      const actionRegion = document.querySelector('[data-testid="discover-eval-actions"]');
      const primary = actionRegion?.querySelector(".rd-v2-btn.primary");
      const secondary = actionRegion?.querySelector(".rd-v2-eval-mobile-secondary-row");
      const mobileNav = document.querySelector(".yzu-sidebar");
      const actionRect = actionRegion?.getBoundingClientRect();
      const primaryRect = primary?.getBoundingClientRect();
      const secondaryRect = secondary?.getBoundingClientRect();
      const navRect = mobileNav?.getBoundingClientRect();
      return {
        viewportHeight: window.innerHeight,
        viewportWidth: window.innerWidth,
        documentScrollHeight: document.documentElement.scrollHeight,
        documentScrollWidth: document.documentElement.scrollWidth,
        mainPaddingBottom: main ? getComputedStyle(main).paddingBottom : null,
        actionsBottom: actionRect?.bottom ?? null,
        navTop: navRect?.top ?? null,
        primaryLeft: primaryRect?.left ?? null,
        primaryRight: primaryRect?.right ?? null,
        secondaryLeft: secondaryRect?.left ?? null,
        secondaryRight: secondaryRect?.right ?? null,
      };
    });

    expect(focusGeometry.documentScrollHeight).toBeLessThanOrEqual(focusGeometry.viewportHeight);
    expect(focusGeometry.documentScrollWidth).toBeLessThanOrEqual(focusGeometry.viewportWidth);
    expect(focusGeometry.mainPaddingBottom).toBe("0px");
    expect(focusGeometry.actionsBottom).toBeLessThanOrEqual(focusGeometry.navTop - 6);
    expect(focusGeometry.actionsBottom).toBeGreaterThanOrEqual(focusGeometry.navTop - 24);
    expect(Math.round(focusGeometry.primaryLeft)).toBe(12);
    expect(Math.round(focusGeometry.primaryRight)).toBe(378);
    expect(Math.round(focusGeometry.secondaryLeft)).toBe(12);
    expect(Math.round(focusGeometry.secondaryRight)).toBe(378);

    await page.getByTestId("discover-focus-workspace").getByRole("button", { name: "Ask", exact: true }).click();
    await expect(shell).not.toHaveClass(/no-rail/);
    await expect(rail).not.toHaveClass(/rd-v2-rail-collapsed/);
    await expect(rail).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();

    await page.getByTestId("discover-focus-workspace").getByRole("button", { name: "Ask", exact: true }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText("MOPS financial statements");
    await expect(page.getByTestId("ask-messages")).toContainText("Assess this");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS financial statements");
  });

  test("Probe source shows verified facts; technical evidence stays collapsed", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    await page.locator('[data-testid="discover-eval-actions"]').getByRole("button", { name: "Probe source" }).click();
    const surface = page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText("text/csv");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText(/domain observed/i);
    await expect(surface.locator(".rd-v2-eval-verified")).not.toContainText("MOPS publisher");
    await expect(surface.locator(".rd-v2-eval-inferred")).toContainText(/direct file|machine-readable/i);
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await surface.locator(".rd-v2-eval-tech > summary").click();
    await expect(surface.locator(".rd-v2-eval-tech")).toHaveAttribute("open");
  });
});
