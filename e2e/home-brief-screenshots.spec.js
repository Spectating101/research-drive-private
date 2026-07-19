import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = "docs/screenshots-review/home-brief";

async function setup(page, viewport) {
  await page.setViewportSize(viewport);
  await mockV2Api(page);
  await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await expect(page.getByTestId("home-continue")).toBeVisible();
}

test("render Home desktop and mobile review states", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });

  await setup(page, { width: 1440, height: 900 });
  await page.screenshot({ path: `${OUT}/01-desktop-current.png`, fullPage: false });

  await setup(page, { width: 390, height: 1200 });
  await page.screenshot({ path: `${OUT}/02-mobile-current.png`, fullPage: false });
});
