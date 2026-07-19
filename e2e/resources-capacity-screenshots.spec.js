import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = "docs/screenshots-review/resources-capacity";

async function setup(page, viewport) {
  await page.setViewportSize(viewport);
  await mockV2Api(page);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await expect(page.getByRole("region", { name: "Capacity and access" })).toBeVisible();
}

test("render Resources capacity, routes, activity, and mobile review states", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });

  await setup(page, { width: 1440, height: 900 });
  await page.screenshot({ path: `${OUT}/01-desktop-overview.png`, fullPage: false });

  await page.locator(".rd-v2-res-routes > summary").click();
  await expect(page.locator('.rd-v2-res-inventory-row[data-kind="source"]')).toHaveCount(5);
  await page.screenshot({ path: `${OUT}/02-desktop-routes-open.png`, fullPage: false });

  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Run log" })).toBeVisible();
  await page.screenshot({ path: `${OUT}/03-desktop-activity.png`, fullPage: false });

  await setup(page, { width: 390, height: 1200 });
  await page.screenshot({ path: `${OUT}/04-mobile-overview.png`, fullPage: false });
});
