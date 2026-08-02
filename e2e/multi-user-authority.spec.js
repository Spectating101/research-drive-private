import { expect, test } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";


test("account menu names the authenticated workspace and role", async ({ page }) => {
  await mockV2Api(page);
  await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
  await waitForShell(page);

  await page.getByRole("button", { name: "Account" }).click();
  const menu = page.getByRole("menu", { name: "Account destinations" });
  await expect(menu).toContainText("Researcher One");
  await expect(menu).toContainText("methods-lab · admin");
});


test("viewer role receives a clear Ask boundary instead of active controls", async ({ page }) => {
  await mockV2Api(page);
  await page.route("**/library/desk/capabilities", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 2,
        authenticated: true,
        access: "viewer",
        principal: {
          id: "viewer-1",
          email: "viewer@example.test",
          display_name: "Library Viewer",
          role: "viewer",
          workspace_ids: ["methods-lab"],
          default_workspace_id: "methods-lab",
        },
        permissions: {
          view_research_data: true,
          view_faculty_profile: true,
          view_operations: false,
          use_ask: false,
          submit_collection: false,
          approve_jobs: false,
          manage_workspace: false,
        },
      }),
    }),
  );
  await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
  await page.getByRole("button", { name: /^Ask/ }).click();
  await expect(page.getByRole("note")).toContainText("Ask is not available for this role");
});
