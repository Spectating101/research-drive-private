import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

/**
 * Discover E2E — Explore | History (authority-aligned intent).
 * Primary viewport 1920×1080.
 *
 * Product authority: docs/UI_PRODUCT_AUTHORITY.md
 * Slice program:     docs/UI_IMPLEMENTATION_PROGRAM.md
 * Classification:    docs/DISCOVER_E2E_AUTHORITY_AUDIT.md
 *
 * Historical Search|Activity anchor (docs/design/DISCOVER_LOOP_ANCHOR.md) is a redirect only.
 * Do not treat Activity-summary assertions as Slice 1 gates.
 * Every report must include git SHA + Vite root; discard contaminated runs.
 */
test.describe("v2 Discover loop anchor", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("suggested card commits search into SERP", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    const title = await page.getByTestId("discover-suggested-card").first().locator("strong").innerText();
    await page.getByTestId("discover-suggested-card").first().click();
    await expect(page.getByTestId("discover-empty")).toHaveCount(0);
    await expect(page.getByTestId("discover-search-input")).toHaveValue(title);
    await expect(page.locator(".rd-v2-discover-candidate").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-search-summary")).not.toContainText(/Checking|updating/i);
  });

  test("search status settles without stuck Checking", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator(".rd-v2-discover-search-summary")).toContainText(/\d+ result/, {
      timeout: 10_000,
    });
    await expect(page.locator(".rd-v2-discover-search-summary")).not.toContainText(/Checking|updating/i);
  });

  test("query is preserved when the Explore queue opens", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("TWSE");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE");
    await page.getByRole("button", { name: /Review queue/ }).click();
    await expect(page.getByTestId("discover-queue-strip")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE");
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".rd-v2-discover-candidate").first()).toBeVisible({ timeout: 10_000 });
  });

  test("Explore queue selection owns the rail", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator("aside.rd-v2-rail .rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" })).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole("button", { name: /Review queue/ }).click();
    const queue = page.getByTestId("discover-queue-strip");
    await expect(queue).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail .rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" })).toHaveCount(0);
    const row = page.getByTestId("discover-queue-row").first();
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("button", { name: /Approve collection/ })).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
  });

  test("header pending opens the Explore queue", async ({ page }) => {
    await page.getByTestId("header-pending-link").click();
    await expect(page).not.toHaveURL(/mode=(approvals|activity|history)/);
    const queue = page.getByTestId("discover-queue-strip");
    await expect(queue).toBeVisible();
    await expect(queue).toContainText("Needs your review");
  });

  test("Discover exposes Explore and History as stable modes", async ({ page }) => {
    const modes = page.getByRole("tablist", { name: "Discover mode" });
    await expect(modes.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(modes.getByRole("tab", { name: "History" })).toBeVisible();
    await expect(modes.getByRole("tab", { name: /Activity/ })).toHaveCount(0);
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    await modes.getByRole("tab", { name: "History" }).click();
    await expect(page).toHaveURL(/mode=history/);
    await expect(page.getByTestId("discover-history")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    // Legacy Activity URLs normalize to Explore rather than reviving a third mode.
    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("tab", { name: "Explore" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    await page.getByRole("tab", { name: "Explore" }).click();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();
    await expect(page).not.toHaveURL(/mode=(activity|history)/);
  });

  test("History shows the research trail and selected outcome in the rail", async ({ page }) => {
    await page.getByRole("tab", { name: "History" }).click();

    const history = page.getByTestId("discover-history");
    await expect(history).toContainText("Research trail");
    await expect(history).toContainText("TWSE governance");
    await expect(history.locator(".rd-v2-history-row").first()).toHaveAttribute("aria-pressed", "true");
    await history.getByRole("button", { name: /TWSE governance/ }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Procurement trail");
    await expect(rail).toContainText("TWSE governance");
  });

  test("committed Discover search is shareable and survives History round trip", async ({ page }) => {
    const search = page.getByTestId("discover-search-input");
    await search.fill("TWSE governance");
    await search.press("Enter");
    await expect(page).toHaveURL(/q=TWSE(\+|%20)governance/);

    await page.getByRole("tab", { name: "History" }).click();
    await page.getByRole("tab", { name: "Explore" }).click();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE governance");
  });

  // LEGACY EXPECTATION — superseded Activity dashboard.
  // See docs/DISCOVER_E2E_AUTHORITY_AUDIT.md §6. Not a Slice 1 acceptance gate.
  // Rewrite target: History lifecycle inbox and/or Explore queue strip + Detail.
  test("Activity summarizes actionable acquisition states", async ({ page }) => {
    await mockV2Api(page, {
      jobsBody: {
        jobs: [
          { id: "pending", status: "pending_approval", plan: { title: "MOPS statements" } },
          { id: "running", status: "running", progress: 64, plan: { title: "GDELT refresh" } },
          { id: "failed", status: "failed", plan: { title: "Daily public queue" } },
        ],
      },
    });
    await page.goto("/?tab=browse&mode=activity", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const summary = page.getByTestId("discover-activity-summary");
    await expect(summary).toContainText("Awaiting");
    await expect(summary).toContainText("Running");
    await expect(summary).toContainText("Queued");
    await expect(summary).toContainText("Failed 7 days");
    await expect(summary).toContainText("1");
  });

  test("dataset-driven Discover reveals compact working-from context", async ({ page }) => {
    await page.goto("/?tab=browse&dataset=gdelt_asia_daily_country_panel", {
      waitUntil: "domcontentloaded",
    });
    await waitForShell(page);

    const context = page.getByTestId("discover-research-context");
    await expect(context).toContainText("Working from");
    await expect(context).toContainText(/GDELT|panel|Index/i);
    await expect(context.locator(".rd-v2-discover-context-meta")).toBeVisible();
    await expect(context.locator(".rd-v2-research-evidence")).toHaveCount(0);
    await expect(page.getByTestId("discover-suggested")).toBeVisible();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Why this matters");
    await expect(rail).toContainText("Source confidence");
    await expect(rail).toContainText("Vault state");
    await expect(rail).toContainText("Next gap");
  });

  test("compact working-from context stays single-line dense at desktop widths", async ({ page }) => {
    for (const width of [1366, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/?tab=browse&dataset=gdelt_asia_daily_country_panel", {
        waitUntil: "domcontentloaded",
      });
      await waitForShell(page);

      const layout = await page.getByTestId("discover-research-context").evaluate((context) => {
        const title = context.querySelector(".rd-v2-discover-context-title");
        const meta = context.querySelector(".rd-v2-discover-context-meta");
        const box = context.getBoundingClientRect();
        return {
          height: box.height,
          hasEvidence: Boolean(context.querySelector(".rd-v2-research-evidence")),
          titleVisible: Boolean(title?.textContent?.trim()),
          metaVisible: Boolean(meta?.textContent?.trim()),
        };
      });

      expect(layout.hasEvidence).toBe(false);
      expect(layout.titleVisible).toBe(true);
      expect(layout.metaVisible).toBe(true);
      expect(layout.height).toBeLessThan(160);
    }
  });
});
