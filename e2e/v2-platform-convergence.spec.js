import { mkdirSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = "artifacts/platform-convergence";

async function capture(page, name) {
  mkdirSync(OUT, { recursive: true });
  await page.waitForTimeout(220);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
}

async function openAccountDestination(page, destination) {
  await page.getByRole("button", { name: "Account" }).click();
  const menu = page.getByRole("menu", { name: "Account destinations" });
  await expect(menu).toBeVisible();
  await menu.getByRole("menuitem", { name: new RegExp(destination, "i") }).click();
}

test.describe("converged platform shell", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("keeps Home, Library, Resources, Profile, Settings, and the rail connected", async ({ page }) => {
    await expect(page.getByTestId("home-continue")).toBeVisible();
    const pickUpTitle = (await page.getByTestId("home-continue").locator("h2").innerText()).trim();
    await page.getByTestId("home-continue").getByRole("button", { name: "Continue" }).click();
    const preview = page.getByRole("dialog", { name: `${pickUpTitle} preview` });
    await expect(preview).toBeVisible();
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await capture(page, "01-home-resume-preview-desktop");
    await preview.getByRole("button", { name: "Close preview" }).click();

    await page.getByRole("button", { name: "Library", exact: true }).click();
    await expect(page.getByTestId("library-directory")).toBeVisible();
    await page.getByRole("textbox", { name: "Search library holdings" }).fill("Asia");
    const firstDataset = page.locator('.rd-v2-catalog-list button[data-kind="dataset"]').first();
    await expect(firstDataset).toBeVisible();
    await firstDataset.click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Can I use this?");
    await capture(page, "02-library-directory-desktop");

    await page.getByRole("button", { name: "Resources", exact: true }).click();
    await expect(page.getByRole("region", { name: "Sources overview" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Source capabilities" })).toBeVisible();
    await capture(page, "03-resources-sources-desktop");

    await openAccountDestination(page, "Profile");
    await expect(page.getByRole("heading", { name: "Profile", exact: true })).toBeVisible();
    await expect(page.getByTestId("profile-detail-rail")).toBeVisible();
    await capture(page, "04-profile-memory-desktop");

    await openAccountDestination(page, "Settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Desk setup");
    await capture(page, "05-settings-desktop");
  });

  test("keeps five work destinations legible and account pages reachable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const primaryNav = page.locator(".rd-v2-sidebar-nav");
    await expect(primaryNav.getByRole("button")).toHaveCount(5);
    await expect(page.locator(".rd-v2-sidebar-foot-nav")).toBeHidden();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      .toBe(true);
    await capture(page, "06-home-mobile-shell");

    await openAccountDestination(page, "Profile");
    await expect(page.getByRole("heading", { name: "Profile", exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Show Detail.*Ask|Hide panel/ }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toBeVisible();
    await expect(rail.getByTestId("profile-detail-rail")).toBeVisible();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.getByTestId("rail-pane-detail")).toBeHidden();
    await expect(rail).toContainText("What research context do you remember?");
    await expect(rail.getByTestId("ask-composer")).toBeVisible();
    await capture(page, "07-profile-ask-mobile");

    await page.getByRole("button", { name: /Hide panel/ }).click();
    await openAccountDestination(page, "Settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await capture(page, "08-settings-mobile");
  });
});
