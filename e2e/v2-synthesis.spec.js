import { mkdirSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const renderDir = "artifacts/synthesis-renders";

const EXPLORING_THREAD = {
  id: "thread-attention",
  session_id: "synthesis-session-attention",
  created_at: "2026-07-19T08:00:00+00:00",
  updated_at: "2026-07-19T08:00:00+00:00",
  title: "Historical stablecoin attention",
  objective: "Construct a defensible longitudinal attention signal for stablecoins from held and reachable evidence.",
  materialisation: "not_materialised",
  state: {
    title: "Historical stablecoin attention",
    objective: "Construct a defensible longitudinal attention signal for stablecoins from held and reachable evidence.",
    required_grain: "asset × week",
    maturity: "exploring",
    maturityLabel: "Evidence mapping",
    lastActivity: "Use GDELT as a validation signal.",
    materialisation: "not_materialised",
    nodes: [
      { id: "target", type: "target", layer: "target", label: "Historical stablecoin attention", interpretation: "A longitudinal public-attention signal.", grain: "asset-week", coverage: "2021–2026" },
      { id: "trends", type: "construct", layer: "evidence", label: "Search intent", role: "Core signal", status: "held", grain: "asset-week", coverage: "2021–2026" },
      { id: "reddit", type: "construct", layer: "evidence", label: "Community activity", role: "Core signal", status: "held", grain: "asset-week", coverage: "2021–2026" },
      { id: "gdelt", type: "source", layer: "evidence", label: "GDELT news", role: "Validation", status: "queryable", grain: "event-day", coverage: "2018–present" },
    ],
    edges: [],
    proposal: null,
    execution_spec: null,
    execution: null,
  },
};

const PROPOSAL_THREAD = {
  id: "thread-proposal",
  created_at: "2026-07-19T08:01:00+00:00",
  updated_at: "2026-07-19T08:01:00+00:00",
  title: "Weekly trust panel",
  objective: "Aggregate held stablecoin evidence at weekly grain.",
  materialisation: "not_materialised",
  state: {
    title: "Weekly trust panel",
    objective: "Aggregate held stablecoin evidence at weekly grain.",
    required_grain: "asset × week",
    maturity: "review",
    maturityLabel: "Method review",
    lastActivity: "A bounded weekly aggregate was proposed.",
    nodes: [
      {
        id: "stablecoin_trust_engagement_weekly",
        type: "source",
        layer: "evidence",
        label: "Stablecoin trust and engagement",
        role: "Held input",
        status: "held",
        grain: "asset-week",
        coverage: "2021–2026",
      },
    ],
    edges: [],
    proposal: {
      id: "proposal-weekly-v1",
      proposal_hash: "sha256:proposal-weekly-v1",
      title: "Aggregate held weekly panel",
      summary: "Aggregate the held evidence by week and preserve the input identity.",
      execution_preflight: { ok: true },
      operations: [{ op: "update_spec", summary: "Use weekly aggregation and bounded metrics." }],
      execution_spec: {
        input_dataset_id: "stablecoin_trust_engagement_weekly",
        output_dataset_id: "stablecoin_attention_weekly",
        group_by: ["asset_id", "week"],
        metrics: [{ field: "attention", aggregate: "mean" }],
      },
    },
    limitations: [
      "Search interest is a proxy for attention, not directly observed investor belief.",
      "Weekly aggregation can hide short-lived event reactions.",
    ],
  },
};

const REGISTERED_THREAD = {
  id: "thread-registered",
  created_at: "2026-07-19T08:02:00+00:00",
  updated_at: "2026-07-19T08:02:00+00:00",
  title: "Stablecoin attention weekly panel",
  objective: "Construct a reusable weekly public-attention panel.",
  materialisation: "registered",
  state: {
    title: "Stablecoin attention weekly panel",
    objective: "Construct a reusable weekly public-attention panel.",
    required_grain: "asset × week",
    maturity: "registered",
    maturityLabel: "Registered output",
    lastActivity: "Registered synthesis output is available in Library.",
    nodes: [],
    edges: [],
    proposal: null,
    execution_spec: {
      input_dataset_id: "stablecoin_trust_engagement_weekly",
      output_dataset_id: "stablecoin_attention_weekly",
      group_by: ["asset_id", "week"],
      metrics: [{ field: "attention", aggregate: "mean" }],
    },
    execution: {
      status: "registered",
      job_id: "job-synthesis-42",
      output_dataset_id: "stablecoin_attention_weekly",
      rows: 13827,
      drive_verified: true,
      manifest_id: "mft_s04_0726",
    },
  },
};

const QUERY_READY_THREAD = {
  ...structuredClone(REGISTERED_THREAD),
  id: "thread-query-ready",
  title: "Query-ready stablecoin attention panel",
  materialisation: "query_ready",
  state: {
    ...structuredClone(REGISTERED_THREAD.state),
    title: "Query-ready stablecoin attention panel",
    maturity: "query_ready",
    maturityLabel: "Query-ready output",
    lastActivity: "Registered output passed query-engine readiness checks.",
    execution: {
      ...structuredClone(REGISTERED_THREAD.state.execution),
      status: "query_ready",
      job_id: "job-synthesis-43",
      output_dataset_id: "stablecoin_attention_query_ready",
    },
  },
};

async function capture(page, name) {
  mkdirSync(renderDir, { recursive: true });
  await page.screenshot({ path: `${renderDir}/${name}.png`, fullPage: true });
}

async function installSynthesisThreadMock(page) {
  const threads = new Map(
    [EXPLORING_THREAD, PROPOSAL_THREAD, REGISTERED_THREAD, QUERY_READY_THREAD].map((thread) => [thread.id, structuredClone(thread)]),
  );

  await page.route("**/api/library/synthesis/threads**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/").filter(Boolean);
    const threadIndex = parts.lastIndexOf("threads");
    const threadId = parts[threadIndex + 1] || "";
    const suffix = parts.slice(threadIndex + 2).join("/");
    const method = route.request().method();
    const respond = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (!threadId && method === "GET") return respond({ threads: [...threads.values()], total: threads.size });
    if (!threadId && method === "POST") {
      const body = route.request().postDataJSON?.() || {};
      const id = `thread-${threads.size + 1}`;
      const thread = {
        id,
        created_at: "2026-07-19T09:00:00+00:00",
        updated_at: "2026-07-19T09:00:00+00:00",
        title: body.objective,
        objective: body.objective,
        materialisation: "not_materialised",
        state: { title: body.objective, objective: body.objective, required_grain: body.required_grain || "", maturity: "exploring", maturityLabel: "Exploring", lastActivity: "Thread created.", nodes: [], edges: [], proposal: null },
      };
      threads.set(id, thread);
      return respond(thread);
    }

    const thread = threads.get(threadId);
    if (!thread) return respond({ error: "not found" }, 404);
    if (!suffix && method === "GET") return respond(thread);
    if (suffix === "patches" && method === "POST") {
      const body = route.request().postDataJSON?.() || {};
      const proposal = thread.state.proposal;
      if (!proposal || body.proposal_id !== proposal.id || body.proposal_hash !== proposal.proposal_hash) {
        return respond({ error: "Synthesis proposal changed; refresh before accepting" }, 409);
      }
      if (body.decision === "accept") {
        thread.state.execution_spec = proposal.execution_spec;
        thread.state.proposal = null;
        thread.state.maturity = "planned";
        thread.state.maturityLabel = "Accepted method";
        thread.state.lastActivity = "Accepted proposal: Aggregate held weekly panel.";
      } else {
        thread.state.proposal = null;
        thread.state.lastActivity = "Proposal rejected.";
      }
      thread.updated_at = "2026-07-19T09:01:00+00:00";
      return respond(thread);
    }
    if (suffix === "conversation" && method === "POST") {
      const body = route.request().postDataJSON?.() || {};
      thread.session_id = body.session_id || "";
      return respond(thread);
    }
    if (suffix === "execute" && method === "POST") {
      thread.state.execution = {
        status: "pending_approval",
        job_id: "job-synthesis-pending",
        output_dataset_id: thread.state.execution_spec?.output_dataset_id || "",
      };
      thread.state.lastActivity = "Execution request is awaiting approval.";
      thread.updated_at = "2026-07-19T09:02:00+00:00";
      return respond({ job: { id: "job-synthesis-pending", status: "pending_approval" }, thread });
    }
    if (suffix === "materialisation" && method === "GET") {
      const execution = thread.state.execution || {};
      return respond({ thread_id: thread.id, materialisation: thread.materialisation, output_registered: execution.status === "registered", output_dataset_id: execution.output_dataset_id || "" });
    }
    return respond({ error: "unsupported mock route" }, 400);
  });

  await page.route("**/api/library/chat/synthesis-session-attention", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "synthesis-session-attention",
        messages: [
          {
            role: "user",
            content: "Keep the primary horizon weekly.",
            artifacts: {},
          },
          {
            role: "assistant",
            content: "The weekly horizon is attached to this project; daily evidence still requires an explicit aggregation rule.",
            artifacts: { action: "synthesis_reasoning" },
          },
        ],
      }),
    }),
  );
}

