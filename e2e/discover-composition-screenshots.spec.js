/**
 * Discover Composition screenshots — Browse vs Focused Evaluation (+ C1).
 * Run: CI=true YZU_PAGES=false TMPDIR=$PWD/.tmp-pw npx playwright test e2e/discover-composition-screenshots.spec.js
 */
import { test, expect } from "@playwright/test";
import { MOCK_DISCOVER_HIT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-composition";
fs.mkdirSync(OUT, { recursive: true });

const KEY = "dataset:mops_financial_statements_ext";

const MIXED_DISCOVER = {
  sections: [
    {
      title: "Mixed",
      rows: [
        {
          dataset_id: "gdelt_asia_daily_country_panel",
          title: "Asia daily news-risk panel",
          source: "GDELT",
          analysis_readiness: "instant",
          local_root: "research_panels/gdelt",
          coverage: "2018–2026 · Asia",
          description: "Lab panel ready for query",
        },
        ...(MOCK_DISCOVER_HIT.sections?.[0]?.rows || []),
        {
          title: "Licensed market feed",
          source: "Vendor",
          url: "https://vendor.example/feed",
          manual_access: true,
          access_mode: "licensed",
          license: "commercial license",
          description: "Entitlement-gated market data",
        },
      ],
    },
  ],
  total: 3,
};

function job(status, extra = {}) {
  return {
    id: `job-${status}`,
    status,
    candidate_key: KEY,
    connector_id: "example_com_data",
    registered_dataset_id: extra.registered_dataset_id ?? null,
    output_manifest_id: extra.output_manifest_id ?? null,
    error: extra.error || "",
    updated_at: extra.updated_at || "2026-07-10T14:32:00Z",
    result: extra.result || {},
    plan: { title: "MOPS financial statements (Taiwan)" },
    request: { candidate_key: KEY, connector_id: "example_com_data" },
  };
}

async function shot(page, label) {
  await page.locator(".rd-v2-toast").waitFor({ state: "detached", timeout: 6000 }).catch(() => {});
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

async function openBrowse(page, { jobsBody = { jobs: [] }, discoverBody = MIXED_DISCOVER } = {}) {
  await mockV2Api(page, { discoverBody, jobsBody });
  await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
  await waitForShell(page);
}

async function selectMops(page) {
  await page.locator(".rd-v2-search-pill input").fill("mops");
  await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
  await expect(page.getByTestId("discover-focus-workspace")).toBeVisible();
}

async function assertMobileFullWidth(page) {
  const box = await page.getByTestId("discover-focus-workspace").boundingBox();
  expect(box).toBeTruthy();
  expect(box.width).toBeGreaterThanOrEqual(380);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const viewport = page.viewportSize();
  expect(scrollWidth).toBeLessThanOrEqual(viewport.width + 1);
}

test.describe("Discover composition screenshots", () => {
  test("browse / focus / focused lifecycle evidence", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    // 01 browse awaiting
    await openBrowse(page);
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(page.locator(".rd-v2-shell")).toHaveClass(/no-rail/);
    await shot(page, "01-desktop-browse-awaiting");

    // 02 browse grouped — all three group headings
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(page.locator('.rd-v2-discover-group[data-group="lab"] .rd-v2-discover-group-title')).toHaveText(
      /In your lab/i,
    );
    await expect(page.locator('.rd-v2-discover-group[data-group="external"] .rd-v2-discover-group-title')).toHaveText(
      /External candidates/i,
    );
    await expect(page.locator('.rd-v2-discover-group[data-group="access"] .rd-v2-discover-group-title')).toHaveText(
      /Needs access/i,
    );
    await shot(page, "02-desktop-browse-grouped");

    // 03 focused external before probe
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    await expect(page.getByTestId("discover-focus-workspace")).toBeVisible();
    await expect(page.getByTestId("discover-browse-mode")).toHaveCount(0);
    await expect(page.locator(".rd-v2-shell")).toHaveClass(/no-rail/);
    await expect(
      page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface").locator('[aria-label="Can I use this"]'),
    ).toContainText("Acquisition available");
    await shot(page, "03-desktop-focus-before-probe");

    // 04 focused after probe
    await page.locator('[data-testid="discover-eval-actions"]').getByRole("button", { name: "Probe source" }).click();
    await expect(
      page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified"),
    ).toBeVisible();
    await shot(page, "04-desktop-focus-after-probe");

    // 05 focused Ask support rail
    await page.getByTestId("discover-focus-workspace").getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.locator("aside.rd-v2-rail")).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await shot(page, "05-desktop-focus-with-ask");

    // 06 approval required
    await openBrowse(page, { jobsBody: { jobs: [job("pending_approval")] } });
    await selectMops(page);
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Approval required",
    );
    await shot(page, "06-desktop-focus-approval-required");

    // 07 running — same-state counterpart to lifecycle screenshot 05
    await openBrowse(page, {
      jobsBody: { jobs: [job("running", { result: { stage: "Downloading files" } })] },
    });
    await selectMops(page);
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Running",
    );
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Downloading files",
    );
    await shot(page, "07-desktop-focus-running");

    // 08 failed
    await openBrowse(page, {
      jobsBody: { jobs: [job("failed", { error: "HTTP 403 from source" })] },
    });
    await selectMops(page);
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Failed",
    );
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "HTTP 403",
    );
    await shot(page, "08-desktop-focus-failed");

    // 09 registration pending
    await openBrowse(page, { jobsBody: { jobs: [job("completed")] } });
    await selectMops(page);
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Registration pending",
    );
    await expect(
      page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface").locator('[aria-label="Can I use this"]'),
    ).toContainText("Not yet reusable");
    await shot(page, "09-desktop-focus-registration-pending");

    // 10 registered
    await openBrowse(page, {
      jobsBody: { jobs: [job("completed", { registered_dataset_id: "mops_financial_statements_2026" })] },
    });
    await selectMops(page);
    const regSurface = page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface");
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Registered in lab",
    );
    await expect(regSurface.locator('[aria-label="Can I use this"]')).toContainText("Registered in lab");
    await expect(regSurface.locator('[aria-label="Can I use this"]')).not.toContainText("Query ready");
    await expect(page.locator('[data-testid="discover-eval-actions"] .rd-v2-btn.primary')).toContainText(
      "Open in Library",
    );
    await shot(page, "10-desktop-focus-registered");

    // 11 query ready
    await openBrowse(page, {
      jobsBody: {
        jobs: [
          job("completed", {
            registered_dataset_id: "mops_financial_statements_2026",
            result: { query_ready: true, analysis_readiness: "instant" },
          }),
        ],
      },
    });
    await selectMops(page);
    const qrSurface = page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface");
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Query ready",
    );
    await expect(qrSurface.locator('[aria-label="Can I use this"]')).toContainText("In lab · Query ready");
    await expect(page.locator('[data-testid="discover-eval-actions"] .rd-v2-btn.primary')).toContainText(
      "Open in Library",
    );
    await shot(page, "11-desktop-focus-query-ready");

    // 12 back to browse reveals projected row/counts (mixed fixture: lab panel + projected MOPS)
    await page.getByTestId("discover-focus-workspace").getByRole("button", { name: "← Back to results" }).click();
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await expect(
      page.locator(".rd-v2-discover-candidate", { hasText: "MOPS" }),
    ).toContainText("In lab · Query ready");
    await expect(page.locator(".rd-v2-discover-pipeline-counts")).toContainText("2 query ready");
    await expect(page.locator(".rd-v2-discover-pipeline-counts")).toContainText("2 in lab");
    await shot(page, "12-desktop-back-projected-query-ready");

    // 13 tablet running
    await page.setViewportSize({ width: 900, height: 1200 });
    await openBrowse(page, {
      jobsBody: { jobs: [job("running", { result: { stage: "Downloading files" } })] },
    });
    await selectMops(page);
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Running",
    );
    await shot(page, "13-tablet-focus-running");

    // 14 tablet failed
    await openBrowse(page, {
      jobsBody: { jobs: [job("failed", { error: "HTTP 403 from source" })] },
    });
    await selectMops(page);
    await shot(page, "14-tablet-focus-failed");

    // 15 mobile browse full width
    await page.setViewportSize({ width: 390, height: 1200 });
    await openBrowse(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await expect(page.getByTestId("discover-browse-mode")).toBeVisible();
    await shot(page, "15-mobile-browse");

    // 16 mobile query ready — full viewport width after shell fix
    await openBrowse(page, {
      jobsBody: {
        jobs: [
          job("completed", {
            registered_dataset_id: "mops_financial_statements_2026",
            result: { query_ready: true, analysis_readiness: "instant" },
          }),
        ],
      },
    });
    await selectMops(page);
    await assertMobileFullWidth(page);
    await expect(
      page.getByTestId("discover-focus-workspace").getByTestId("discover-eval-surface").locator('[aria-label="Can I use this"]'),
    ).toContainText("In lab · Query ready");
    await expect(page.getByTestId("discover-focus-workspace").getByTestId("discover-lifecycle")).toContainText(
      "Query ready",
    );
    await expect(page.locator('[data-testid="discover-eval-actions"] .rd-v2-btn.primary')).toContainText(
      "Open in Library",
    );
    await shot(page, "16-mobile-focus-query-ready");
  });
});
