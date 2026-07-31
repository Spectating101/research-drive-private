/**
 * Visual closure acceptance — RESEARCH_DRIVE_VISUAL_CLOSURE_FREEZE_2026-07-30.md section 5.
 *
 * Captures the journeys the Discover freeze spec does not already cover, and
 * asserts the VC-1..VC-8 corrections are present in the rendered result rather
 * than only in source.
 *
 * Run: TMPDIR=$PWD/.tmp-pw npx playwright test e2e/visual-closure-acceptance.spec.js
 */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { MOCK_DISCOVER_HIT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = path.resolve("docs/status/generated/visual-closure-2026-07-30");
const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

function ensureOut() {
  fs.mkdirSync(OUT, { recursive: true });
}

async function open(page, url, viewport = DESKTOP, options = {}) {
  await page.setViewportSize(viewport);
  await mockV2Api(page, options);
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await waitForShell(page).catch(() => {});
  await page.waitForTimeout(900);
}

async function shot(page, name) {
  ensureOut();
  await page.screenshot({ path: path.join(OUT, name), fullPage: false });
}

test("Home sparse — start action, no dead sidebar placeholder", async ({ page }) => {
  await open(page, "/?tab=home");
  // VC-8: suggested questions replace dead system language.
  await expect(page.getByRole("region", { name: "Suggested asks" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("No material machine consequences");
  // Sidebar placeholder is removed rather than decorated.
  await expect(page.locator(".rd-v2-sidebar-hint", { hasText: "Recent assets appear" })).toHaveCount(0);
  await shot(page, "home-sparse-1440x900.png");
});

test("Library sparse branch — clear state and bounded intake", async ({ page }) => {
  await open(page, "/?tab=library&folder=zz-empty-branch");
  const empty = page.locator(".rd-v2-library-empty");
  await expect(empty).toContainText("Nothing else in this folder");
  for (const label of ["Add files", "Add URL", "Find missing data"]) {
    await expect(empty.getByRole("button", { name: label })).toBeVisible();
  }
  // Library boundary vocabulary is unified.
  await expect(page.locator("main")).not.toContainText("Lab root");
  await shot(page, "library-sparse-1440x900.png");
});

test("Discover idle — first-use examples, no oversized empty route block", async ({ page }) => {
  await open(page, "/?tab=browse");
  const examples = page.getByTestId("discover-composer-examples");
  await expect(examples.getByText("Try a keyword")).toBeVisible();
  await expect(examples.getByText("Ask a research need")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Sources the desk already knows how to investigate" }),
  ).toHaveCount(0);
  await shot(page, "discover-idle-1440x900.png");
});

test("Synthesis new — lifecycle rail and stated disabled reason", async ({ page }) => {
  await open(page, "/?tab=synthesis");
  const rail = page.getByRole("complementary", { name: "Inspector" });
  // Scope to rail field labels — "Ask" is also the rail tab name.
  const labels = rail.locator(".rd-v2-detail-label");
  for (const step of ["Start", "Ask", "Ground", "Review", "Output"]) {
    await expect(labels.filter({ hasText: new RegExp(`^${step}$`, "i") })).toHaveCount(1);
  }
  await expect(rail).not.toContainText("Choose a blueprint or custom pair");
  // Synthesis nests a studio <main> inside the shell <main>.
  await expect(page.locator("main.yzu-main")).toContainText("Enter an objective to continue");
  await shot(page, "synthesis-new-1440x900.png");
});

test("Resources — one collector vocabulary across toolbar, card, and rail", async ({ page }) => {
  await open(page, "/?tab=resources");
  const phrase = "12 registered · 3 connected · 2 running";
  await expect(page.locator("main")).toContainText(phrase);
  await expect(page.getByRole("complementary", { name: "Inspector" })).toContainText(phrase);
  await expect(page.locator("main")).not.toContainText("joined");
  await shot(page, "resources-1440x900.png");
});

test("Profile thin — actionable memory and Library connections", async ({ page }) => {
  await open(page, "/?tab=profile");
  const main = page.locator("main");
  await expect(main).toContainText("No research direction saved.");
  await expect(main.getByRole("button", { name: "Add research focus" })).toBeVisible();
  await expect(main).toContainText("Library connections");
  await expect(main.getByRole("button", { name: "Find relevant Library assets" })).toBeVisible();
  await expect(main).toContainText("Suggestions appear after a research focus is saved.");
  await shot(page, "profile-thin-1440x900.png");
});

test("Settings connected — state-consistent actions, no production example control", async ({ page }) => {
  await open(page, "/?tab=settings");
  const main = page.locator("main");
  await expect(main.getByRole("button", { name: "Reconnect" })).toBeVisible();
  await expect(main.getByRole("button", { name: "Disconnect" })).toBeVisible();
  // VC-3: a connected desk is not offered a primary Connect action, and the
  // EXAMPLE binding stays out of production presentation.
  await expect(main.getByRole("button", { name: "Connect browser" })).toHaveCount(0);
  await expect(main.getByRole("button", { name: /Use EXAMPLE/ })).toHaveCount(0);
  await shot(page, "settings-connected-1440x900.png");
});

test("Mobile Discover — first result readable, no horizontal overflow", async ({ page }) => {
  await open(page, "/?tab=browse&q=stablecoin", MOBILE, { discoverBody: MOCK_DISCOVER_HIT });
  // The freeze requires the first offering to be readable on a phone, so the
  // capture must show a populated result rather than a miss state.
  const firstRow = page.getByTestId("discover-best-fit").locator(".rd-v2-discover-candidate").first();
  await expect(firstRow).toBeVisible();
  const rowBox = await firstRow.boundingBox();
  expect(rowBox.x).toBeGreaterThanOrEqual(0);
  expect(rowBox.x + rowBox.width).toBeLessThanOrEqual(MOBILE.width);
  const dims = await page.evaluate(() => ({
    viewport: window.innerWidth,
    body: document.body.scrollWidth,
    doc: document.documentElement.scrollWidth,
  }));
  expect(dims.body).toBeLessThanOrEqual(dims.viewport);
  expect(dims.doc).toBeLessThanOrEqual(dims.viewport);
  // VC-2: the closed rail trigger is a compact control, not a full-width bar.
  const grip = await page.locator(".rd-v2-rail-mobile-grip").boundingBox();
  expect(grip).not.toBeNull();
  expect(grip.height).toBeGreaterThanOrEqual(44);
  expect(grip.width).toBeLessThan(dims.viewport * 0.6);
  await shot(page, "discover-mobile-390x844.png");
});

test("Mobile Home and Profile stay within the viewport", async ({ page }) => {
  for (const [tab, name] of [["home", "home-mobile-390x844.png"], ["profile", "profile-mobile-390x844.png"]]) {
    await open(page, `/?tab=${tab}`, MOBILE);
    const dims = await page.evaluate(() => ({
      viewport: window.innerWidth,
      doc: document.documentElement.scrollWidth,
    }));
    expect(dims.doc, `${tab} must not overflow horizontally`).toBeLessThanOrEqual(dims.viewport);
    await shot(page, name);
  }
});

test("a selected dataset does not leak into deep links for pages that ignore it", async ({ page }) => {
  // Ported from origin-lineage work: syncUrl carried `dataset` onto every tab,
  // so navigating away from Library produced a Resources/Settings deep link
  // pinned to a dataset those pages never read. Sharing that URL restored a
  // stale selection. Only Home/Discover/Library own a dataset.
  await open(page, "/?tab=library&dataset=gdelt_asia_daily_country_panel");
  await expect(page).toHaveURL(/dataset=gdelt_asia_daily_country_panel/);

  await page.getByRole("button", { name: "Resources", exact: true }).click();
  await expect(page).toHaveURL(/tab=resources/);
  await expect(page).not.toHaveURL(/dataset=/);

  await page.getByRole("button", { name: "Library", exact: true }).click();
  await expect(page).toHaveURL(/tab=library/);
});
