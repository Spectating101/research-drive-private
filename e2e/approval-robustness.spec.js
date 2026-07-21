import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("Research Drive approval feedback robustness", () => {
  test("failed approval returns to an actionable button and never claims success", async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await mockV2Api(page);
    await page.unroute("**/api/library/chat/stream");
    await page.unroute("**/api/library/chat");

    const approvalCandidate = (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "approval-failure-test",
          reply: "The collection job requires approval.",
          action: "queue",
          artifacts: {
            job: {
              id: "job-approval-fail",
              status: "pending_approval",
            },
          },
        }),
      });
    await page.route("**/api/library/chat/stream", approvalCandidate);
    await page.route("**/api/library/chat", approvalCandidate);

    let approvalRequests = 0;
    await page.route("**/library/jobs/job-approval-fail/approve", async (route) => {
      approvalRequests += 1;
      await new Promise((resolve) => setTimeout(resolve, 150));
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Approval service unavailable" }),
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("tab", { name: "Ask" }).click();
    await rail.getByTestId("ask-composer").fill("Queue a source that needs approval.");
    await rail.getByRole("button", { name: "Send" }).click();

    const approve = rail.getByRole("button", { name: "Approve job" });
    await expect(approve).toBeVisible();
    await approve.click();
    await expect(rail.getByRole("button", { name: /Approving/ })).toBeDisabled();

    const errorToast = page.locator(".rd-v2-toast.error");
    await expect(errorToast).toHaveText("Approval service unavailable");
    await expect(errorToast).toHaveAttribute("role", "alert");
    await expect(errorToast).toHaveAttribute("aria-live", "assertive");
    await expect(approve).toBeVisible();
    await expect(approve).toBeEnabled();
    await expect(rail).not.toContainText("Approval requested");

    expect(approvalRequests).toBe(1);
    expect(pageErrors).toEqual([]);
  });
});
