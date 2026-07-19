/**
 * Discover composition visual authority.
 * The selected candidate must remain in Explore while Detail and Ask retain context.
 */
import { test, expect } from "@playwright/test";
import { MOCK_DISCOVER_HIT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-composition";
fs.mkdirSync(OUT, { recursive: true });

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

async function openSelectedCandidate(page) {
  await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.locator(".rd-v2-search-pill input").fill("mops");
  await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
  await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
  await expect(page.locator(".rd-v2-discover-candidate.selected")).toHaveCount(1);
}

test.describe("Discover composition screenshots", () => {
  test("Explore remains visible beside Detail and Ask", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSelectedCandidate(page);

    const rail = page.locator("aside.rd-v2-rail");
    const detail = rail.getByTestId("discover-eval-surface");
    await expect(detail).toContainText("Can I use this?");
    await expect(detail).toContainText("Still unknown");
    await shot(page, "01-desktop-explore-detail");

    await page.getByTestId("discover-eval-actions").getByRole("button", { name: "Probe source" }).click();
    await expect(detail.locator(".rd-v2-eval-verified")).toBeVisible();
    await shot(page, "02-desktop-explore-probed-detail");

    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByTestId("ask-messages")).toContainText("Selected candidate stays in context");
    await shot(page, "03-desktop-explore-ask");

    await page.setViewportSize({ width: 900, height: 1200 });
    await rail.getByRole("tab", { name: "Detail" }).click();
    await expect(detail).toBeVisible();
    await shot(page, "04-tablet-explore-detail");

    await page.setViewportSize({ width: 390, height: 1200 });
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(rail).toHaveClass(/rd-v2-rail-collapsed/);
    await rail.getByRole("button", { name: /Show Detail/ }).click();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail).not.toHaveClass(/rd-v2-rail-collapsed/);
    await shot(page, "05-mobile-explore-ask");
  });
});
