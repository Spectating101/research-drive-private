/**
 * Legacy Research Drive UI — guards old src/main.jsx until VITE_UI_V2 cutover.
 * @see docs/RESEARCH_DRIVE_UI_CONTRACT.md (legacy)
 * @see docs/RESEARCH_DRIVE_UI_CANON.md (new work — use e2e/ui-v2.spec.js when added)
 */
import { test, expect } from "@playwright/test";

async function navTo(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

async function waitForHome(page) {
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
  await page.getByRole("heading", { name: "Recent" }).waitFor({ timeout: 30_000 });
}

async function firstDataRow(page, root = "main") {
  let row = page.locator(`${root} .rd-catalog-table tbody tr`).filter({ has: page.locator(".rd-title") }).first();
  const homeVisible = await row.isVisible().catch(() => false);
  if (!homeVisible) {
    await navTo(page, "Drive");
    await page.getByRole("heading", { name: "Drive", exact: true }).waitFor({ timeout: 20_000 });
    row = page.locator("main .rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first();
  }
  await row.waitFor({ timeout: 20_000 });
  return row;
}

test.describe("UI contract — shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForHome(page);
  });

  test("library views use three-column shell with inspector", async ({ page }) => {
    await expect(page.locator(".yzu-shell")).toBeVisible();
    await expect(page.locator("aside.yzu-sidebar")).toBeVisible();
    await expect(page.locator("aside.yzu-inspector")).toBeVisible();
    await expect(page.locator(".rd-inspector-idle, .rd-inspector-compact")).toBeVisible();
  });

  test("sidebar primary nav — Home, Drive, Source, Pipeline", async ({ page }) => {
    await expect(page.locator("aside.yzu-sidebar button").filter({ hasText: /^Home$/ })).toBeVisible();
    await expect(page.locator("aside.yzu-sidebar button").filter({ hasText: /^Drive$/ })).toBeVisible();
    await expect(page.locator("aside.yzu-sidebar button").filter({ hasText: /^Source$/ })).toBeVisible();
    await expect(page.locator("aside.yzu-sidebar button").filter({ hasText: /^Pipeline$/ })).toBeVisible();
  });

  test("Source nav has no badge; Pipeline nav exists", async ({ page }) => {
    const sourceNav = page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Source/ });
    await expect(sourceNav).toBeVisible();
    await expect(sourceNav.locator("small")).toHaveCount(0);
    await expect(page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Pipeline/ })).toBeVisible();
  });
});

test.describe("UI contract — Home", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForHome(page);
  });

  test("GDrive-style Home: Recent + drive-parity table", async ({ page }) => {
    await expect(page.locator(".rd-home-drive")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
    await expect(page.locator(".rd-home-drive .rd-catalog-table")).toBeVisible();
  });

  test("Home anti-patterns absent", async ({ page }) => {
    await expect(page.getByText("What the lab holds")).toHaveCount(0);
    await expect(page.getByText(/INTERNAL · HOLDINGS/i)).toHaveCount(0);
    await expect(page.getByText("Missing data?")).toHaveCount(0);
    await expect(page.locator(".rd-home-surface, .rd-l1-panel")).toHaveCount(0);
    await expect(page.locator("main .yzu-procure.main")).toHaveCount(0);
  });

  test("inspector idle Details without procure upsell", async ({ page }) => {
    await expect(page.locator(".rd-inspector-idle h2")).toHaveText("Details");
    await expect(page.locator(".rd-inspector-idle")).not.toContainText("Discover");
    await expect(page.locator(".rd-inspector-idle")).not.toContainText("Chat");
  });

  test("inspector Assistant tab is scoped and opt-in", async ({ page }) => {
    const rail = page.locator("aside.yzu-inspector");
    await expect(rail.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
    await rail.getByRole("tab", { name: "Assistant" }).click();
    await expect(rail.getByRole("tab", { name: "Assistant" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-inspector-chat-panel .yzu-procure.card")).toBeVisible();
    await expect(rail.locator(".rd-inspector-chat-panel .yzu-composer textarea")).toBeVisible();
    await expect(page.locator("main .yzu-procure.main")).toHaveCount(0);
  });

  test("inspector Assistant sends chat without leaving library view", async ({ page }) => {
    await page.route("**/library/chat/stream", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/x-ndjson; charset=utf-8",
        body: [
          JSON.stringify({
            type: "complete",
            result: {
              session_id: "rail-test-session",
              action: "composer",
              reply: "Rail assistant response from scoped chat.",
              candidates: [],
              suggested_prompts: [],
              next_steps: [],
              artifacts: { action: "composer" },
            },
          }),
        ].join("\n") + "\n",
      });
    });
    const rail = page.locator("aside.yzu-inspector");
    await rail.getByRole("tab", { name: "Assistant" }).click();
    await rail.locator(".rd-inspector-chat-panel .yzu-composer textarea").fill("rail integration test");
    await rail.locator(".rd-inspector-chat-panel .yzu-composer button.primary").click();
    await expect(rail.locator("article.assistant").last()).toContainText("Rail assistant response");
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  });

  test("selection opens Details in rail", async ({ page }) => {
    const row = await firstDataRow(page, ".rd-home-drive");
    await row.click();
    await expect(page.locator(".rd-inspector-compact h2")).toBeVisible();
    await expect(page.getByRole("toolbar", { name: "Selected dataset" })).toBeVisible();
  });
});

