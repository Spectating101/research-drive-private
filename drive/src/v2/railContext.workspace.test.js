import assert from "node:assert/strict";
import test from "node:test";
import { buildRailContext } from "./railContext.js";

test("Discover workspace carries open Explore query and summary into Ask rail", () => {
  const ctx = buildRailContext({
    tab: "browse",
    mode: "ask",
    searchQuery: "Taiwan stock prices",
    discoverMode: "explore",
    discoverSummary: {
      query: "Taiwan stock prices",
      held: 0,
      offerings: 3,
      webContext: 0,
      engine: "hands_routes",
      next_action: "collect_route",
      summary: "Desk can collect via 3 declared route(s).",
      route_titles: [{ title: "TWSE Open API", source_id: "twse_official" }],
    },
  });
  assert.equal(ctx.surface, "discover");
  assert.equal(ctx.workspace.surface, "discover");
  assert.equal(ctx.workspace.query, "Taiwan stock prices");
  assert.equal(ctx.workspace.engine, "hands_routes");
  assert.equal(ctx.workspace.next_action, "collect_route");
  assert.equal(ctx.workspace.routes[0].source_id, "twse_official");
});

test("Synthesis workspace carries open proposal into Ask rail", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_1",
      title: "Stablecoin trust construct",
      thread: {
        objective: "Join trust and engagement panels",
        state: {
          maturity: "draft",
          objective: "Join trust and engagement panels",
          proposal: {
            id: "prop_1",
            title: "Weekly join",
            summary: "Join at week grain",
            proposal_hash: "abc",
          },
        },
      },
    },
  });
  assert.equal(ctx.surface, "synthesis");
  assert.equal(ctx.thread_id, "thr_1");
  assert.equal(ctx.workspace.thread_id, "thr_1");
  assert.match(String(ctx.workspace.objective || ""), /trust/i);
  assert.equal(ctx.workspace.proposal_id, "prop_1");
  assert.equal(ctx.workspace.proposal.id, "prop_1");
  assert.match(String(ctx.workspace.proposal.summary || ""), /week/i);
});

test("Synthesis workspace offers request_execution after accepted method", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_2",
      title: "Keeling accel",
      thread: {
        objective: "Build monthly acceleration",
        state: {
          maturity: "exploring",
          objective: "Build monthly acceleration",
          proposal: null,
          spec: { purpose: "accel", grain: "month" },
          nodes: [{ id: "src", type: "source" }],
        },
      },
    },
  });
  assert.equal(ctx.workspace.has_method, true);
  assert.equal(ctx.workspace.can_request_execution, undefined);
  assert.equal(ctx.workspace.method_not_executable, true);
});

test("Synthesis workspace offers request_execution only with bounded execution_spec", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_3",
      title: "Aggregate panel",
      thread: {
        objective: "Weekly mean trust",
        state: {
          maturity: "exploring",
          proposal: null,
          execution_spec: {
            input_dataset_id: "stablecoin_trust_engagement_weekly",
            output_dataset_id: "synthesis_trust_week_mean",
            metrics: [{ function: "mean", column: "trust", as: "trust_mean" }],
          },
        },
      },
    },
  });
  assert.equal(ctx.workspace.can_request_execution, true);
  assert.equal(ctx.workspace.method_not_executable, undefined);
});

test("Synthesis workspace offers request_execution for row_output lag transforms", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_4",
      title: "Keeling lag",
      thread: {
        objective: "Monthly lag CO2",
        state: {
          maturity: "exploring",
          proposal: null,
          execution_spec: {
            input_dataset_id: "keeling_co2_monthly",
            output_dataset_id: "synthesis_keeling_lag12",
            row_output: true,
            transforms: [{ op: "lag", column: "co2", periods: 12, as: "co2_lag12" }],
          },
        },
      },
    },
  });
  assert.equal(ctx.workspace.can_request_execution, true);
  assert.equal(ctx.workspace.method_not_executable, undefined);
});

test("Synthesis workspace does not re-offer execution when output is already query-ready", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_keeling",
      title: "Monthly Keeling Curve acceleration",
      thread: {
        objective: "Build monthly acceleration",
        materialisation: "query_ready",
        state: {
          maturity: "query_ready",
          proposal: null,
          materialisation: "query_ready",
          execution_spec: {
            input_dataset_id: "keeling_mlo_monthly_clean",
            output_dataset_id: "synthesis_keeling_accel_monthly_v1",
            row_output: true,
            transforms: [{ op: "diff", column: "sa_ppm", periods: 12, as: "annual_rate_ppm" }],
          },
          execution: {
            status: "query_ready",
            output_dataset_id: "synthesis_keeling_accel_monthly_v1",
            query_ready: true,
          },
        },
      },
    },
  });
  assert.equal(ctx.workspace.can_request_execution, undefined);
  assert.equal(ctx.workspace.output_ready, true);
  assert.equal(ctx.workspace.query_ready, true);
  assert.ok(ctx.actions.includes("open_output"));
  assert.equal(ctx.actions.includes("request_execution"), false);
});

test("Synthesis workspace does not re-offer execution when output is only registered", () => {
  const ctx = buildRailContext({
    tab: "synthesis",
    mode: "ask",
    activeObject: {
      kind: "synthesis_thread",
      id: "thr_reg",
      title: "Registered construct",
      thread: {
        materialisation: "registered",
        state: {
          proposal: null,
          materialisation: "registered",
          execution_spec: {
            input_dataset_id: "src_a",
            output_dataset_id: "out_b",
            metrics: [{ function: "mean", column: "x", as: "x_mean" }],
          },
          execution: { status: "registered", output_dataset_id: "out_b" },
        },
      },
    },
  });
  assert.equal(ctx.workspace.can_request_execution, undefined);
  assert.equal(ctx.workspace.output_ready, true);
  assert.equal(ctx.workspace.query_ready, undefined);
  assert.ok(ctx.actions.includes("open_output"));
});
