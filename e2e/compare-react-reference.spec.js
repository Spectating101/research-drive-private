import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";
const REACT_DEV_URL = process.env.REACT_DESK_URL || "http://127.0.0.1:5178";
const PROD_URL = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";

test("reference comparison: React dev vs production build", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto(REACT_DEV_URL, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 45_000 });
  await page.screenshot({ path: `${OUT}/compare-react-reference-home.png`, fullPage: false });

  const reactAskInMain = await page.locator("main .rd-ask-card").count();
  const reactAskInRail = await page.locator("aside.yzu-inspector").count();
  const reactInspector = await page.locator("aside.yzu-inspector").count();
  expect(reactAskInMain).toBe(0);
  expect(reactAskInRail).toBe(1);
  expect(reactInspector).toBe(1);

  await page.goto(PROD_URL, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
  await page.screenshot({ path: `${OUT}/compare-prod-react-home.png`, fullPage: false });

  const prodAskInMain = await page.locator("main .rd-ask-card").count();
  const prodAskInRail = await page.locator("aside.yzu-inspector").count();
  expect(prodAskInMain).toBe(0);
  expect(prodAskInRail).toBe(1);

  await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Source/ }).first().click();
  await page.locator("main .yzu-procure.main").screenshot({ path: `${OUT}/compare-prod-rail.png` });
});

test("React reference: demo ask triggers live chat reply", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(REACT_DEV_URL, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 45_000 });

  await page.getByRole("tab", { name: "Assistant" }).click();
  await page.locator("aside .yzu-composer textarea").fill("what taiwan equity panels do we have?");
  await page.locator("aside .yzu-composer button.primary").click();
  await page.waitForFunction(
    () => {
      const el = document.querySelector("aside .yzu-chat-card article.assistant");
      return el && el.textContent && el.textContent.length > 40 && !el.textContent.includes("…");
    },
    { timeout: 90_000 },
  );
  await page.screenshot({ path: `${OUT}/compare-react-after-ask.png`, fullPage: false });
});

test("Production React: rail chat triggers live reply", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(PROD_URL, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });

  await page.getByRole("tab", { name: "Assistant" }).click();
  await page.locator("aside .yzu-advice-recs .yzu-chip").first().click();
  await page.waitForFunction(
    () => {
      const el = document.querySelector("aside .yzu-chat-card article.assistant");
      return el && el.textContent && el.textContent.length > 40 && !el.textContent.includes("…");
    },
    { timeout: 90_000 },
  );
  await page.screenshot({ path: `${OUT}/compare-prod-after-ask.png`, fullPage: false });
});
