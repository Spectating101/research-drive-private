import { mkdirSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const renderDir = "artifacts/synthesis-renders";

const EXPLORING_THREAD = {
  id: "thread-attention",
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
      { id: "filings", type: "source", layer: "evidence", label: "Regulatory filings", role: "Direct measure gap", status: "missing", grain: "issuer-quarter", coverage: "Not held" },
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
    nodes: [],
    edges: [],
    proposal: {
      id: "proposal-weekly-v1",
      proposal_hash: "sha256:proposal-weekly-v1",
      title: "Aggregate held weekly panel",
      summary: "Aggregate the held evidence by week and preserve the input identity.",
      operations: [{ op: "update_spec", summary: "Use weekly aggregation and bounded metrics." }],
      execution_spec: {
        input_dataset_id: "stablecoin_trust_engagement_weekly",
        output_dataset_id: "stablecoin_attention_weekly",
        group_by: ["asset_id", "week"],
        metrics: [{ field: "attention", aggregate: "mean" }],
      },
    },
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

  await page.route("**/api/library/jobs/job-synthesis-pending/approve", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const thread = threads.get("thread-proposal");
    thread.state.execution = {
      ...thread.state.execution,
      status: "queued",
    };
    thread.updated_at = "2026-07-19T09:03:00+00:00";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "job-synthesis-pending", status: "queued" }),
    });
  });

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
    if (suffix === "discover-handoff" && method === "GET") {
      return respond({
        thread_id: "thread-attention",
        objective: EXPLORING_THREAD.objective,
        required_grain: "asset × week",
        held_evidence: [{ id: "trends", label: "Search intent" }],
        missing_evidence: [{ id: "filings", label: "Regulatory filings", source_identity: "regulatory filings" }],
        collect_intents: [{ evidence_id: "filings", label: "Regulatory filings", source_identity: "regulatory filings", resolvable: false }],
        fake_collection: false,
      });
    }
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
    await expect(page.locator("aside.rd-v2-rail")).toContainText("4 mapped inputs");
    await expect(page.getByText("Nothing registered", { exact: true })).toBeVisible();
    await capture(page, "01-durable-evidence-desktop");
  });

  test("accepts a revision-bound proposal, then exposes one approval action without fabricating registration", async ({ page }) => {
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Weekly trust panel" }).click();
    await expect(page.getByTestId("synthesis-proposal-state")).toContainText("Aggregate held weekly panel");
    await page.getByRole("button", { name: "Accept proposal" }).click();
    const execution = page.getByTestId("synthesis-execution-state");
    await expect(execution).toContainText("stablecoin_attention_weekly");
    await expect(execution.getByRole("button", { name: "Approve and run" })).toBeVisible();
    await expect(execution.getByRole("button", { name: "Request execution" })).toHaveCount(0);
    await expect(execution.getByRole("button", { name: "Approve build" })).toHaveCount(0);
    await expect(execution.getByText("Query ready", { exact: true })).toHaveCount(0);
    await capture(page, "02-execution-request-desktop");
  });

  test("queues an approved synthesis build without fabricating a registered output", async ({ page }) => {
    await page.getByTestId("synthesis-thread-item").filter({ hasText: "Weekly trust panel" }).click();
    await page.getByRole("button", { name: "Accept proposal" }).click();

    const execution = page.getByTestId("synthesis-execution-state");
    await expect(execution.getByRole("button", { name: "Approve and run" })).toBeVisible();
    await execution.getByRole("button", { name: "Approve and run" }).click();

    const queued = page.getByTestId("synthesis-execution-state");
    await expect(queued).toContainText("queued");
    await expect(queued.getByRole("button", { name: "Open in Library" })).toHaveCount(0);
    await expect(queued.getByText("Query ready", { exact: true })).toHaveCount(0);
  });

  test("obtains a durable Discover handoff before routing a selected evidence gap to Discover", async ({ page }) => {
    await page.getByRole("button", { name: /Regulatory filings/ }).click();
    await expect(page.getByTestId("synthesis-selected-field")).toContainText("Regulatory filings");
    await capture(page, "07-selected-evidence-handoff-desktop");
    await page.getByRole("button", { name: "Route to Discover" }).click();
    await expect(page).toHaveURL(/tab=browse/);
    await expect(page.getByTestId("synthesis-discover-handoff")).toContainText("Regulatory filings");
    await expect(page.getByTestId("synthesis-discover-handoff")).toContainText("asset × week");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Continue Synthesis evidence search");
    await capture(page, "08-discover-handoff-desktop");
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("synthesis-discover-handoff")).toContainText("Regulatory filings");
  });

  test("keeps held evidence inspectable but does not route it as a missing-evidence handoff", async ({ page }) => {
    await page.getByRole("button", { name: /Search intent/ }).click();
    const selected = page.getByTestId("synthesis-selected-field");
    await expect(selected).toContainText("Search intent");
    await expect(selected.getByRole("button", { name: "Route to Discover" })).toHaveCount(0);
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
    await capture(page, "03-registered-desktop");
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
    await expect(page.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail).toContainText("Ask · synthesis thread");
    await expect(rail).toContainText("durable research construction");
    await expect(rail).not.toContainText("context received for");
    await expect(rail.getByTestId("ask-composer")).toHaveAttribute(
      "placeholder",
      "Correct the interpretation, add a constraint, or ask…",
    );
    await capture(page, "04-shared-ask-desktop");
  });

  test("creates a durable thread, opens Ask, and shows the thread-created decision card", async ({ page }) => {
    await page.getByRole("button", { name: "+ New" }).click();
    const objective = "Construct a weekly issuer attention panel for Taiwan filings.";
    await page.getByTestId("synthesis-intent-state").getByRole("textbox").fill(objective);
    await page.getByRole("button", { name: "Create thread & discuss" }).click();

    const created = page.getByTestId("synthesis-thread-created-state");
    await expect(created).toBeVisible();
    await expect(created).toContainText("Thread created");
    await expect(created).toContainText(objective);
    await expect(page.getByTestId("synthesis-empty-state")).toHaveCount(0);
    await expect(page.getByTestId("synthesis-blueprints")).toHaveCount(0);

    await expect(page.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Ask · synthesis thread");
    await expect(rail).toContainText(objective.slice(0, 24));
    await expect(rail.getByTestId("ask-messages")).toContainText("durable research construction");
    await expect(page.getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "false");
    await capture(page, "05-new-thread-ask-desktop");
  });

  test("shows recoverable Ask UI for provider linking failures on a Synthesis thread", async ({ page }) => {
    await page.getByRole("tab", { name: "Ask" }).click();
    await page.getByTestId("ask-composer").fill("force provider linking failure");
    await page.getByRole("button", { name: "Send" }).click();
    const recovery = page.getByTestId("ask-recovery-state");
    await expect(recovery).toBeVisible();
    await expect(recovery).toContainText("Assistant provider is unavailable");
    await expect(recovery).toContainText("objective is preserved");
    await expect(page.getByTestId("ask-messages")).not.toContainText("Provider not linked: composer is not configured");
    await capture(page, "09-ask-provider-recovery-desktop");
  });

  test("keeps the right rail usable on mobile while the workspace remains source-backed", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("synthesis-evidence-state")).toBeVisible();
    await page.getByRole("button", { name: /Show Detail.*Ask|Hide panel/ }).click();
    await expect(page.locator("aside.rd-v2-rail")).toBeVisible();
    await capture(page, "06-durable-evidence-mobile");
  });
});
