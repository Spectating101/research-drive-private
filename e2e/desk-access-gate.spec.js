import { expect, test } from "@playwright/test";
import { mockV2Api } from "./fixtures/v2MockApi.js";

test("anonymous browser stays locked until a valid desk token is presented", async ({ page }) => {
  await mockV2Api(page);

  await page.route("**/library/desk/capabilities", (route) => {
    const token = route.request().headers()["x-desk-token"] || "";
    const authenticated = token === "review-token-for-test";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        authenticated,
        server_configured: true,
        access: authenticated ? "operator" : "locked",
        permissions: { view_research_data: authenticated, use_ask: authenticated },
      }),
    });
  });
  await page.route("**/library/desk/session", (route) => {
    const token = route.request().headers()["x-desk-token"] || "";
    return route.fulfill({
      status: token === "review-token-for-test" ? 200 : 403,
      contentType: "application/json",
      body: JSON.stringify(
        token === "review-token-for-test"
          ? { ok: true, authorized: true }
          : { ok: false, error: "Forbidden" },
      ),
    });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Research data stays inside the desk." })).toBeVisible();
  await expect(page.locator("aside.yzu-sidebar")).toHaveCount(0);
  await expect(page.getByText("faculty memory, credentials, jobs, and worker details")).toBeVisible();

  await page.getByLabel("Desk access token").fill("review-token-for-test");
  await page.getByRole("button", { name: "Connect" }).click();

  await expect(page.locator(".rd-v2-shell")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research data stays inside the desk." })).toHaveCount(0);
});
