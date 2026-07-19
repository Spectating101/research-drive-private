import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";
import path from "node:path";
import fs from "node:fs";

const OUT = "docs/screenshots-review/discover-history";
fs.mkdirSync(OUT, { recursive: true });

const HISTORY = {
  items: [
    {
      id: "intent-usdt-history",
      title: "Historical USDT transactions",
      kind: "intent",
      status: "pending_approval",
      summary: "BigQuery historical transaction request prepared",
      candidate_key: "source:twse_mops:mops_taiwan",
      job_id: "job-usdt-history",
      updated_at: "2026-07-18T15:30:00Z",
    },
    {
      id: "collect-stablecoin-attention",
      title: "Historical stablecoin attention",
      kind: "collection_run",
      status: "running",
      summary: "Latest verified range: 2022-06-30",
      updated_at: "2026-07-18T15:20:00Z",
    },
    {
      id: "failed-governance",
      title: "Taiwan governance source",
      kind: "collection_run",
      status: "failed",
      summary: "Provider endpoint rejected the configured route",
      updated_at: "2026-07-18T15:10:00Z",
    },
    {
      id: "registered-tickers",
      title: "SEC company tickers",
      kind: "collection_run",
      status: "query_ready",
      summary: "Registry confirmed; Library asset available",
      updated_at: "2026-07-18T15:00:00Z",
    },
    {
      id: "schedule-twse",
      title: "TWSE refresh",
      kind: "subscription",
      status: "scheduled",
      cadence: "Every Monday at 10:00",
      execution_mode: "non_executing",
      summary: "Request saved; automatic execution not claimed",
      updated_at: "2026-07-18T14:50:00Z",
    },
  ],
};

const JOBS = {
  jobs: [
    {
      id: "job-usdt-history",
      status: "pending_approval",
      candidate_key: "source:twse_mops:mops_taiwan",
      connector_id: "example_com_data",
      plan: { title: "Historical USDT transactions" },
      request: { candidate_key: "source:twse_mops:mops_taiwan" },
    },
  ],
};

async function shot(page, label) {
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

test.describe("Discover History visual acceptance", () => {
  test("durable lifecycle selection stays in the rail", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockV2Api(page, { jobsBody: JOBS, historyBody: HISTORY });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByRole("tab", { name: /History/ }).click();

    const ledger = page.getByTestId("discover-history");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(ledger.getByRole("heading", { name: "Needs you" })).toBeVisible();
    await expect(ledger.getByRole("heading", { name: "Research lifecycle" })).toBeVisible();
    await expect(rail).toContainText("Historical USDT transactions");
    await expect(rail).toContainText("Approval required");
    await shot(page, "01-desktop-needs-you");

    await ledger.getByRole("button", { name: /Historical stablecoin attention/i }).click();
    await expect(rail).toContainText("Collecting");
    await shot(page, "02-desktop-active-detail");

    await ledger.getByRole("button", { name: "Recovery", exact: true }).click();
    await expect(ledger).toContainText("Taiwan governance source");
    await expect(rail).toContainText("Recovery required");
    await shot(page, "03-desktop-recovery-detail");

    await ledger.getByRole("button", { name: "Scheduled", exact: true }).click();
    await expect(rail).toContainText("Scheduled refresh");
    await expect(rail).toContainText(/Automatic execution is not claimed/i);
    await shot(page, "04-desktop-scheduled-detail");

    await rail.getByRole("button", { name: "Ask about this" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-head")).toContainText("lifecycle item");
    await expect(rail.getByTestId("ask-messages")).toContainText("Lifecycle context received for TWSE refresh");
    await shot(page, "05-desktop-history-ask");
  });
});
