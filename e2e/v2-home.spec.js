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
    await expect(queue).toContainText("4 objects");
    await expect(queue.locator('[data-kind="approval"]')).toContainText("MOPS financial statements");
    await expect(queue.locator('[data-kind="approval"]')).toContainText("1 pending");
    await expect(queue.locator('[data-kind="procurement"]')).toContainText("Procurement in progress");
    await expect(queue.locator('[data-kind="procurement"]')).toContainText(/running/i);
    await expect(queue.locator('[data-kind="library"]')).toContainText("Faculty vault");
    await expect(queue.locator('[data-kind="discover"]')).toContainText("Find missing data");
    await expect(queue.getByRole("button", { name: /^Open / })).toHaveCount(4);
    await expect(queue.getByRole("button", { name: /^Ask about / })).toHaveCount(4);
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

  test("Open on approval attention selects the Resources job rail", async ({ page }) => {
    const queue = page.getByRole("region", { name: "Attention queue" });
    await queue.locator('[data-kind="approval"]').getByRole("button", { name: /^Open Approval/ }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Resources" })).toBeVisible();
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("MOPS financial statements");
    await expect(rail).toContainText("Job ID");
    await expect(rail).toContainText("job-pending-1");
    await expect(rail.getByRole("button", { name: "Approve job" })).toBeVisible();
  });

  test("Ask on approval attention sends grounded Home context", async ({ page }) => {
    const queue = page.getByRole("region", { name: "Attention queue" });
    await queue.locator('[data-kind="approval"]').getByRole("button", { name: /^Ask about Approval/ }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-rail-selection")).toHaveText("MOPS financial statements");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText("Home · MOPS financial statements");
    await expect(page.getByTestId("ask-messages")).toContainText("Review the pending procurement approval");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS financial statements");

    await rail.getByRole("tab", { name: "Detail" }).click();
    await expect(rail.getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Type");
    await expect(rail).toContainText("Approval");
    await expect(rail).toContainText("Review source, cost, destination");
  });

  test("home command surface shows Drive + HF + Ask promise", async ({ page }) => {
    const command = page.locator(".rd-v2-home-command");
    await expect(command).toContainText("Google Drive vault for the lab");
    await expect(command).toContainText("Hugging Face, DOI catalogs");
    await expect(command).toContainText("Ask the assistant");
  });

  test("desk lanes strip routes Library, Discover, and Ask", async ({ page }) => {
    const lanes = page.locator(".rd-v2-desk-lanes");
    await expect(lanes).toContainText("Library");
    await expect(lanes).toContainText("Discover");
    await expect(lanes).toContainText("Ask");
    await lanes.getByRole("button", { name: /Library/i }).click();
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Library" })).toBeVisible();
  });

  test("suggested asks render from faculty profile", async ({ page }) => {
    const asks = page.locator(".rd-v2-home-suggested");
    await expect(asks).toBeVisible();
    await expect(asks.getByRole("button").first()).toBeVisible();
  });
});
