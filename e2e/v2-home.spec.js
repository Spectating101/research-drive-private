import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("v2 Home attention", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("attention queue shows actionable work objects", async ({ page }) => {
    const queue = page.getByRole("region", { name: "Attention queue" });
    await expect(queue).toContainText("3 of 4");
    await expect(queue.locator('[data-kind="approval"]')).toContainText("MOPS financial statements");
    await expect(queue.locator('[data-kind="approval"]')).toContainText("1 pending");
    await expect(queue.locator('[data-kind="procurement"]')).toContainText("Procurement in progress");
    await expect(queue.locator('[data-kind="procurement"]')).toContainText(/running/i);
    await expect(queue.locator('[data-kind="library"]')).toContainText("Faculty vault");
    await expect(queue.locator('[data-kind="discover"]')).toHaveCount(0);
    await expect(queue.getByRole("button", { name: /^Open / })).toHaveCount(3);
    await expect(queue.getByRole("button", { name: /^Ask about / })).toHaveCount(0);
  });

  test("Open on Library attention lands on branch rail", async ({ page }) => {
    const queue = page.getByRole("region", { name: "Attention queue" });
    await queue.locator('[data-kind="library"]').getByRole("button", { name: /^Open Library/ }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Library" })).toBeVisible();
    await expect(page.locator(".rd-v2-library-pathbar")).toContainText("Lab root");
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("Lab root");
    await expect(rail).toContainText("Upload here");
  });

  test("Open on approval attention lands on Discover Review queue", async ({ page }) => {
    const queue = page.getByRole("region", { name: "Attention queue" });
    await queue.locator('[data-kind="approval"]').getByRole("button", { name: /^Open Approval/ }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(page).toHaveURL(/mode=(approvals|activity)/);
    await expect(page.getByTestId("discover-activity")).toBeVisible();
    await expect(page.getByTestId("discover-activity")).toContainText("Review queue");
    await expect(rail.locator(".rd-v2-rail-selection")).toContainText("MOPS financial statements");
    await expect(rail.getByTestId("procurement-decision-card")).toBeVisible();
    await expect(rail).toContainText("job-pending-1");
    await expect(rail.getByRole("button", { name: "Approve collection" })).toBeVisible();
  });

  test("home continue card routes to Library and Preview", async ({ page }) => {
    const cont = page.getByRole("region", { name: "Continue" });
    await expect(cont).toBeVisible();
    await expect(cont.getByRole("button", { name: "Open in Library" })).toBeVisible();
    await expect(cont.getByRole("button", { name: "Preview rows" })).toBeVisible();
    const brief = page.getByRole("region", { name: "Research Drive brief" });
    await expect(brief).toBeVisible();
    await expect(brief).toContainText("Find");
    await expect(brief).toContainText("Verify");
    await expect(brief).toContainText("Acquire");
    await expect(brief).toContainText("Synthesize");
    await expect(page.getByRole("region", { name: "Recent datasets" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Suggested searches" })).toBeVisible();

    await cont.getByRole("button", { name: "Open in Library" }).click();
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Library" })).toBeVisible();
  });

  test("mobile Home reveals current work in the first viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const brief = page.getByRole("region", { name: "Research Drive brief" });
    const attention = page.getByRole("region", { name: "Attention queue" });
    expect(await brief.evaluate((element) => element.clientHeight)).toBeLessThan(210);
    const attentionTop = await attention.evaluate((element) => element.getBoundingClientRect().top);
    expect(attentionTop).toBeLessThan(844);
  });
});
