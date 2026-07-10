import { test, expect } from "@playwright/test";

const EMAIL = "drkong@saturn.yzu.edu.tw";
const OUT = "docs/status/generated";

async function navTo(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

async function waitForRegistryRows(page) {
  await page.waitForFunction(
    () => document.querySelectorAll(
      ".rd-home-quick-chips button, .rd-library-table .rd-title, .yzu-drive-table tbody .rd-title, .rd-catalog-table tbody .rd-title",
    ).length > 0,
    { timeout: 30_000 },
  );
}

async function signIn(page) {
  await page.locator(".yzu-account-btn").click();
  await page.getByPlaceholder("you@saturn.yzu.edu.tw").fill(EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForFunction(
    () => {
      const strong = document.querySelector(".yzu-account-copy strong");
      return strong && !/sign in/i.test(strong.textContent || "");
    },
    { timeout: 25_000 },
  );
}

test("full desk tour for user review", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("http://127.0.0.1:8765/");
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload();
  await waitForRegistryRows(page);

  await page.screenshot({ path: `${OUT}/tour-01-home-guest.png`, fullPage: false });

  await signIn(page);
  await page.screenshot({ path: `${OUT}/tour-02-home-signed-in.png`, fullPage: false });

  await navTo(page, "Drive");
  await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
  await page.getByRole("button", { name: "Lab", exact: true }).click();
  await waitForRegistryRows(page);
  await page.screenshot({ path: `${OUT}/tour-03-library.png`, fullPage: false });

  const browseAll = page.getByRole("button", { name: /Browse all/ });
  if (await browseAll.count()) await browseAll.click();
  const panelsFilter = page.getByRole("button", { name: "Research panels" });
  if (await panelsFilter.count()) await panelsFilter.click();
  const fileRow = page.locator(".rd-catalog-table tbody tr:has(.rd-file)").first();
  await fileRow.click();
  await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
  await expect(page.getByRole("button", { name: "Overview" })).toBeVisible();
  await page.screenshot({ path: `${OUT}/tour-04-dataset-overview.png`, fullPage: false });

  await page.locator("main").getByRole("button", { name: "Preview", exact: true }).click();
  await page.getByRole("heading", { name: "Preview" }).waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/tour-05-dataset-preview.png`, fullPage: false });

  await page.getByRole("button", { name: "Schema" }).click();
  await page.screenshot({ path: `${OUT}/tour-06-dataset-schema.png`, fullPage: false });

  await navTo(page, "Discover");
  await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
  await expect(page.locator(".rd-discover-starters .rd-chip-starter")).toHaveCount(10);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${OUT}/tour-07-discover.png`, fullPage: false });

  await navTo(page, "Pipeline");
  await page.getByRole("heading", { name: /^Activity$/ }).waitFor();
  await page.screenshot({ path: `${OUT}/tour-08-activity.png`, fullPage: false });

  await navTo(page, "Home");
  await page.getByRole("tab", { name: "Assistant" }).click();
  await page.locator("aside .yzu-advice-recs .yzu-chip").first().click();
  await page.locator("aside article.assistant").last().filter({ hasNotText: "…" }).waitFor({ timeout: 90_000 });
  await page.screenshot({ path: `${OUT}/tour-09-chat-reply.png`, fullPage: false });

  await expect(
    page.locator("aside .yzu-candidates, aside .yzu-next-steps, aside .yzu-chat-rail article.assistant").first(),
  ).toBeVisible();
});
