import { test, expect } from "@playwright/test";

async function navTo(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
  await page.getByRole("heading", { name: "Recent" }).waitFor({ timeout: 30_000 });
});

test("home loads React desk shell", async ({ page }) => {
  await expect(page.getByText("Research Drive")).toBeVisible();
  await expect(page.getByPlaceholder("Search datasets in the library")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent" })).toBeVisible();
  await expect(page.locator(".rd-inspector-idle, .rd-inspector-compact")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Internal/ })).toHaveCount(0);
});

test("selection scopes details in rail", async ({ page }) => {
  await navTo(page, "Drive");
  await page.getByRole("heading", { name: "Drive", exact: true }).waitFor();
  const row = page.locator("main .rd-catalog-table tbody tr").filter({ has: page.locator(".rd-title") }).first();
  await row.waitFor({ timeout: 20_000 });
  await row.click();
  await expect(page.locator("aside.yzu-inspector")).toBeVisible();
  await expect(page.locator(".rd-inspector-compact h2, .rd-inspector-idle h2")).toBeVisible();
});

test("drive catalog browser", async ({ page }) => {
  await navTo(page, "Drive");
  await expect(page.getByRole("heading", { name: "Drive", exact: true })).toBeVisible();
  await expect(page.locator(".rd-catalog-table tbody tr").first()).toBeVisible();
  await expect(page.locator(".rd-folder-tree")).toHaveCount(0);
  await page.getByRole("button", { name: "Lab", exact: true }).click();
  await expect(page.getByRole("button", { name: "Research panels" })).toBeVisible();
});

test("library row opens dataset detail tabs", async ({ page }) => {
  await navTo(page, "Drive");
  await page.getByRole("button", { name: "Lab", exact: true }).click();
  await page.locator(".rd-catalog-table tbody tr:has(.rd-file)").first().click();
  await page.getByRole("toolbar", { name: "Selected dataset" }).getByRole("button", { name: "Open" }).click();
  await expect(page.getByRole("button", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Schema" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Query" })).toBeVisible();
});

test("chat page is full-width in main", async ({ page }) => {
  await navTo(page, "Source");
  await expect(page.getByRole("heading", { name: /Source & compare/i })).toBeVisible();
  const chat = page.locator("main .yzu-procure.main");
  await expect(chat).toBeVisible();
  await expect(chat.locator(".yzu-composer textarea")).toBeVisible();
  await expect(page.locator("aside .yzu-procure")).toHaveCount(0);
});

test("chat returns assistant prose or candidate cards", async ({ page }) => {
  test.setTimeout(180_000);
  await navTo(page, "Source");
  await page.locator("main .yzu-composer textarea").fill("What TWSE data is in the vault? Answer briefly.");
  await page.locator("main .yzu-composer button.primary").click();
  await page.waitForFunction(
    () => {
      const cards = document.querySelectorAll("main .yzu-candidate").length;
      const articles = [...document.querySelectorAll("main article.assistant")];
      const last = articles[articles.length - 1];
      const text = (last?.textContent || "").trim();
      return cards > 0 || (text.length > 80 && !text.includes("…"));
    },
    { timeout: 150_000 },
  );
  const body = await page.locator("main .yzu-chat").innerText();
  expect(body.length).toBeGreaterThan(80);
});

test("chat stream renders markdown without internal action badge", async ({ page }) => {
  let releaseStream;
  const streamPending = new Promise((resolve) => {
    releaseStream = resolve;
  });
  await page.route("**/library/chat/stream", async (route) => {
    await streamPending;
    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson; charset=utf-8",
      body: [
        JSON.stringify({ type: "progress", phase: "planning", text: "Checking the lab registry…" }),
        JSON.stringify({
          type: "complete",
          result: {
            session_id: "test-session",
            action: "composer",
            reply: [
              "## Procurement status",
              "",
              "- Registry hit",
              "- Stream parsed",
              "",
              "| Dataset | Status |",
              "|---|---|",
              "| TWSE | Ready |",
              "",
              "```text",
              "research_query_dataset",
              "```",
            ].join("\n"),
            candidates: [],
            suggested_prompts: [],
            next_steps: [],
            artifacts: { action: "composer" },
          },
        }),
      ].join("\n") + "\n",
    });
  });
  await navTo(page, "Source");
  await page.locator("main .yzu-composer textarea").fill("mock stream please");
  await page.locator("main .yzu-composer button.primary").click();
  await expect(page.locator("main article.assistant").last()).toContainText("Understanding your request");
  releaseStream();
  await expect(page.locator("main article.assistant h3", { hasText: "Procurement status" })).toBeVisible();
  await expect(page.locator("main article.assistant li", { hasText: "Registry hit" })).toBeVisible();
  await expect(page.locator("main article.assistant table").last()).toContainText("TWSE");
  await expect(page.locator("main article.assistant pre code", { hasText: "research_query_dataset" })).toBeVisible();
  await expect(page.locator("main article.assistant .yzu-action-label")).toHaveCount(0);
});
