import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {
  MOCK_STABLECOIN_ASSESSMENT,
  mockV2Api,
  waitForShell,
} from "./fixtures/v2MockApi.js";

const OUT = path.resolve("docs/status/generated/discover-freeze-2026-07-28");
const QUESTION = "What data can I use to study stablecoin de-pegs?";
const GROUNDED_REPLY =
  "Use dated de-peg events as the spine, then join daily exchange-level price and volume. "
  + "The known sources cover event timing and market activity, but harmonized exchange volume remains the gap. "
  + "Clarify the target exchanges before accepting a custom strategy.";

const DISCOVER_BODY = {
  sections: [
    {
      title: "Known sources",
      rows: [
        {
          dataset_id: "coingecko_market_history_ext",
          candidate_key: "dataset:coingecko_market_history_ext",
          title: "CoinGecko market history",
          source: "CoinGecko",
          collect_via: "coingecko_public",
          url: "https://www.coingecko.com/en/api",
          coverage: "2020–present",
          grain: "asset-day",
          description:
            "Daily crypto prices and aggregate volume by asset; exchange-level history requires a custom collection route.",
          recommended_use: "Measure crypto market activity around dated de-peg events.",
        },
        {
          dataset_id: "bigquery_public_blockchain_ext",
          candidate_key: "dataset:bigquery_public_blockchain_ext",
          title: "Google BigQuery public blockchain datasets",
          source: "Google Cloud",
          collect_via: "bigquery_public",
          url: "https://cloud.google.com/blockchain-analytics",
          grain: "transaction",
          description: "Public on-chain transaction tables for measuring blockchain activity around market events.",
          recommended_use: "Construct transaction activity measures around dated market events.",
        },
      ],
    },
  ],
  total: 2,
};

async function shot(page, name) {
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, name), fullPage: false });
}

test("capture the frozen adaptive Discover composition after polish", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockV2Api(page, {
    discoverBody: DISCOVER_BODY,
    assessmentBody: MOCK_STABLECOIN_ASSESSMENT,
    chatReply: GROUNDED_REPLY,
  });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);

  await page.getByLabel("Search or describe a research need").fill(QUESTION);
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await expect(page.getByTestId("discover-best-fit")).toContainText("CoinGecko market history");
  await expect(page.getByTestId("ask-messages")).toContainText("Use dated de-peg events as the spine");
  await expect(page.getByRole("button", { name: "Custom strategy ready" })).toBeVisible();
  await shot(page, "results.png");

  await page.setViewportSize({ width: 390, height: 844 });
  const grip = page.locator(".rd-v2-rail-mobile-grip");
  if (await grip.getAttribute("aria-expanded") !== "true") await grip.click();
  await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await shot(page, "mobile-question.png");

  if (await grip.getAttribute("aria-expanded") === "true") await grip.click();
  await expect(page.getByTestId("discover-best-fit")).toBeVisible();
  await shot(page, "mobile-results.png");

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "Custom strategy ready" }).click();
  const strategy = page.getByTestId("discover-route-comparison");
  await expect(strategy).toContainText("Stablecoin de-peg exchange activity dataset");
  await expect(strategy).toContainText("Major stablecoin exchanges");
  await shot(page, "strategy.png");

  await strategy.getByRole("button", { name: "Close acquisition strategy" }).click();
  await page.getByTestId("discover-best-fit").getByRole("button", { name: "Add to collection" }).first().click();
  await expect(page.getByRole("dialog", { name: "Review acquisition" })).toBeVisible();
  await expect(page.getByTestId("discover-intent-workspace")).toContainText("Acquisition review");
  await shot(page, "acquisition-review.png");
});
