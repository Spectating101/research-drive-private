import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

/**
 * Discover Loop Anchor gates — primary viewport 1920×1080.
 * See docs/design/DISCOVER_LOOP_ANCHOR.md
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

  test("query is preserved across Search and Review queue", async ({ page }) => {
    await page.getByTestId("discover-search-input").fill("TWSE");
    await page.getByTestId("discover-search-input").press("Enter");
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE");
    await page.getByRole("button", { name: /Review queue/ }).click();
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE");
    await page.getByRole("tab", { name: "Search" }).click();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE");
    await expect(page.locator(".rd-v2-discover-candidate").first()).toBeVisible({ timeout: 10_000 });
  });

  test("Activity job selection owns the rail", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator("aside.rd-v2-rail .rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" })).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole("button", { name: /Review queue/ }).click();
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    // Stale Search candidate must not remain — sticky Add to lab goes away.
    await expect(page.locator("aside.rd-v2-rail .rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" })).toHaveCount(0);
    const row = page.getByTestId("discover-activity-row").first();
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("button", { name: /Approve collection/ })).toBeVisible();
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
  });

  test("header pending opens Discover Activity awaiting", async ({ page }) => {
    await page.getByTestId("header-pending-link").click();
    await expect(page).toHaveURL(/mode=(approvals|activity)/);
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-activity")).toContainText("Review queue");
    await expect(page.getByTestId("discover-activity")).not.toContainText(/GiB|Ask usage|REMOTE TABLES/i);
    await expect(page.getByTestId("discover-activity-filters").getByRole("button", { name: /Awaiting/ })).toHaveClass(
      /on/,
    );
  });

  test("Discover exposes Search Activity and History as stable modes", async ({ page }) => {
    const modes = page.getByRole("tablist", { name: "Discover mode" });
    await expect(modes.getByRole("tab", { name: "Search" })).toHaveAttribute("aria-selected", "true");
    await expect(modes.getByRole("tab", { name: /Activity/ })).toBeVisible();
    await expect(modes.getByRole("tab", { name: "History" })).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    await modes.getByRole("tab", { name: "History" }).click();
    await expect(page).toHaveURL(/mode=history/);
    await expect(page.getByTestId("discover-history")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    await modes.getByRole("tab", { name: /Activity/ }).click();
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-search-input")).toBeVisible();

    await modes.getByRole("tab", { name: "Search" }).click();
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
    await page.getByRole("tab", { name: "Search" }).click();
    await expect(page.getByTestId("discover-search-input")).toHaveValue("TWSE governance");
  });

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

  test("dataset-driven Discover reveals the research operating loop", async ({ page }) => {
    await page.goto("/?tab=browse&dataset=gdelt_asia_daily_country_panel", {
      waitUntil: "domcontentloaded",
    });
    await waitForShell(page);

    const context = page.getByTestId("discover-research-context");
    await expect(context).toContainText("Research context");
    await expect(context).toContainText("Find");
    await expect(context).toContainText("Verify");
    await expect(context).toContainText("Acquire");
    await expect(context).toContainText("Synthesize");
    await expect(context).toContainText("Evidence and coverage");

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Why this matters");
    await expect(rail).toContainText("Source confidence");
    await expect(rail).toContainText("Vault state");
    await expect(rail).toContainText("Next gap");
  });

  test("research context owns its column backgrounds without clipping at desktop widths", async ({ page }) => {
    for (const width of [1366, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/?tab=browse&dataset=gdelt_asia_daily_country_panel", {
        waitUntil: "domcontentloaded",
      });
      await waitForShell(page);

      const layout = await page.getByTestId("discover-research-context").evaluate((context) => {
        const main = context.querySelector(".rd-v2-discover-context-main");
        const heading = main.querySelector("h2");
        const contextStyle = getComputedStyle(context);
        const mainStyle = getComputedStyle(main);
        const headingRect = heading.getBoundingClientRect();
        const mainRect = main.getBoundingClientRect();
        const evidenceValues = [...context.querySelectorAll(".rd-v2-research-evidence dd")];
        return {
          gap: contextStyle.columnGap,
          paddingTop: contextStyle.paddingTop,
          paddingBottom: contextStyle.paddingBottom,
          backgroundImage: contextStyle.backgroundImage,
          mainBackground: mainStyle.backgroundColor,
          headingInsideMain: headingRect.right <= mainRect.right + 0.5,
          headingOverflow: heading.scrollWidth - heading.clientWidth,
          evidenceValuesUsable: evidenceValues.every(
            (value) => value.clientWidth >= 50 && value.scrollWidth <= value.clientWidth + 1,
          ),
        };
      });

      expect(layout.gap).toBe("0px");
      expect(layout.paddingTop).toBe("0px");
      expect(layout.paddingBottom).toBe("0px");
      expect(layout.backgroundImage).toBe("none");
      expect(layout.mainBackground).toBe("rgb(16, 42, 67)");
      expect(layout.headingInsideMain).toBe(true);
      expect(layout.headingOverflow).toBeLessThanOrEqual(0);
      expect(layout.evidenceValuesUsable).toBe(true);
    }
  });
});
