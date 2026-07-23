/**
 * Account navigation — primary workspace stack + account menu overlays
 * (Profile/Settings are not page-level nav destinations).
 */
import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "../docs/status/generated/profile-settings-visual");

const PROFILE = {
  found: true,
  profile: {
    name_en: "Kong, De-Rong",
    title: "Assistant Professor",
    discipline: "Finance",
    email: "drkong@saturn.yzu.edu.tw",
    specialties: ["empirical asset pricing"],
    research_tracks: [
      { id: "token", title: "Token taxonomy — on-chain and off-chain data", phase: "active_grant", weight: 10 },
    ],
    method_tags: ["panel_data"],
    publication_highlights: ["Kong, D.-R. (2021). Alternative investments in the FinTech era."],
    lab_fintech_stack: [{ id: "coingecko", label: "CoinGecko prices", route: "vault" }],
    procurement_recommendations: [
      { dataset: "TWSE daily prices", source_route: "vault", search_query: "TWSE daily prices" },
    ],
  },
};

test.describe("Account cluster navigation", () => {
  test("desktop sidebar is five workspace tabs + account cluster; menu has real actions", async ({
    page,
  }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try {
        localStorage.setItem("procure_user_email", "drkong@saturn.yzu.edu.tw");
      } catch {
        /* ignore */
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const nav = page.locator(".yzu-sidebar nav");
    await expect(nav.getByRole("button", { name: /^Home$/i })).toBeVisible();
    await expect(nav.getByRole("button", { name: /^Library$/i })).toBeVisible();
    await expect(nav.getByRole("button", { name: /^Discover$/i })).toBeVisible();
    await expect(nav.getByRole("button", { name: /^Synthesis$/i })).toBeVisible();
    await expect(nav.getByRole("button", { name: /^Resources$/i })).toBeVisible();
    await expect(nav.getByRole("button", { name: /^Profile$/i })).toHaveCount(0);
    await expect(nav.getByRole("button", { name: /^Settings$/i })).toHaveCount(0);

    // Header account control must be normally clickable on desktop (rail must not intercept).
    // Collapsed rail class must not apply at 1440 — otherwise it intercepts.
    await expect(page.locator(".yzu-inspector")).not.toHaveClass(/rd-v2-rail-collapsed/);
    const headerAccount = page.getByTestId("header-account-menu");
    await expect(headerAccount).toBeVisible();
    await headerAccount.click();
    await expect(page.getByTestId("account-menu")).toBeVisible();
    await expect(page.getByTestId("account-menu").getByRole("menuitem")).toHaveCount(2);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("account-menu")).toHaveCount(0);

    const cluster = page.getByTestId("sidebar-account-menu");
    await expect(cluster).toBeVisible();
    await expect(cluster).toContainText(/Kong/i);

    await cluster.click();
    const menu = page.getByTestId("account-menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByTestId("account-menu-profile")).toContainText(/Research context/i);
    await expect(menu.getByTestId("account-menu-workspace")).toContainText(/Workspace preferences/i);
    await expect(menu.getByTestId("account-menu-context")).toHaveCount(0);
    await expect(menu.getByTestId("account-menu-clear")).toHaveCount(0);
    await expect(menu.getByTestId("account-menu-advanced")).toHaveCount(0);
    await expect(menu.getByRole("menuitem")).toHaveCount(2);

    await page.screenshot({
      path: path.join(OUT, "account_menu_desktop_1440.png"),
      fullPage: false,
    });

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(cluster).toBeFocused();

    await cluster.click();
    await page.getByTestId("account-menu").getByTestId("account-menu-profile").click();
    const research = page.getByTestId("research-context-overlay");
    await expect(research).toBeVisible({ timeout: 15_000 });
    await expect(research.getByRole("heading", { name: "Research context" })).toBeVisible();
    await expect(research.getByTestId("profile-understanding")).toBeVisible();

    await page.screenshot({
      path: path.join(OUT, "account_bound_research_context_desktop_1440.png"),
      fullPage: false,
    });

    await research.getByTestId("research-context-close").click();
    await expect(research).toHaveCount(0);

    await cluster.click();
    await page.getByTestId("account-menu").getByTestId("account-menu-workspace").click();
    const prefs = page.getByTestId("workspace-prefs-overlay");
    await expect(prefs).toBeVisible();
    await expect(prefs.getByRole("heading", { name: "Workspace preferences" })).toBeVisible();
    await expect(prefs.getByTestId("workspace-preferences")).toBeVisible();
    await expect(prefs.getByTestId("workspace-prefs-compact")).toBeVisible();
    await expect(prefs.getByTestId("workspace-default-tab")).toBeVisible();
    await expect(prefs.getByTestId("workspace-on-select")).toBeVisible();
    await expect(prefs.getByTestId("settings-group-context")).toHaveCount(0);
    await expect(prefs.getByTestId("settings-open-health")).toHaveCount(0);

    await page.screenshot({
      path: path.join(OUT, "account_workspace_prefs_desktop_1440.png"),
      fullPage: false,
    });
  });

  test("unbound account cluster labels Research context", async ({ page }) => {
    await mockV2Api(page);
    await page.addInitScript(() => {
      try {
        localStorage.removeItem("procure_user_email");
      } catch {
        /* ignore */
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const cluster = page.getByTestId("sidebar-account-menu");
    await expect(cluster).toContainText(/Research context/i);
    await expect(cluster).toContainText(/Unbound/i);
    await cluster.click();
    const menu = page.getByTestId("account-menu");
    await expect(menu.getByTestId("account-menu-profile")).toBeVisible();
    await expect(menu.getByTestId("account-menu-workspace")).toBeVisible();
    await expect(menu.getByTestId("account-menu-context")).toHaveCount(0);
    await expect(menu.getByRole("menuitem")).toHaveCount(2);

    await page.screenshot({
      path: path.join(OUT, "account_unbound_desktop_1440.png"),
      fullPage: false,
    });
  });

  test("mobile keeps five nav items; header avatar opens sheet overlays", async ({
    page,
  }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try {
        localStorage.setItem("procure_user_email", "drkong@saturn.yzu.edu.tw");
      } catch {
        /* ignore */
      }
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const nav = page.locator(".yzu-sidebar nav");
    await expect(nav.getByRole("button")).toHaveCount(5);
    await expect(page.getByTestId("sidebar-account-cluster")).toBeHidden();

    await page.getByTestId("header-account-menu").click();
    const menu = page.getByTestId("account-menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByTestId("account-menu-profile")).toBeVisible();
    await expect(menu.getByTestId("account-menu-workspace")).toBeVisible();
    await expect(menu.getByRole("menuitem")).toHaveCount(2);

    await page.screenshot({
      path: path.join(OUT, "account_bound_mobile_menu_390.png"),
      fullPage: false,
    });

    await menu.getByTestId("account-menu-workspace").click();
    const prefs = page.getByTestId("workspace-prefs-overlay");
    await expect(prefs).toBeVisible();
    await expect(prefs.getByTestId("workspace-preferences")).toBeVisible();
    await prefs.getByTestId("workspace-default-tab").selectOption("library");
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("rd_v2_settings") || "{}"));
    expect(stored.defaultTab).toBe("library");

    await page.screenshot({
      path: path.join(OUT, "account_bound_mobile_sheet_390.png"),
      fullPage: false,
    });
  });

  test("direct Profile and Settings URLs open overlays", async ({ page }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try {
        localStorage.setItem("procure_user_email", "drkong@saturn.yzu.edu.tw");
      } catch {
        /* ignore */
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("research-context-overlay")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByTestId("research-context-overlay").getByRole("heading", { name: "Research context" }),
    ).toBeVisible();
    await expect(page.getByTestId("profile-understanding")).toBeVisible();

    await page.screenshot({
      path: path.join(OUT, "legacy_profile_url_overlay_desktop_1440.png"),
      fullPage: false,
    });

    await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("workspace-prefs-overlay")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByTestId("workspace-prefs-overlay").getByRole("heading", { name: "Workspace preferences" }),
    ).toBeVisible();
    await expect(page.getByTestId("settings-group-context")).toBeVisible();
  });
});
