import { test, expect } from "@playwright/test";

const EMAIL = "drkong@saturn.yzu.edu.tw";
const OUT = "docs/status/generated";

async function signIn(page) {
  await page.getByRole("button", { name: /Sign in/i }).click();
  await page.getByPlaceholder("you@saturn.yzu.edu.tw").fill(EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
}

test("capture desk ui tour", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload();
  await page.getByRole("heading", { name: "Recent" }).waitFor();
  await page.getByRole("button", { name: "Browse Drive" }).waitFor();
  await page.screenshot({ path: `${OUT}/desk-ui-home-guest-desktop.png`, fullPage: true });

  await signIn(page);
  await page.getByText("Asst. Prof. Kong").first().waitFor();
  await page.screenshot({ path: `${OUT}/desk-ui-home-desktop.png`, fullPage: true });

  await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Drive/ }).first().click();
  await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
  await page.screenshot({ path: `${OUT}/desk-ui-library-desktop.png`, fullPage: true });

  await page.locator("aside.yzu-sidebar nav button").filter({ hasText: /^Source/ }).first().click();
  await page.getByPlaceholder("Describe what you need…").fill("Explain the TWSE listed firm daily prices dataset.");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.locator("article.assistant").last().filter({ hasNotText: "…" }).waitFor({ timeout: 90_000 });
  await page.screenshot({ path: `${OUT}/desk-ui-chat-reply-desktop.png`, fullPage: true });
});
