import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_ASSESSMENT,
  MOCK_DISCOVER_HIT,
  mockV2Api,
  waitForShell,
} from "./fixtures/v2MockApi.js";

async function search(page, query = "MOPS filings") {
  await page.getByLabel("Search Discover").fill(query);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByTestId("discover-result-summary")).toBeVisible();
}

test.describe("Discover adaptive Explore", () => {
  test("plain lookup stays on the index path and Ask starts a continuing investigation", async ({ page }) => {
    let widerCalls = 0;
    let assessmentCalls = 0;
    page.on("request", (request) => {
      if (request.url().includes("/library/discover/sources")) widerCalls += 1;
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
    expect(widerCalls).toBe(0);
    expect(assessmentCalls).toBe(0);

    await page.getByRole("button", { name: "Ask about results" }).click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Ask · investigation");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS filings");
    await page.getByTestId("ask-composer").fill("Limit that to Taiwan and quarterly observations.");
    await page.getByTestId("ask-composer").press("Enter");
    await expect(page.getByTestId("ask-messages")).toContainText("Limit that to Taiwan and quarterly observations.");
    expect(widerCalls).toBe(0);
  });

  test("an index miss stays local until Search wider is explicit", async ({ page }) => {
    let widerCalls = 0;
    let webCalls = 0;
    page.on("request", (request) => {
      if (request.url().includes("/library/discover/sources")) widerCalls += 1;
      if (request.url().includes("/library/discover/web")) webCalls += 1;
    });
    await mockV2Api(page);
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "xylophone qqq archive");
    await expect(page.getByText(/No matches for/)).toBeVisible();
    expect(widerCalls).toBe(0);
    expect(webCalls).toBe(0);

    await page.getByRole("button", { name: "Search wider", exact: true }).click();
    await expect.poll(() => widerCalls).toBeGreaterThan(0);
  });

  test("assessment layers over retained results and exposes editable provenance", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: MOCK_DISCOVER_ASSESSMENT,
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "Do we hold issuer-quarter governance data for Taiwan?");

    await page.getByRole("button", { name: "Assess coverage" }).click();
    const result = page.getByTestId("discover-assessment-result");
    await expect(result).toBeVisible();
    await expect(page.getByTestId("discover-verdict")).toHaveText("Partially covered");
    await expect(page.getByTestId("discover-best-fit")).toContainText("MOPS financial statements");
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
    await search(page, "Taiwan issuer-quarter governance");
    await page.getByRole("button", { name: "Assess coverage" }).click();

    await expect(page.getByTestId("discover-verdict")).toHaveText("Not yet recorded");
    await expect(page.getByTestId("discover-verdict")).toHaveClass(/insufficient_metadata/);
    await expect(page.getByText("Verify catalog coverage before comparing procurement routes.")).toBeVisible();
    await expect(page.getByTestId("discover-route-comparison")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Compare ways/ })).toHaveCount(0);
  });

  test("a genuine evidence gap opens temporary route comparison and keeps approval downstream", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      assessmentBody: MOCK_DISCOVER_ASSESSMENT,
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "Taiwan issuer-quarter governance");
    await page.getByRole("button", { name: "Assess coverage" }).click();

    await page.getByRole("button", { name: /Compare ways to close this gap/ }).click();
    const comparison = page.getByTestId("discover-route-comparison");
    await expect(comparison).toBeVisible();
    await expect(comparison).toContainText("Inspect a public collection route");
    await expect(comparison).toContainText("Record implementation needed");
    await expect(comparison).toContainText("approval remains required");

    await comparison.getByRole("button", { name: "Inspect route evidence" }).click();
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
  });

  test("an external result becomes a reviewed durable intent before approval submission", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await search(page, "MOPS filings");

    await page.getByTestId("discover-best-fit").click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("button", { name: "Request this evidence" }).click();
    await expect(page.getByTestId("discover-request-confirm")).toContainText(
      "No collection starts from this action",
    );
    await page.getByRole("button", { name: "Open acquisition review" }).click();

    const workspace = page.getByTestId("discover-intent-workspace");
    await expect(workspace).toBeVisible();
    await expect(workspace).toContainText("MOPS financial statements");
    await expect(workspace).toContainText("TW listed company filings");
    await expect(workspace).toContainText("Proposed routes · review required");
    await expect(workspace).toContainText("Recommended route");
    await expect(workspace.getByRole("button", { name: "Submit for approval" })).toHaveCount(0);
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
