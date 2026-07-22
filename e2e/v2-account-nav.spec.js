/**
 * Account navigation — primary workspace stack + unified account dialog
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

function expectStableDialogBox(box) {
  expect(box).toBeTruthy();
  // Desktop: one shell — min(960px, 100vw - 48px) × min(720px, 100vh - 48px)
  expect(box.width).toBeGreaterThanOrEqual(900);
  expect(box.width).toBeLessThanOrEqual(960);
  expect(box.height).toBeGreaterThanOrEqual(680);
  expect(box.height).toBeLessThanOrEqual(720);
}

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
    await expect(menu.getByRole("menuitem")).toHaveCount(2);

    const menuBox = await menu.boundingBox();
    expect(menuBox.width).toBeLessThan(420);
    expect(menuBox.height).toBeLessThan(160);

    await page.screenshot({
      path: path.join(OUT, "account_menu_desktop_1440.png"),
      fullPage: false,
    });

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(cluster).toBeFocused();

    // Snapshot Detail rail selection before opening account dialog
    const railBefore = await page.locator(".yzu-inspector").evaluate((el) => ({
      text: (el.innerText || "").slice(0, 240),
      className: el.className,
    }));

    await cluster.click();
    await page.getByTestId("account-menu").getByTestId("account-menu-profile").click();
    const dialog = page.getByTestId("account-dialog-overlay");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog).toHaveAttribute("data-mode", "research");
    const research = page.getByTestId("research-context-overlay");
    await expect(research.getByRole("heading", { name: "Research context" })).toBeVisible();
    await expect(research.getByTestId("account-dialog-modes")).toBeVisible();
    await expect(research.getByTestId("profile-understanding")).toBeVisible();
    await expect(research.getByTestId("profile-understanding-columns")).toBeVisible();
    const basis = research.getByTestId("profile-understanding-provenance");
    await expect(basis).toBeVisible();
    await expect(basis).not.toHaveAttribute("open", "");
    await expect(basis.locator("summary")).toHaveText(/Evidence basis/i);
    await expect(research.getByTestId("profile-context-source")).toBeVisible();
    await expect(research.getByTestId("profile-source-line")).toContainText(/drkong@saturn\.yzu\.edu\.tw/i);
    await expect(research.getByTestId("profile-context-change")).toBeVisible();
    await expect(research.getByTestId("profile-bind-form")).toHaveCount(0);
    await research.getByTestId("profile-context-change").click();
    await expect(research.getByTestId("profile-bind-form")).toBeVisible();
    await expect(research.getByTestId("profile-email-input")).toBeVisible();
    await expect(research.getByTestId("profile-save-identity")).toBeVisible();
    await expect(research.getByTestId("profile-clear-context")).toBeVisible();
    await research.getByTestId("profile-context-cancel").click();
    await expect(research.getByTestId("profile-bind-form")).toHaveCount(0);

    const boundBox = await research.boundingBox();
    expectStableDialogBox(boundBox);

    await page.screenshot({
      path: path.join(OUT, "account_bound_research_context_desktop_1440.png"),
      fullPage: false,
    });

    // Switch in-dialog to Workspace preferences — same shell, not Detail rail
    await research.getByTestId("account-dialog-mode-preferences").click();
    await expect(dialog).toHaveAttribute("data-mode", "preferences");
    const prefs = page.getByTestId("workspace-prefs-overlay");
    await expect(prefs.getByRole("heading", { name: "Workspace preferences" })).toBeVisible();
    await expect(prefs.getByTestId("workspace-preferences")).toBeVisible();
    await expect(prefs.getByTestId("settings-dialog-columns")).toBeVisible();
    const formBox = await prefs.getByTestId("settings-centre").boundingBox();
    const prefsBox = await prefs.boundingBox();
    expect(formBox).toBeTruthy();
    expect(prefsBox).toBeTruthy();
    expect(formBox.width).toBeGreaterThanOrEqual(480);
    expect(formBox.width).toBeLessThanOrEqual(560);
    // Horizontally centered in the 960 shell (±24px)
    const formCenter = formBox.x + formBox.width / 2;
    const prefsCenter = prefsBox.x + prefsBox.width / 2;
    expect(Math.abs(formCenter - prefsCenter)).toBeLessThan(24);
    const chrome = prefs.locator(".rd-v2-account-dialog-chrome");
    const chromeBox = await chrome.boundingBox();
    expect(chromeBox.height).toBeLessThan(64);
    await expect(prefs.getByTestId("settings-group-context")).toHaveCount(0);
    await expect(prefs.getByTestId("settings-email-input")).toHaveCount(0);
    await expect(prefs.getByTestId("settings-group-workspace")).toBeVisible();
    await expect(prefs.getByTestId("settings-default-tab")).toBeVisible();
    await expect(prefs.getByTestId("settings-on-select")).toBeVisible();
    await expect(prefs.getByTestId("workspace-prefs-compact")).toHaveCount(0);
    await expect(page.getByTestId("settings-detail-rail")).toHaveCount(0);
    await expect(page.getByTestId("profile-detail-rail")).toHaveCount(0);

    expectStableDialogBox(prefsBox);
    expect(Math.abs(prefsBox.width - boundBox.width)).toBeLessThan(2);
    expect(Math.abs(prefsBox.height - boundBox.height)).toBeLessThan(2);

    const railAfter = await page.locator(".yzu-inspector").evaluate((el) => ({
      text: (el.innerText || "").slice(0, 240),
      className: el.className,
    }));
    expect(railAfter.className).toBe(railBefore.className);

    await page.screenshot({
      path: path.join(OUT, "account_workspace_prefs_desktop_1440.png"),
      fullPage: false,
    });

    await prefs.getByTestId("workspace-prefs-close").click();
    await expect(dialog).toHaveCount(0);
  });

  test("unbound research context uses the same dialog shell", async ({ page }) => {
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
    await expect(menu.getByRole("menuitem")).toHaveCount(2);
    const menuBox = await menu.boundingBox();
    expect(menuBox.width).toBeLessThan(420);

    await page.screenshot({
      path: path.join(OUT, "account_unbound_desktop_1440.png"),
      fullPage: false,
    });

    await menu.getByTestId("account-menu-profile").click();
    const research = page.getByTestId("research-context-overlay");
    await expect(research).toBeVisible({ timeout: 15_000 });
    // Chrome stays above the unbound body — same fixed shell header
    await expect(research.getByRole("heading", { name: "Research context" })).toBeVisible();
    await expect(research.getByTestId("account-dialog-modes")).toBeVisible();
    await expect(research.getByTestId("research-context-close")).toBeVisible();
    const chromeBox = await research.locator(".rd-v2-account-dialog-chrome").boundingBox();
    const bodyBox = await research.locator(".rd-v2-account-overlay-body").boundingBox();
    expect(chromeBox).toBeTruthy();
    expect(bodyBox).toBeTruthy();
    expect(chromeBox.y).toBeLessThan(bodyBox.y);
    expect(chromeBox.y + chromeBox.height).toBeLessThanOrEqual(bodyBox.y + 1);
    await expect(research.getByTestId("profile-unbound-badge")).toBeVisible();
    await expect(research.getByTestId("profile-email-input")).toBeVisible();
    await expect(research.getByTestId("profile-save-identity")).toHaveText(/Connect faculty email/i);
    await expect(research.getByTestId("profile-primary-command")).toHaveCount(0);
    await expect(research.getByTestId("settings-email-input")).toHaveCount(0);
    const identityBox = await research.getByTestId("profile-identity").boundingBox();
    expect(identityBox).toBeTruthy();
    expect(chromeBox.y + chromeBox.height).toBeLessThanOrEqual(identityBox.y + 1);
    expectStableDialogBox(await research.boundingBox());

    await page.screenshot({
      path: path.join(OUT, "account_unbound_research_context_desktop_1440.png"),
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
    await expect(menu.getByRole("menuitem")).toHaveCount(2);

    await page.screenshot({
      path: path.join(OUT, "account_bound_mobile_menu_390.png"),
      fullPage: false,
    });

    await menu.getByTestId("account-menu-profile").click();
    const research = page.getByTestId("research-context-overlay");
    await expect(research).toBeVisible({ timeout: 15_000 });
    await expect(research.getByTestId("profile-understanding")).toBeVisible();
    const researchBox = await research.boundingBox();
    expect(researchBox).toBeTruthy();
    expect(researchBox.width).toBeGreaterThanOrEqual(360);
    expect(researchBox.height).toBeGreaterThan(500);

    await page.screenshot({
      path: path.join(OUT, "account_bound_research_context_mobile_390.png"),
      fullPage: false,
    });

    await research.getByTestId("research-context-close").click();
    await expect(page.getByTestId("account-dialog-overlay")).toHaveCount(0);

    await page.getByTestId("header-account-menu").click();
    await page.getByTestId("account-menu").getByTestId("account-menu-workspace").click();
    const prefs = page.getByTestId("workspace-prefs-overlay");
    await expect(prefs).toBeVisible();
    await expect(prefs.getByTestId("workspace-preferences")).toBeVisible();
    await prefs.getByTestId("settings-default-tab").selectOption("library");
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("rd_v2_settings") || "{}"));
    expect(stored.defaultTab).toBe("library");

    await page.screenshot({
      path: path.join(OUT, "account_bound_mobile_sheet_390.png"),
      fullPage: false,
    });
  });

  test("direct Profile and Settings URLs open the same account dialog modes", async ({ page }) => {
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
    const dialog = page.getByTestId("account-dialog-overlay");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog).toHaveAttribute("data-mode", "research");
    await expect(page.getByTestId("research-context-overlay").getByRole("heading", { name: "Research context" })).toBeVisible();
    await expect(page.getByTestId("profile-understanding")).toBeVisible();
    expectStableDialogBox(await page.getByTestId("research-context-overlay").boundingBox());

    await page.screenshot({
      path: path.join(OUT, "legacy_profile_url_overlay_desktop_1440.png"),
      fullPage: false,
    });

    await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("account-dialog-overlay")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("account-dialog-overlay")).toHaveAttribute("data-mode", "preferences");
    await expect(
      page.getByTestId("workspace-prefs-overlay").getByRole("heading", { name: "Workspace preferences" }),
    ).toBeVisible();
    await expect(page.getByTestId("settings-group-workspace")).toBeVisible();
    await expect(page.getByTestId("settings-group-context")).toHaveCount(0);
    await expect(page.getByTestId("settings-email-input")).toHaveCount(0);
    expectStableDialogBox(await page.getByTestId("workspace-prefs-overlay").boundingBox());
  });
});