test.describe("UI contract — Drive", () => {
  test("scope chips and inspector", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await navTo(page, "Drive");
    await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
    await expect(page.getByRole("button", { name: "All", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Lab", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "My uploads", exact: true })).toBeVisible();
    await expect(page.locator(".rd-folder-tree")).toHaveCount(0);
    await expect(page.locator("aside.yzu-inspector")).toBeVisible();
    await expect(page.locator("main .yzu-procure.main")).toHaveCount(0);
  });
});

test.describe("UI contract — procure surfaces", () => {
  test("Discover: no inspector, card grid contract", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await navTo(page, "Discover");
    await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
    await expect(page.locator("aside.yzu-inspector")).toHaveCount(0);
    await expect(page.locator(".yzu-shell")).toHaveClass(/no-inspector/);
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-card, .rd-discover-empty, .rd-discover-skeleton"),
      { timeout: 45_000 },
    );
    await expect(page.locator(".rd-result-row")).toHaveCount(0);
  });

  test("Browse: drill-in from Discover without inspector", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await navTo(page, "Discover");
    await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
    await page.waitForFunction(
      () => !document.body.textContent?.includes("Loading recommendations"),
      { timeout: 45_000 },
    );
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-card") || document.querySelector(".rd-discover-empty"),
      { timeout: 45_000 },
    );
    const card = page.locator(".rd-discover-card").first();
    test.skip((await card.count()) === 0, "Discover catalog empty — API may be unavailable");
    await card.getByRole("button", { name: "Browse" }).click();
    await expect(page.locator(".rd-browse-surface")).toBeVisible();
    await expect(page.locator("aside.yzu-inspector")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Collect" })).toBeVisible();
  });

  test("Chat: full-page procure, no inspector", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await navTo(page, "Source");
    await page.getByRole("heading", { name: /Source & compare/i }).waitFor();
    await expect(page.locator("main .yzu-procure.main")).toBeVisible();
    await expect(page.locator("aside.yzu-inspector")).toHaveCount(0);
    await expect(page.locator("aside .yzu-procure")).toHaveCount(0);
  });

  test("Cluster and Activity: no inspector", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await navTo(page, "Cluster");
    await page.getByRole("heading", { name: /^Cluster$/ }).waitFor();
    await expect(page.locator("aside.yzu-inspector")).toHaveCount(0);

    await navTo(page, "Pipeline");
    await page.getByRole("heading", { name: /^Activity$/ }).waitFor();
    await expect(page.getByText("Procurement dashboard")).toHaveCount(0);
    await expect(page.locator("aside.yzu-inspector")).toHaveCount(0);
  });
});
