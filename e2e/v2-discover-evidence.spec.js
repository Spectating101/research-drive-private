import { test, expect } from "@playwright/test";
import { MOCK_DISCOVER_ASSESSMENT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

test.describe("Discover evidence assessment", () => {
  test("question → editable brief → verdict → held evidence → precise gap keeps unknown metadata honest", async ({ page }) => {
    const incomplete = {
      ...MOCK_DISCOVER_ASSESSMENT,
      held_evidence: [
        ...MOCK_DISCOVER_ASSESSMENT.held_evidence,
        {
          dataset_id: "unknown_governance_metadata",
          evidence_state: {
            materialization: { status: "not_materialized" },
            access: { status: "unknown" },
            coverage: { status: "incomplete" },
          },
        },
      ],
      gap: {
        ...MOCK_DISCOVER_ASSESSMENT.gap,
        blocks: { analysis: "A governance-specific issuer-quarter analysis." },
      },
    };
    await mockV2Api(page, { assessmentBody: incomplete });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    await expect(page.getByLabel("Public URL or DOI")).toBeVisible();
    await page.getByLabel("Explore question").fill("Do we hold issuer-quarter governance data for Taiwan?");
    await page.getByRole("button", { name: "Assess evidence" }).click();

    const result = page.getByTestId("discover-assessment-result");
    await expect(result).toBeVisible();
    await expect(page.getByTestId("discover-verdict")).toHaveText("Partially covered");
    await expect(result.getByLabel("Geography / universe value")).toHaveValue("Taiwan listed issuers");
    await expect(result.getByLabel("Fields value")).toHaveValue("board_composition · governance_score");
    await expect(result.getByLabel("Time range provenance")).toHaveValue("unspecified");
    await expect(page.getByTestId("discover-held-evidence")).toContainText("Issuer weekly fundamentals");
    await expect(page.getByTestId("discover-held-evidence")).toContainText("Held evidence record");
    await expect(page.getByTestId("discover-held-evidence")).toContainText("Contribution unknown");
    await expect(page.getByTestId("discover-evidence-gap")).toContainText("Board-governance variables");
    await expect(result).toContainText("2 held catalog records considered · deterministic catalog metadata");
    await expect(result).not.toContainText("[object Object]");
    await expect(page.getByTestId("discover-filter-menu")).toHaveCount(0);

    await result.getByRole("button", { name: "Apply & reassess" }).click();
    await expect(page.getByTestId("discover-verdict")).toBeVisible();
    await page.getByTestId("discover-held-evidence").getByRole("button", { name: /Issuer weekly fundamentals/ }).click();
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
  });

  test("missing catalog coverage is neutral and does not become a negative verdict", async ({ page }) => {
    await mockV2Api(page, {
      assessmentBody: {
        ...MOCK_DISCOVER_ASSESSMENT,
        assessment_status: "insufficient_metadata",
        verdict: null,
        because: "No catalog record considered declares coverage metadata for any requested dimension.",
        held_evidence: [],
        assessment_basis: {
          ...MOCK_DISCOVER_ASSESSMENT.assessment_basis,
          uncovered_candidate_ids: ["issuer_weekly_panel"],
        },
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    await page.getByLabel("Explore question").fill("Do we hold issuer-quarter governance data for Taiwan?");
    await page.getByRole("button", { name: "Assess evidence" }).click();

    await expect(page.getByTestId("discover-verdict")).toHaveText("Not yet recorded");
    await expect(page.getByTestId("discover-verdict")).toHaveClass(/insufficient_metadata/);
    await expect(page.getByTestId("discover-assessment-result")).not.toContainText("Not covered");
  });
});
