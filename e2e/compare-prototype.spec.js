import { test } from "@playwright/test";

const OUT = "docs/status/generated";

test("capture faculty HTML screenshots (headless)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
  await page.screenshot({ path: `${OUT}/faculty-home.png`, fullPage: false });

  await page.locator("aside.yzu-inspector").screenshot({ path: `${OUT}/faculty-right-rail-os.png` });

  await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
  await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
  await page.screenshot({ path: `${OUT}/faculty-library.png`, fullPage: false });
});
