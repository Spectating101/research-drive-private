import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  MOCK_PROBE_RESULT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

const TWO_DISCOVER_SOURCES = {
  sections: [
    {
      title: "Registry",
      rows: [
        MOCK_DISCOVER_HIT.sections[0].rows[0],
        {
          dataset_id: "sec_company_facts_ext",
          candidate_key: "dataset:sec_company_facts_ext",
          title: "SEC company facts",
          source: "SEC",
          collect_via: "sec_companyfacts",
          url: "https://www.sec.gov/files/company_tickers.json",
          coverage: "2009–2026",
          license: "US Government Work",
          grain: "issuer-quarter",
          description: "US issuer filings and standardized facts",
        },
      ],
    },
  ],
  total: 2,
};

async function openAsk(page) {
  const rail = page.locator("aside.rd-v2-rail");
  await rail.getByRole("tab", { name: "Ask" }).click();
  return rail;
}

function capturePageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test.describe("Research Drive interaction robustness", () => {
  test("same-tick Ask activation submits once and survives navigation", async ({ page }) => {
    const pageErrors = capturePageErrors(page);
    await mockV2Api(page);
    await page.unroute("**/api/library/chat/stream");
    await page.unroute("**/api/library/chat");

    let chatRequests = 0;
    const delayedChat = async (route) => {
      chatRequests += 1;
      await new Promise((resolve) => setTimeout(resolve, 800));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "robustness-single-flight",
          reply: "The single request completed after navigation.",
          action: "answer",
        }),
      });
    };
    await page.route("**/api/library/chat/stream", delayedChat);
    await page.route("**/api/library/chat", delayedChat);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const rail = await openAsk(page);
    await rail.getByTestId("ask-composer").fill("Explain the stability envelope.");

    await page.evaluate(() => {
      const send = [...document.querySelectorAll("aside.rd-v2-rail button")]
        .find((node) => node.textContent?.trim() === "Send");
      if (!send) throw new Error("Send button not found");
      send.click();
      send.click();
      send.click();
    });

    await expect(rail.getByTestId("interaction-progress")).toBeVisible();
    await v2Nav(page, "Synthesis");
    await expect(page.getByRole("heading", { name: "Synthesis" })).toBeVisible();
    await expect(rail).toContainText("The single request completed after navigation.", { timeout: 10_000 });

    expect(chatRequests).toBe(1);
    await expect(
      rail.locator(".rd-v2-ask-bubble", { hasText: "You: Explain the stability envelope." }),
    ).toHaveCount(1);
    await expect(rail.getByTestId("interaction-progress")).toHaveCount(0);
    await expect(rail.getByTestId("ask-composer")).toBeEnabled();
    expect(pageErrors).toEqual([]);
  });

  test("Ask failure clears transient state and permits a successful retry", async ({ page }) => {
    const pageErrors = capturePageErrors(page);
    await mockV2Api(page);
    await page.unroute("**/api/library/chat/stream");
    await page.unroute("**/api/library/chat");

    let attempts = 0;
    const failThenSucceed = async (route) => {
      attempts += 1;
      if (attempts === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Research assistant temporarily unavailable" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "robustness-retry",
          reply: "Retry completed successfully.",
          action: "answer",
        }),
      });
    };
    await page.route("**/api/library/chat/stream", failThenSucceed);
    await page.route("**/api/library/chat", failThenSucceed);

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const rail = await openAsk(page);
    const composer = rail.getByTestId("ask-composer");
    const send = rail.getByRole("button", { name: "Send" });

    await composer.fill("First attempt");
    await send.click();
    await expect(rail.locator(".rd-v2-ask-bubble.error")).toContainText(/temporarily unavailable|503/i);
    await expect(rail.getByTestId("interaction-progress")).toHaveCount(0);
    await expect(composer).toBeEnabled();

    await composer.fill("Retry attempt");
    await send.click();
    await expect(rail).toContainText("Retry completed successfully.");
    expect(attempts).toBe(2);
    await expect(rail.getByTestId("interaction-progress")).toHaveCount(0);
    await expect(composer).toBeEnabled();
    expect(pageErrors).toEqual([]);
  });

  test("stale probes cannot overwrite selection and probe toasts preserve the active source", async ({ page }) => {
    const pageErrors = capturePageErrors(page);
    await mockV2Api(page, { discoverBody: TWO_DISCOVER_SOURCES });
    await page.unroute("**/library/discover/probe");

    const probedKeys = [];
    await page.route("**/library/discover/probe", async (route) => {
      const body = route.request().postDataJSON?.() || {};
      const key = String(body.candidate_key || "");
      probedKeys.push(key);
      if (key.includes("mops")) {
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_PROBE_RESULT,
          candidate_key: key,
          connector: {
            ...MOCK_PROBE_RESULT.connector,
            id: key.includes("sec") ? "sec_companyfacts" : "mops_tw",
            connector_id: key.includes("sec") ? "sec_companyfacts" : "mops_tw",
          },
        }),
      });
    });

    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("filings");

    const mops = page.locator("button.rd-v2-discover-candidate", { hasText: "MOPS financial statements" });
    const sec = page.locator("button.rd-v2-discover-candidate", { hasText: "SEC company facts" });
    await expect(mops).toBeVisible();
    await expect(sec).toBeVisible();

    await mops.click();
    await page.getByTestId("discover-eval-actions").getByRole("button", { name: "Probe source" }).click();
    await sec.click();
    await page.waitForTimeout(800);

    const rail = page.locator("aside.rd-v2-rail");
    const surface = rail.getByTestId("discover-eval-surface");
    await expect(sec).toHaveClass(/selected/);
    await expect(surface.locator(".rd-v2-eval-title")).toContainText("SEC company facts");
    await expect(page.locator(".rd-v2-toast", { hasText: "MOPS" })).toHaveCount(0);

    await page.getByTestId("discover-eval-actions").getByRole("button", { name: "Probe source" }).click();
    await expect(page.locator(".rd-v2-toast")).toContainText("SEC company facts probed");
    await expect(sec).toHaveClass(/selected/);
    await expect(surface).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-title")).toContainText("SEC company facts");
    expect(probedKeys).toEqual([
      "dataset:mops_financial_statements_ext",
      "dataset:sec_company_facts_ext",
    ]);
    expect(pageErrors).toEqual([]);
  });

  test("a replacement toast owns its full dwell time without stacking", async ({ page }) => {
    const pageErrors = capturePageErrors(page);
    await mockV2Api(page);
    await page.unroute("**/api/library/chat/stream");
    await page.unroute("**/api/library/chat");

    const queuedResponse = (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "robustness-toast",
          reply: "Queue request accepted.",
          action: "queue",
        }),
      });
    await page.route("**/api/library/chat/stream", queuedResponse);
    await page.route("**/api/library/chat", queuedResponse);

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const rail = await openAsk(page);
    const composer = rail.getByTestId("ask-composer");

    await composer.fill("Queue request one");
    await rail.getByRole("button", { name: "Send" }).click();
    const toast = page.locator(".rd-v2-toast");
    await expect(toast).toHaveText("Queued for collection");
    await expect(toast).toHaveCount(1);

    await page.waitForTimeout(1200);
    await composer.fill("Queue request two");
    await rail.getByRole("button", { name: "Send" }).click();
    await expect(toast).toHaveText("Queued for collection");
    await expect(toast).toHaveCount(1);

    await page.waitForTimeout(3200);
    await expect(toast).toBeVisible();
    await expect(toast).not.toHaveClass(/exiting/);
    await expect(toast).toHaveCount(0, { timeout: 1500 });
    expect(pageErrors).toEqual([]);
  });
});
