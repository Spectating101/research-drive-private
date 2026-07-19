import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("v2 Library directory", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=library", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Lab root renders as a folder-first directory", async ({ page }) => {
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Library" })).toBeVisible();
    const estate = page.getByTestId("library-estate-browser");
    await expect(estate).toContainText("All holdings");
    await expect(estate).toContainText(/3 assets/);
    await expect(estate).toContainText(/3 ready to use/);
    await expect(page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "Research panels" })).toBeVisible();
    await expect(page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "Connected sources" })).toBeVisible();
    await expect(page.locator(".rd-v2-library-pathbar")).toHaveCount(0);
    await expect(page.locator(".rd-v2-rail-selection")).toHaveText("Lab");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("In this library");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Add data");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Branch actions");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Upload here");
  });

  test("folders drill down to datasets and keep the rail as the selection anchor", async ({ page }) => {
    await page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "Research panels" }).click();
    await expect(page.getByTestId("library-estate-browser")).toContainText("Research panels");
    await expect(page.locator(".rd-v2-rail-selection")).toHaveText("Research panels");

    await page.locator('[data-testid="library-collection"][data-kind="folder"]', { hasText: "gdelt" }).click();
    await expect(page.locator('.rd-v2-library-asset[data-kind="dataset"]')).toHaveCount(1);
    await expect(page.locator(".rd-v2-rail-selection")).toHaveText("gdelt");
    await page.locator('.rd-v2-library-asset[data-kind="dataset"]', { hasText: "Asia daily news-risk panel" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Asia daily news-risk panel");
    await expect(rail).toContainText("Can I use this?");
    await expect(rail).toContainText("Query ready");
    await expect(rail).toContainText("Useful for");
    await expect(rail).toContainText("Coverage & grain");
    await expect(rail).toContainText("Join keys");
    await expect(rail.getByRole("button", { name: "Preview rows" })).toBeVisible();
    await expect(page.getByTestId("library-estate-browser")).not.toContainText("Selected");
  });

  test("New menu routes upload intake through the rail", async ({ page }) => {
    await page.getByRole("button", { name: "Open new library item menu" }).click();
    await expect(page.getByRole("menu", { name: "New library item" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "New folder" })).toBeDisabled();

    await page.getByRole("menuitem", { name: "Upload file..." }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(page.getByRole("dialog", { name: "Upload files to library" })).toHaveCount(0);
    await expect(rail).toContainText("Upload files");
    await expect(rail).toContainText("Destination");
    await expect(rail).toContainText("Lab");
    await expect(rail.getByRole("button", { name: "Send to Ask" })).toBeDisabled();

    await rail.locator('input[type="file"]').setInputFiles({
      name: "faculty-panel.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("date,value\n2026-01-01,1\n"),
    });
    await expect(rail).toContainText("faculty-panel.csv");
    await rail.getByRole("button", { name: "Send to Ask" }).click();
    await expect(page.locator(".rd-v2-rail-toggle button.on", { hasText: "Ask" })).toBeVisible();
    await expect(page.getByTestId("ask-messages")).toContainText("Upload files to Lab");
    await expect(page.getByTestId("ask-messages")).toContainText("faculty-panel.csv");
  });

  test("URL / DOI intake waits for a target before sending to Ask", async ({ page }) => {
    await page.getByRole("button", { name: "Open new library item menu" }).click();
    await page.getByRole("menuitem", { name: "Add URL / DOI..." }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(page.getByRole("dialog", { name: "Add URL or DOI to library" })).toHaveCount(0);
    await expect(rail).toContainText("Add URL / DOI");
    await expect(rail.getByRole("button", { name: "Send to Ask" })).toBeDisabled();

    await rail.locator("#rd-v2-rail-url-input").fill("https://doi.org/10.1234/example");
    await rail.getByRole("button", { name: "Send to Ask" }).click();
    await expect(page.locator(".rd-v2-rail-toggle button.on", { hasText: "Ask" })).toBeVisible();
    await expect(page.getByTestId("ask-messages")).toContainText("https://doi.org/10.1234/example");
  });
});

test.describe("v2 Library navigation", () => {
  test("entering Library from Home lands on the branch rail", async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Asia daily news-risk panel");

    await page.locator("aside.yzu-sidebar").getByRole("button", { name: "Library", exact: true }).click();
    await expect(page.locator(".rd-v2-rail-selection")).toHaveText("Lab");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("In this library");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Add data");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Upload here");
  });
});
