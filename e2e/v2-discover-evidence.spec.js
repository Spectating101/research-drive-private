import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_ASSESSMENT,
  MOCK_DISCOVER_HIT,
  mockV2Api,
  waitForShell,
} from "./fixtures/v2MockApi.js";

async function search(page, query = "MOPS filings") {
  await page.getByLabel("Search or describe a research need").fill(query);
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await expect(page.getByTestId("discover-result-summary")).toBeVisible();
}

test.describe("Discover adaptive Explore", () => {
  test("plain lookup stays on the index path without starting assessment or Ask", async ({ page }) => {
    let deepCalls = 0;
    let assessmentCalls = 0;
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (
        url.pathname.includes("/library/discover/sources")
        && (url.searchParams.get("live") === "1" || url.searchParams.get("semantic") === "1")
      ) deepCalls += 1;
      if (request.url().includes("/library/discover/assessment")) assessmentCalls += 1;
    });
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: MOCK_DISCOVER_ASSESSMENT,
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    await expect(page.getByLabel("Public URL or DOI")).toBeVisible();
    await search(page);
    await expect(page.getByTestId("discover-best-fit")).toContainText("MOPS financial statements");
    expect(deepCalls).toBe(0);
    expect(assessmentCalls).toBe(0);
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  test("an index miss stays local until Search wider is explicit", async ({ page }) => {
    let deepCalls = 0;
    let webCalls = 0;
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (
        url.pathname.includes("/library/discover/sources")
        && (url.searchParams.get("live") === "1" || url.searchParams.get("semantic") === "1")
      ) deepCalls += 1;
      if (request.url().includes("/library/discover/web")) webCalls += 1;
    });
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "xylophone qqq archive");
    await expect(page.getByText(/No matches for/)).toBeVisible();
    expect(deepCalls).toBe(0);
    expect(webCalls).toBe(0);

    await page.getByRole("button", { name: "Search wider", exact: true }).click();
    await expect.poll(() => deepCalls).toBeGreaterThan(0);
  });

  test("a research question keeps results visible, assesses automatically, and seeds Ask", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: MOCK_DISCOVER_ASSESSMENT,
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "Do we hold issuer-quarter governance data for Taiwan?");

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("ask-messages")).toContainText(
      "Do we hold issuer-quarter governance data for Taiwan?",
    );
    await rail.getByRole("tab", { name: "Detail" }).click();
    const result = page.getByTestId("discover-assessment-result");
    await expect(result).toBeVisible();
    await expect(page.getByTestId("discover-verdict")).toHaveText("Partially covered");
    await expect(page.getByTestId("discover-best-fit")).toContainText("MOPS financial statements");
    await expect(rail.getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
    await result.locator("details.rd-v2-evidence-edit > summary").click();
    await expect(result.getByLabel("Geography / universe value")).toHaveValue("Taiwan listed issuers");
    await expect(result.getByLabel("Fields provenance")).toHaveValue("explicit");
    await expect(page.getByTestId("discover-filter-menu")).toHaveCount(1);
    await expect(result).not.toContainText("[object Object]");
  });

  test("metadata gaps stay neutral and do not open procurement comparison", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: {
        ...MOCK_DISCOVER_ASSESSMENT,
        assessment_status: "insufficient_metadata",
        verdict: null,
        because: "No catalog record considered declares coverage metadata for any requested dimension.",
        held_evidence: [],
        assessment_basis: {
          ...MOCK_DISCOVER_ASSESSMENT.assessment_basis,
          uncovered_candidate_ids: ["mops_financial_statements_ext"],
        },
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "What data covers Taiwan issuer-quarter governance?");
    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" }).click();

    await expect(page.getByTestId("discover-verdict")).toHaveText("Not yet recorded");
    await expect(page.getByTestId("discover-verdict")).toHaveClass(/insufficient_metadata/);
    await expect(page.getByRole("button", { name: "Strategy needs context" })).toBeVisible();
    await expect(page.getByTestId("discover-route-comparison")).toHaveCount(0);
  });

  test("a genuine evidence gap opens temporary route comparison and keeps approval downstream", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: MOCK_DISCOVER_ASSESSMENT,
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "What data covers Taiwan issuer-quarter governance?");

    await page.getByRole("button", { name: "Custom strategy ready" }).click();
    const comparison = page.getByTestId("discover-route-comparison");
    await expect(comparison).toBeVisible();
    await expect(comparison).toContainText("Proposed transform");
    await expect(comparison).toContainText("Planned output");
    await expect(comparison).toContainText("Unknown");
    await expect(comparison).toContainText("cannot submit procurement");

    await comparison.getByRole("button", { name: /MOPS financial statements/ }).click();
    await expect(page.getByTestId("discover-intent-workspace")).toBeVisible();
    await expect(page.getByTestId("discover-result-summary")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Review acquisition" })).toBeVisible();
  });

  test("an external result becomes a reviewed durable intent before approval submission", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "MOPS filings");

    await page.getByTestId("discover-best-fit").getByRole("button", { name: "Add to collection" }).click();

    const workspace = page.getByTestId("discover-intent-workspace");
    await expect(workspace).toBeVisible();
    await expect(workspace).toContainText("MOPS financial statements");
    await expect(workspace).toContainText("TW listed company filings");
    await expect(workspace).toContainText("Proposed routes · review required");
    await expect(workspace).toContainText("Recommended route");
    await expect(workspace.getByRole("button", { name: "Submit for approval" })).toHaveCount(0);
    await expect(page.getByTestId("discover-result-summary")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Review acquisition" })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Durable Discover decision record");
    await expect(page.locator("aside.rd-v2-rail").getByRole("button", { name: "Request this evidence" })).toHaveCount(0);

    await workspace.getByRole("button", { name: "Accept routes for review" }).click();
    await expect(workspace).toContainText("Reviewed routes");
    await expect(workspace.getByRole("button", { name: "Submit for approval" })).toBeEnabled();
    await workspace.getByRole("button", { name: "Submit for approval" }).click();

    await expect(workspace.getByTestId("discover-intent-collection")).toContainText("pending approval");
    await expect(workspace.getByTestId("discover-intent-collection")).toContainText(
      "collection remains governed by History",
    );
  });
});
