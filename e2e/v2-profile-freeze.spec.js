/**
 * Profile freeze showcase — asserts organic Memory/Works/Lab + DETAIL rail.
 * Run: TMPDIR=$PWD/.tmp-pw npx playwright test e2e/v2-profile-freeze.spec.js --retries=0
 */
import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "../docs/status/generated/profile-freeze-showcase.png");

test.describe("Profile freeze showcase", () => {
  test("Memory Works Lab and Detail rail match freeze", async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.removeItem("procure_user_email");
      } catch {
        /* ignore */
      }
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".rd-v2-profile-name")).not.toHaveText("Research profile", { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
    await expect(page.getByText("Saved research context")).toBeVisible();

    const memory = page.getByTestId("profile-memory");
    await expect(memory).toBeVisible();
    await expect(memory.locator(".rd-v2-profile-memory-card").first()).toContainText(/Asset Pricing|FinTech|Finance/i);
    await expect(memory).toContainText(/Current:/i);
    await expect(memory).toContainText(/Also:/i);
    await expect(memory).toContainText(/Methods:/i);

    const works = page.getByTestId("profile-works");
    await expect(works).toBeVisible();
    await expect(works).toContainText(/indexed/i);

    const lab = page.getByTestId("profile-lab");
    await expect(lab).toBeVisible();
    await expect(lab.getByText("Linked to you")).toBeVisible();
    await expect(lab.getByText("Suggested")).toBeVisible();
    await expect(lab.getByText(/Open →|Link →|Search →/).first()).toBeVisible();

    // No legacy split panes / tracks list
    await expect(page.getByTestId("profile-know")).toHaveCount(0);
    await expect(page.getByTestId("profile-offer")).toHaveCount(0);

    const detail = page.getByTestId("profile-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail.getByText("Scholar")).toBeVisible();
    await expect(detail.getByText("Strengths")).toBeVisible();
    await expect(detail.getByText("Desk")).toBeVisible();
    await expect(detail).toContainText(/faculty/i);

    await page.screenshot({ path: OUT, fullPage: true });
  });
});
