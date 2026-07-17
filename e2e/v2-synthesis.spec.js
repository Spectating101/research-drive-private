import { mkdirSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const renderDir = "artifacts/synthesis-renders";

async function capture(page, name) {
  mkdirSync(renderDir, { recursive: true });
  await page.screenshot({ path: `${renderDir}/${name}.png`, fullPage: true });
}

test.describe("v2 Synthesis S-04", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("opens on one AI recommendation with integrated Ask context", async ({ page }) => {
    const recommendation = page.getByTestId("synthesis-recommendation");
    await expect(page.getByTestId("synthesis-studio")).toBeVisible();
    await expect(recommendation).toContainText("Composite weekly attention index");
    await expect(recommendation.getByText("Google Trends", { exact: true })).toBeVisible();
    await expect(recommendation.getByText("GDELT news", { exact: true })).toBeVisible();
    await expect(page.getByText("AI interpretation", { exact: true })).toBeVisible();
    await expect(recommendation.getByRole("button", { name: "Accept & design method" })).toBeVisible();
    await capture(page, "01-explore-desktop");
  });

  test("moves through design, preview, build, and registration", async ({ page }) => {
    await page.getByTestId("synthesis-recommendation").getByRole("button", { name: "Accept & design method" }).click();
    await expect(page.getByTestId("synthesis-design-state")).toContainText("One methodological decision remains");
    await capture(page, "02-design-desktop");

    await page.getByRole("button", { name: "Accept & test" }).click();
    await expect(page.getByTestId("synthesis-test-state")).toContainText("3,120");
    await capture(page, "03-test-desktop");

    await page.getByRole("button", { name: "Accept warning & request build" }).click();
    await expect(page.getByTestId("synthesis-build-state")).toBeVisible();
    await capture(page, "04-build-desktop");

    await expect(page.getByTestId("synthesis-registered-state")).toBeVisible({ timeout: 7000 });
    await expect(page.getByTestId("synthesis-registered-state")).toContainText("mft_s04_0726");
    await expect(page.getByRole("button", { name: "Open in Library" })).toBeVisible();
    await capture(page, "05-registered-desktop");
  });

  test("keeps alternative constructions secondary", async ({ page }) => {
    await page.getByTestId("synthesis-recommendation").getByRole("button", { name: "Compare alternatives" }).click();
    const dialog = page.locator(".s04-overlay");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("News-visibility index");
    await expect(dialog).toContainText("Event-attention panel");
    await capture(page, "06-alternatives-desktop");
    await dialog.getByRole("button", { name: "Keep recommended construction" }).click();
    await expect(dialog).toBeHidden();
  });

  test("opens the shared Ask rail from Synthesis context", async ({ page }) => {
    await page.getByRole("button", { name: "Why is GDELT validation?" }).click();
    await expect(page.locator("aside.rd-v2-rail")).toBeVisible();
    await expect(page.locator(".s04-ask")).toBeHidden();
    await capture(page, "07-shared-ask-desktop");
  });

  test("supports explicit failure and retry", async ({ page }) => {
    await page.goto("/?tab=synthesis&synthesis_state=build", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByRole("button", { name: "Exercise failure state" }).click();
    await expect(page.getByTestId("synthesis-failed-state")).toContainText(/no Library asset was created/i);
    await capture(page, "08-failure-desktop");
    await page.getByRole("button", { name: "Retry build" }).click();
    await expect(page.getByTestId("synthesis-registered-state")).toBeVisible({ timeout: 7000 });
  });

  test("mobile keeps the primary workflow readable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("synthesis-recommendation")).toBeVisible();
    await expect(page.getByTestId("synthesis-recommendation").getByRole("button", { name: "Accept & design method" })).toBeVisible();
    await expect(page.locator(".s04-ask")).toBeVisible();
    await expect(page.locator(".s04-shell")).not.toHaveCSS("overflow-x", "scroll");
    await capture(page, "09-explore-mobile");
  });
});
