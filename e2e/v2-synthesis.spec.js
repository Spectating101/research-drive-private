import { mkdirSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const renderDir = "docs/status/generated/synthesis-workbench-visual";

const MOCK_SYNTHESIS = {
  profiles: [
    {
      id: "stablecoin_trust_engagement",
      title: "Stablecoin trust ↔ engagement",
      type: "trust_engagement",
      description: "Skynet + GDELT + DeFiLlama entity panels.",
      sources: ["Skynet", "GDELT", "DeFiLlama"],
      join_keys: ["entity_id", "date"],
      research_questions: ["Which entities lack on-chain coverage?"],
    },
  ],
  latest: {},
  count: 1,
};

const PROPOSAL = {
  id: "gdelt-validation",
  title: "Use GDELT as a validation signal",
  summary: "Add Google Trends + GDELT without claiming output.",
  proposal_hash: "hash-gdelt-1",
  operations: [
    {
      op: "add_node",
      node: {
        id: "trends",
        type: "source",
        layer: "evidence",
        label: "Google Trends",
        status: "held",
      },
    },
    {
      op: "add_node",
      node: {
        id: "gdelt",
        type: "source",
        layer: "evidence",
        label: "GDELT",
        status: "proposed",
      },
    },
    {
      op: "update_spec",
      patch: { grain: "asset-week", coreEvidence: ["Google Trends"], validation: ["GDELT"] },
    },
  ],
};

function emptyThread(overrides = {}) {
  return {
    id: "thread-durable-1",
    created_at: "2026-07-22T00:00:00+00:00",
    updated_at: "2026-07-22T00:00:00+00:00",
    title: "New synthesis",
    objective: "New synthesis — research measure pending Composer.",
    session_id: "syn-sess-durable-1",
    conversation_id: "",
    materialisation: "not_materialised",
    state: {
      title: "New synthesis",
      objective: "New synthesis — research measure pending Composer.",
      required_grain: "",
      maturity: "exploring",
      maturityLabel: "Exploring",
      lastActivity: "Thread created.",
      materialisation: "not_materialised",
      nodes: [],
      edges: [],
      proposal: null,
      decisions: [],
      activity: [{ time: "Now", kind: "create", message: "Synthesis thread created." }],
      spec: {
        purpose: "New synthesis — research measure pending Composer.",
        grain: "",
        coreEvidence: [],
        validation: [],
        unavailable: [],
        construction: [],
        limitations: [],
      },
      plannedColumns: [],
      chartIdeas: [],
    },
    execution_recorded: false,
    ...overrides,
  };
}

async function capture(page, name) {
  mkdirSync(renderDir, { recursive: true });
  await page.screenshot({ path: `${renderDir}/${name}.png`, fullPage: false });
}

test.describe("v2 Synthesis durable Composer workbench", () => {
  test("New synthesis opens durable thread with unformed Model and Composer rail", async ({ page }) => {
    const created = emptyThread();
    await mockV2Api(page, {
      synthesisProfiles: MOCK_SYNTHESIS,
      synthesisThreads: { threads: [], total: 0 },
      synthesisThreadCreate: created,
      chatComplete: {
        session_id: created.session_id,
        reply: "Ready to propose a construction when you describe the measure.",
        action: "answer",
        session_messages: [],
      },
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    await expect(page.getByTestId("synthesis-workbench")).toBeVisible();
    await expect(page.getByTestId("synthesis-state-empty")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("synthesis-construction-unformed")).toContainText(
      "Model stays empty until Composer returns a controlled proposal",
    );
    await expect(page.getByTestId("synthesis-session-draft")).toHaveCount(0);
    await expect(page.getByTestId("synthesis-thread-id")).toContainText(created.id);

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("tab", { name: "Composer" })).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Composer" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveCount(0);
    await expect(page.getByTestId("synthesis-composer-context")).toContainText(created.id);
    await expect(page.getByTestId("ask-composer")).toBeVisible();
    await expect(page.locator(".rd-v2-ask-status")).toHaveCount(0);

    await page.getByTestId("synthesis-workbench-tab-data").click();
    await expect(page.getByTestId("synthesis-data-empty")).toContainText("does not claim that collection ran");
    await page.getByTestId("synthesis-workbench-tab-output").click();
    await expect(page.getByTestId("synthesis-output-empty")).toContainText("No registered output");

    await capture(page, "desktop_1440_durable_unformed");
  });

  test("Composer shows thread messages; proposal renders Model; accept calls patches", async ({ page }) => {
    const base = emptyThread();
    const withProposal = {
      ...base,
      state: {
        ...base.state,
        proposal: PROPOSAL,
        maturityLabel: "Proposal awaiting review",
      },
    };
    let current = structuredClone(base);

    await mockV2Api(page, {
      synthesisProfiles: MOCK_SYNTHESIS,
      synthesisThreads: { threads: [base], total: 1 },
      synthesisThreadCreate: base,
      synthesisThreadById: (id) => (id === current.id ? structuredClone(current) : null),
      chatComplete: {
        session_id: base.session_id,
        reply: "Proposed Trends + GDELT as a controlled construction patch.",
        action: "composer",
        artifacts: {
          synthesis_proposal: PROPOSAL,
          synthesis_thread_id: base.id,
        },
        session_messages: [],
      },
    });

    // After chat completes, subsequent GET returns proposal.
    await page.route(/\/library\/synthesis\/threads\/thread-durable-1$/, async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(current),
      });
    });
    await page.route(/\/library\/synthesis\/threads\/thread-durable-1\/patches$/, async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const payload = route.request().postDataJSON();
      expect(payload.decision).toBe("accept");
      expect(payload.proposal_id).toBe(PROPOSAL.id);
      expect(payload.proposal_hash).toBe(PROPOSAL.proposal_hash);
      current = {
        ...withProposal,
        state: {
          ...withProposal.state,
          proposal: null,
          nodes: PROPOSAL.operations.filter((o) => o.op === "add_node").map((o) => o.node),
          spec: {
            ...withProposal.state.spec,
            grain: "asset-week",
            coreEvidence: ["Google Trends"],
            validation: ["GDELT"],
          },
          maturityLabel: "Accepted construction",
        },
      };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(current),
      });
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await expect(page.getByTestId("synthesis-thread-id")).toContainText(base.id);

    // Seed proposal onto thread and refresh via Composer send path.
    current = structuredClone(withProposal);
    await page.getByTestId("ask-composer").fill("Map Trends and GDELT for an attention measure.");
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByTestId("ask-messages")).toContainText("Proposed Trends + GDELT", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("synthesis-composer-user")).toContainText("Map Trends and GDELT");
    await expect(page.getByTestId("synthesis-state-proposed")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("synthesis-construction-map")).toContainText("Google Trends");
    await expect(page.getByTestId("synthesis-construction-map")).toContainText("GDELT");
    await expect(page.getByTestId("synthesis-proposal-card")).toContainText("Use GDELT as a validation signal");
    await expect(page.getByTestId("synthesis-composer-proposal")).toBeVisible();

    await page.getByTestId("synthesis-proposal-accept").click();
    await expect(page.getByTestId("synthesis-state-accepted")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("synthesis-proposal-card")).toHaveCount(0);
    await expect(page.getByTestId("synthesis-construction-map")).toContainText("Google Trends");

    await page.getByTestId("synthesis-workbench-tab-spec").click();
    await expect(page.getByTestId("synthesis-spec-state")).toHaveText("Accepted");
    await expect(page.getByTestId("synthesis-spec-grain")).toContainText("asset-week");

    await capture(page, "desktop_1440_proposal_accepted");
  });

  test("threads API failure keeps honest local-draft fallback", async ({ page }) => {
    await mockV2Api(page, {
      synthesisProfiles: MOCK_SYNTHESIS,
    });
    await page.route("**/library/synthesis/threads**", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "not found" }),
      }),
    );

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    await expect(page.getByTestId("synthesis-session-draft")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("synthesis-draft-note")).toContainText("Not saved thread history");
    await expect(page.getByTestId("synthesis-composer-context")).toContainText("Local draft");
    await page.getByTestId("synthesis-dir-trigger").click();
    await expect(page.getByTestId("synthesis-directory")).toContainText("local draft only");
    await capture(page, "desktop_1440_local_fallback");
  });
});
