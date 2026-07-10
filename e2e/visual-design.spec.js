import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";
const EMAIL = "drkong@saturn.yzu.edu.tw";

async function navTo(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

async function openFirstLabDataset(page) {
  await navTo(page, "Drive");
  await page.getByRole("button", { name: "Lab", exact: true }).click();
  const row = page.locator(".rd-catalog-table tbody tr:has(.rd-file)").first();
  await row.waitFor({ timeout: 30_000 });
  await row.click();
  await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
  await page.getByRole("button", { name: "Overview" }).waitFor({ timeout: 20_000 });
}

async function waitForRegistryRows(page) {
  await page.waitForFunction(
    () => {
      const home = document.querySelectorAll(".rd-catalog-table tbody tr:not(.rd-skeleton-row) .rd-title");
      const lib = document.querySelectorAll(
        ".yzu-drive-table tbody tr .rd-title, .rd-catalog-table tbody tr .rd-title",
      );
      return home.length > 0 || lib.length > 0;
    },
    { timeout: 30_000 },
  );
}

async function openChatPanel(page) {
  await navTo(page, "Source");
  await expect(page.getByRole("heading", { name: /Source & compare/i })).toBeVisible();
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

test.describe("Visual design loop", () => {
  test.describe.configure({ mode: "serial", timeout: 180_000 });
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      localStorage.setItem("rd_recent_datasets", JSON.stringify([{ id: "coingecko_simple_price", at: Date.now() }]));
    });
    await page.reload();
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await waitForRegistryRows(page);
  });

  test("01 home — unified dark shell", async ({ page }) => {
    const railBg = await page.locator("aside.yzu-inspector").evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(railBg).not.toBe("rgb(255, 255, 255)");

    const heroFont = await page.locator(".rd-page-bar h1").first().evaluate((el) => getComputedStyle(el).fontFamily);
    expect(heroFont.length).toBeGreaterThan(0);

    await page.screenshot({ path: `${OUT}/visual-01-home.png`, fullPage: false });
  });

  test("02 home — stats populated", async ({ page }) => {
    await expect(page.locator(".rd-library-stats")).toContainText(/datasets/i);
    await expect(page.locator(".rd-catalog-table .rd-title").first()).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-02-home-loaded.png`, fullPage: false });
  });

  test("03 chat page — composer", async ({ page }) => {
    await openChatPanel(page);
    await expect(page.locator("aside .yzu-procure")).toHaveCount(0);
    await page.locator("main .yzu-composer textarea").fill("climate calibration panel");
    await page.screenshot({ path: `${OUT}/visual-03-rail-composer.png`, fullPage: false });
  });

  test("04 drive — catalog facets", async ({ page }) => {
    await navTo(page, "Drive");
    await expect(page.getByRole("heading", { name: "Drive", exact: true })).toBeVisible();
    await expect(page.locator(".rd-folder-tree")).toHaveCount(0);
    await waitForRegistryRows(page);
    await page.getByRole("button", { name: "Lab", exact: true }).click();
    await expect(page.getByRole("button", { name: "Research panels" })).toBeVisible();
    await expect(page.locator(".rd-catalog-table tbody tr").first()).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-04-library.png`, fullPage: false });
  });

  test("04b my uploads — personal space", async ({ page }) => {
    await navTo(page, "Drive");
    await page.getByRole("button", { name: "My uploads", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Drive", exact: true })).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-04b-folder-uploads.png`, fullPage: false });
  });

  test("05 dataset detail", async ({ page }) => {
    await waitForRegistryRows(page);
    await openFirstLabDataset(page);
    await expect(page.getByRole("button", { name: "Overview" })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".rd-dataset-nav button", { hasText: "Schema" })).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-05-dataset.png`, fullPage: false });
  });

  test("06 chat — candidate cards", async ({ page }) => {
    await signIn(page);
    await openChatPanel(page);
    await page.locator("main .yzu-composer textarea").fill("climate calibration ridge regression");
    await page.locator("main .yzu-composer button.primary").click();
    await page.waitForFunction(
      () => document.querySelectorAll("main .yzu-candidate").length > 0,
      { timeout: 90_000 },
    );
    await expect(page.locator("main .yzu-trust-pill").first()).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-06-chat-candidates.png`, fullPage: false });
  });

  test("07 compare — two picks + table", async ({ page }) => {
    await signIn(page);
    await openChatPanel(page);
    await page.locator("main .yzu-composer textarea").fill("climate calibration ridge regression");
    await page.locator("main .yzu-composer button.primary").click();
    await page.waitForFunction(() => document.querySelectorAll("main .yzu-candidate").length >= 2, { timeout: 90_000 });
    const toggles = page.locator("main .yzu-compare-toggle");
    await toggles.nth(0).click();
    await toggles.nth(1).click();
    await expect(page.getByRole("button", { name: "Compare" })).toBeVisible();
    await page.screenshot({ path: `${OUT}/visual-07a-compare-picks.png`, fullPage: false });
    await page.getByRole("button", { name: "Compare" }).click();
    await page.waitForFunction(
      () => {
        const tbl = document.querySelector("main .yzu-compare-table-wrap");
        const reply = document.querySelector("main .yzu-chat-rail article.assistant:last-of-type, main .yzu-chat article.assistant:last-of-type");
        return Boolean(tbl || (reply && /comparison/i.test(reply.textContent || "")));
      },
      { timeout: 90_000 },
    );
    await page.screenshot({ path: `${OUT}/visual-07-compare-table.png`, fullPage: false });
  });

  test("08 recommended + activity", async ({ page }) => {
    await navTo(page, "Discover");
    await page.getByRole("heading", { name: /^Discover$/ }).waitFor();
    await page.screenshot({ path: `${OUT}/visual-08-recommended.png`, fullPage: false });

    await navTo(page, "Pipeline");
    await page.getByRole("heading", { name: /^Activity$/ }).waitFor();
    await page.screenshot({ path: `${OUT}/visual-09-activity.png`, fullPage: false });
  });

  test("09 signed-in chat starters", async ({ page }) => {
    await signIn(page);
    await navTo(page, "Home");
    await openChatPanel(page);
    await expect(page.locator("main .yzu-advice-recs .yzu-chip, main .rd-action-list .rd-action-btn").first()).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${OUT}/visual-10-signed-in.png`, fullPage: false });
  });

  test("10 mobile layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await waitForRegistryRows(page);
    await page.screenshot({ path: `${OUT}/visual-11-mobile.png`, fullPage: true });
  });
});