test.describe("v2 Synthesis durable thread surface", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await installSynthesisThreadMock(page);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("renders the selected durable thread in the workspace and Detail rail", async ({ page }) => {
    await expect(page.getByTestId("synthesis-evidence-state")).toContainText("Historical stablecoin attention");
    await expect(page.getByTestId("synthesis-evidence-state")).toContainText("Search intent");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Historical stablecoin attention");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("3 mapped inputs");
    await expect(page.getByTestId("rail-pane-ask")).toBeHidden();
    await expect(page.getByText("Nothing registered", { exact: true })).toBeVisible();
    await capture(page, "01-durable-evidence-desktop");
  });

  test("accepts a revision-bound proposal, then requests but does not fabricate execution", async ({ page }) => {
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Weekly trust panel" }).click();
    const proposal = page.getByTestId("synthesis-proposal-state");
    await expect(proposal).toContainText("Aggregate held weekly panel");
    await expect(proposal).toContainText("Held input");
    await expect(proposal).toContainText("Proposed output");
    await expect(proposal).toContainText("Nothing is materialised yet");
    await expect(proposal).toContainText("Still not established");
    await capture(page, "02-proposal-review-desktop");
    await page.getByRole("button", { name: "Accept proposal" }).click();
    await expect(page.getByTestId("synthesis-execution-state")).toContainText("stablecoin_attention_weekly");
    await page.getByRole("button", { name: "Request execution" }).click();
    const pending = page.getByTestId("synthesis-execution-state");
    await expect(pending).toContainText("pending approval");
    await expect(pending.getByRole("button", { name: "Review approval" })).toBeVisible();
    await expect(pending.getByRole("button", { name: "Request execution" })).toHaveCount(0);
    await expect(pending).toContainText("Researcher approval");
    await expect(pending).toContainText("Archive + registry");
    await expect(pending.getByText("Query ready", { exact: true })).toHaveCount(0);
    await capture(page, "03-execution-request-desktop");
    await pending.getByRole("button", { name: "Review approval" }).click();
    await expect(page).toHaveURL(/tab=browse/);
    await expect(page).toHaveURL(/mode=history/);
  });

  test("renders registered output only from thread registration evidence", async ({ page }) => {
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Stablecoin attention weekly panel" }).click();
    const registered = page.getByTestId("synthesis-registered-state");
    await expect(registered).toContainText("13,827");
    await expect(registered).toContainText("mft_s04_0726");
    await expect(registered).toContainText("Reported verified");
    await expect(registered.getByText("Registered", { exact: true })).toBeVisible();
    await expect(registered.getByText("Query ready", { exact: true })).toHaveCount(0);
    await expect(registered.getByRole("button", { name: "Open in Library" })).toBeVisible();
    await expect(registered).toContainText("Library handoff");
    await expect(registered).toContainText("Registered");
    await capture(page, "04-registered-desktop");
  });

  test("renders query-ready only from an explicit query-ready lifecycle", async ({ page }) => {
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Query-ready stablecoin attention panel" }).click();
    const ready = page.getByTestId("synthesis-query-ready-state");
    await expect(ready.getByText("Query ready", { exact: true })).toBeVisible();
    await expect(ready).toContainText("Query-ready output reported");
    await expect(ready.getByRole("button", { name: "Open in Library" })).toBeVisible();
  });

  test("sends the selected durable thread to the shared Ask rail", async ({ page }) => {
    await page.getByRole("button", { name: "Discuss construction in Ask" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Ask · synthesis thread");
    await expect(rail).toContainText("Keep the primary horizon weekly.");
    await expect(rail).toContainText("Provisionally, Historical stablecoin attention");
    await expect(rail).toContainText("construct validity and time alignment");
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("rail-pane-detail")).toBeHidden();
    await expect(rail.getByTestId("ask-composer")).toHaveAttribute(
      "placeholder",
      "Correct the interpretation, add a constraint, or ask…",
    );
    await capture(page, "05-shared-ask-desktop");
  });

  test("creates a durable thread before handing the objective to Ask", async ({ page }) => {
    await page.getByRole("button", { name: "+ New" }).click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Synthesis studio");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Historical stablecoin attention");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Keep the primary horizon weekly.");
    await expect(page.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await page.waitForTimeout(250);
    await capture(page, "06-new-project-entry-desktop");
    const objective = "Construct a weekly issuer attention panel for Taiwan filings.";
    await page.getByTestId("synthesis-intent-state").getByRole("textbox").fill(objective);
    await page.getByRole("button", { name: "Start project in Ask" }).click();
    await expect(page.getByText(objective, { exact: true }).first()).toBeVisible();
    await expect(page.getByTestId("synthesis-draft-state")).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Ask · synthesis thread");
    await expect(page.locator("aside.rd-v2-rail")).toContainText(`Provisionally, ${objective}`);
    await expect(page.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await page.waitForTimeout(250);
    await capture(page, "07-new-project-ask-desktop");
  });

  test("keeps the right rail usable on mobile while the workspace remains source-backed", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("synthesis-evidence-state")).toBeVisible();
    await expect(page.locator(".rd-v2-sidebar-foot-nav")).toBeHidden();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      .toBe(true);
    await capture(page, "08-durable-evidence-mobile");
    await page.getByRole("button", { name: /Show Detail.*Ask|Hide panel/ }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toBeVisible();
    await expect.poll(async () => (await rail.boundingBox())?.height || 0).toBeGreaterThan(600);
    await expect(rail.getByTestId("rail-pane-detail")).toBeVisible();
    await expect(rail).toContainText("3 mapped inputs");
    await capture(page, "09-detail-sheet-mobile");
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.getByTestId("rail-pane-detail")).toBeHidden();
    await expect(rail.getByTestId("ask-composer")).toBeVisible();
    await page.waitForTimeout(250);
    await capture(page, "10-ask-sheet-mobile");
  });

  test("keeps proposal review legible on mobile without flattening the method flow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Weekly trust panel" }).click();
    const proposal = page.getByTestId("synthesis-proposal-state");
    await expect(proposal).toContainText("Held input");
    await expect(proposal).toContainText("Construction");
    await expect(proposal).toContainText("Proposed output");
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      .toBe(true);
    await capture(page, "11-proposal-review-mobile");
  });
});
