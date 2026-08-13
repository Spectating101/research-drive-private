import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  waitForShell,
} from "./fixtures/v2MockApi.js";

/**
 * Discover feature E2E (main composition + Explore|History converge).
 * Authority: docs/UI_PRODUCT_AUTHORITY.md
 * Classify via docs/DISCOVER_E2E_AUTHORITY_AUDIT.md before product fixes.
 */

async function searchDiscover(page, query = "MOPS") {
  await page.getByLabel("Search or describe a research need").fill(query);
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await expect(page.getByTestId("discover-result-summary")).toBeVisible();
}

test.describe("v2 Discover tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("empty state offers one adaptive entrance and quiet intake", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByLabel("Search or describe a research need")).toBeVisible();
    await expect(page.getByRole("button", { name: "Explore", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /mode/i })).toHaveCount(0);
    await expect(page.getByLabel("Public URL or DOI")).toBeVisible();
    // VC-5: two compact examples teach the one-composer behaviour, and the
    // curated-source block collapses to a single quiet line when it has no
    // routes rather than filling the canvas with an empty section.
    const examples = page.getByTestId("discover-composer-examples");
    await expect(examples).toBeVisible();
    await expect(examples.getByText("Try a keyword")).toBeVisible();
    await expect(examples.getByText("Ask a research need")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Sources the desk already knows how to investigate" }),
    ).toHaveCount(0);
  });

  test("keyword search renders the external result composition", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "TWSE governance");
    await expect(page.locator('button.rd-v2-discover-candidate').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('button.rd-v2-discover-candidate')).not.toHaveCount(0);
    await expect(page.getByTestId("discover-best-fit")).toContainText(/TWSE Open\s*API|TWSE|MOPS|candidate/i);
    await expect(page.getByTestId("discover-interpreting")).toBeVisible();
    await expect(page.getByTestId("discover-search-summary")).toContainText(/offerings? you can add/i);
    await expect(page.getByTestId("discover-search-summary")).toContainText(/already in your Library/i);
    await expect(page.getByTestId("discover-rank-foot")).toContainText(/Ranked using active research/i);
    await expect(page.getByTestId("discover-filter-menu")).toBeVisible();
    await expect(page.getByTestId("discover-browse-mode")).not.toContainText(/process overview/i);
  });

  test("selecting a discover row keeps Explore visible and updates the Detail rail", async ({ page }) => {
    // Explicit fixture: with an empty index the desk now states an honest
    // "no match in the current research index" rather than seeding demo rows,
    // so a selectable candidate has to come from real result data.
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page);
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
    const surface = page.locator("aside.rd-v2-rail").getByTestId("discover-eval-surface");
    await expect(surface).toBeVisible();
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected")).toHaveCount(1);
    await expect(page.locator(".rd-v2-shell")).not.toHaveClass(/no-rail/);
    await expect(surface.locator(".rd-v2-eval-title")).toContainText(/MOPS|Taiwan/i);
    await expect(surface).toContainText("Can I use this?");
    await expect(surface).toContainText("Evidence");
    await expect(surface).toContainText("Still unknown");
    await expect(surface.locator(".rd-v2-eval-tech")).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await expect(
      page.locator('[data-testid="discover-eval-actions"] .rd-v2-btn.primary', {
        hasText: /Request this evidence|Open in Library/,
      }),
    ).toBeVisible();
    await expect(surface).not.toContainText("What we know");
    await expect(surface).not.toContainText("Possession");
  });

  test("mobile selection preserves Explore and opens Ask deliberately", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();

    const shell = page.locator(".rd-v2-shell");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected")).toHaveCount(1);
    await expect(shell).not.toHaveClass(/no-rail/);
    await expect(rail).toHaveClass(/rd-v2-rail-collapsed/);
    await rail.getByRole("button", { name: /Show Detail/ }).click();
    await expect(rail).not.toHaveClass(/rd-v2-rail-collapsed/);
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(shell).not.toHaveClass(/no-rail/);
    await expect(rail).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText(/MOPS|Taiwan/i);
    await page.getByTestId("ask-messages").getByRole("button", { name: /Assess this source/i }).click();
    await expect(page.getByTestId("ask-messages")).toContainText("Assess this");
    await expect(page.getByTestId("ask-messages")).toContainText(/MOPS|Taiwan/i);
  });

  test("Probe source shows verified facts; technical evidence stays collapsed", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    await page.locator('[data-testid="discover-eval-actions"]').getByRole("button", { name: "Probe source" }).click();
    const surface = page.locator("aside.rd-v2-rail").getByTestId("discover-eval-surface");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText("text/csv");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText(/domain observed/i);
    await expect(surface.locator(".rd-v2-eval-verified")).not.toContainText("MOPS publisher");
    await expect(surface.locator(".rd-v2-eval-inferred")).toContainText(/direct file|machine-readable/i);
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await surface.locator(".rd-v2-eval-tech > summary").click();
    await expect(surface.locator(".rd-v2-eval-tech")).toHaveAttribute("open");
  });

  test("an internal mechanism marker in source never renders as a raw ribbon token", async ({ page }) => {
    const body = {
      sections: [
        {
          title: "Registry",
          rows: [
            {
              dataset_id: "etherscan_stablecoin_probe",
              candidate_key: "dataset:etherscan_stablecoin_probe",
              title: "Etherscan Stablecoin Probe Snapshot",
              source: "collection_index",
              collect_via: "collection_intake",
              coverage: "2024-2026",
              grain: "token-day",
              description: "Etherscan stablecoin token snapshot",
            },
          ],
        },
      ],
      total: 1,
    };
    await mockV2Api(page, { discoverBody: body });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "stablecoin");
    const row = page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate", { hasText: "Etherscan" });
    await expect(row).toBeVisible();
    await expect(row).not.toContainText("COLLECTION_I");
    await expect(row.locator(".rd-v2-source-ribbon")).toHaveCount(0);
  });

  test("the result breakdown is stated once, never restated further down the page", async ({ page }) => {
    const body = {
      sections: [
        {
          title: "Registry",
          rows: [
            {
              dataset_id: "mops_financial_statements_ext",
              candidate_key: "dataset:mops_financial_statements_ext",
              title: "MOPS financial statements (Taiwan)",
              source: "MOPS",
              collect_via: "mops_tw",
              url: "https://mops.twse.com.tw/example",
              coverage: "2015-2026",
              grain: "issuer-quarter",
              description: "TW listed company filings",
            },
            {
              dataset_id: "coingecko_market_history",
              candidate_key: "dataset:coingecko_market_history",
              title: "CoinGecko market history",
              source: "CoinGecko",
              url: "https://coingecko.com/example",
              coverage: "2018-2026",
              grain: "asset-day",
              description: "Public crypto market API",
            },
          ],
        },
      ],
      total: 2,
    };
    await mockV2Api(page, { discoverBody: body });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await searchDiscover(page, "market");
    const centre = await page.locator("main").innerText();
    expect((centre.match(/results? in your Library/gi) || []).length).toBeLessThanOrEqual(1);
    expect(centre).not.toContain("sources beyond your Library");
  });
});
