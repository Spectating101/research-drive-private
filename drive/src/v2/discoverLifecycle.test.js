import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  LIFECYCLE,
  applyLifecycleToEvaluation,
  buildDiscoverLifecycle,
  classifyJobLifecycle,
  exactJobsForCandidate,
  projectDiscoverCandidateLifecycle,
  selectLifecycleJob,
} from "./discoverLifecycle.js";
import { buildDiscoverEvaluation } from "./discoverEvaluation.js";

const ROW = {
  candidate_key: "dataset:mops_financial_statements_ext",
  dataset_id: "mops_financial_statements_ext",
  title: "MOPS financial statements",
  url: "https://mops.twse.com.tw/example",
  connector_id: "mops_tw",
};

function job(partial) {
  return {
    id: partial.id || "job-1",
    status: partial.status,
    candidate_key: Object.prototype.hasOwnProperty.call(partial, "candidate_key")
      ? partial.candidate_key
      : ROW.candidate_key,
    connector_id: Object.prototype.hasOwnProperty.call(partial, "connector_id")
      ? partial.connector_id
      : "mops_tw",
    created_at: partial.created_at || "2026-07-01T00:00:00Z",
    updated_at: partial.updated_at || partial.created_at || "2026-07-01T00:00:00Z",
    error: partial.error || "",
    result: partial.result || {},
    registered_dataset_id: Object.prototype.hasOwnProperty.call(partial, "registered_dataset_id")
      ? partial.registered_dataset_id
      : null,
    plan: partial.plan || { title: "MOPS financial statements" },
    request: partial.request || {},
  };
}

describe("exact candidate↔job linkage", () => {
  it("links by exact candidate_key", () => {
    const jobs = [job({ status: "queued", candidate_key: ROW.candidate_key })];
    assert.equal(exactJobsForCandidate(ROW, jobs).length, 1);
  });

  it("does not link title-only similar job", () => {
    const jobs = [
      job({
        status: "pending_approval",
        candidate_key: null,
        connector_id: null,
        plan: { title: "MOPS financial statements" },
      }),
    ];
    assert.equal(exactJobsForCandidate(ROW, jobs).length, 0);
    assert.equal(selectLifecycleJob(ROW, jobs), null);
  });

  it("prefers active nonterminal over older terminal", () => {
    const jobs = [
      job({
        id: "old-failed",
        status: "failed",
        updated_at: "2026-07-01T00:00:00Z",
        error: "boom",
      }),
      job({
        id: "active",
        status: "running",
        updated_at: "2026-07-02T00:00:00Z",
      }),
    ];
    assert.equal(selectLifecycleJob(ROW, jobs).id, "active");
  });

  it("uses newest exact terminal when no active job", () => {
    const jobs = [
      job({
        id: "older",
        status: "failed",
        updated_at: "2026-07-01T00:00:00Z",
        error: "a",
      }),
      job({
        id: "newer",
        status: "completed",
        updated_at: "2026-07-03T00:00:00Z",
        registered_dataset_id: null,
      }),
    ];
    assert.equal(selectLifecycleJob(ROW, jobs).id, "newer");
  });
});

describe("classifyJobLifecycle", () => {
  it("approval-required only from pending_approval", () => {
    const c = classifyJobLifecycle(job({ status: "pending_approval" }));
    assert.equal(c.state, LIFECYCLE.APPROVAL_REQUIRED);
    assert.equal(c.primaryAction.id, "review_approval");
  });

  it("queued is not running", () => {
    const c = classifyJobLifecycle(job({ status: "queued" }));
    assert.equal(c.state, LIFECYCLE.QUEUED);
    assert.notEqual(c.state, LIFECYCLE.RUNNING);
  });

  it("running does not invent percentage", () => {
    const c = classifyJobLifecycle(
      job({
        status: "running",
        result: { stage: "Downloading files" },
        updated_at: "2026-07-10T14:32:00Z",
      }),
    );
    assert.equal(c.state, LIFECYCLE.RUNNING);
    assert.ok(c.evidence.some((e) => e.label === "Stage"));
    assert.equal(
      c.evidence.some((e) => /%|percent/i.test(e.label + e.value)),
      false,
    );
  });

  it("failed remains failed with summary", () => {
    const c = classifyJobLifecycle(job({ status: "failed", error: "HTTP 403 from source" }));
    assert.equal(c.state, LIFECYCLE.FAILED);
    assert.match(c.explanation, /403/);
  });

  it("completed without registered_dataset_id = registration pending", () => {
    const c = classifyJobLifecycle(job({ status: "completed", registered_dataset_id: null }));
    assert.equal(c.state, LIFECYCLE.COMPLETED_UNREGISTERED);
  });

  it("registered_dataset_id = Registered in Library", () => {
    const c = classifyJobLifecycle(
      job({ status: "completed", registered_dataset_id: "mops_financial_statements_2026" }),
      { catalog: [{ dataset_id: "mops_financial_statements_2026" }] },
    );
    assert.equal(c.state, LIFECYCLE.REGISTERED);
    assert.equal(c.primaryAction.id, "open_library");
  });

  it("registered without query readiness is not Query ready", () => {
    const c = classifyJobLifecycle(
      job({ status: "completed", registered_dataset_id: "mops_financial_statements_2026" }),
      {
        catalog: [
          {
            dataset_id: "mops_financial_statements_2026",
            analysis_readiness: "metadata_search",
          },
        ],
      },
    );
    assert.equal(c.state, LIFECYCLE.REGISTERED);
    assert.notEqual(c.state, LIFECYCLE.QUERY_READY);
  });

  it("registered query-ready asset = In Library · Query ready", () => {
    const c = classifyJobLifecycle(
      job({ status: "completed", registered_dataset_id: "mops_panel" }),
      {
        catalog: [{ dataset_id: "mops_panel", analysis_readiness: "instant" }],
      },
    );
    assert.equal(c.state, LIFECYCLE.QUERY_READY);
    assert.equal(c.label, "In Library · Query ready");
  });
});

describe("buildDiscoverLifecycle", () => {
  it("submitting disables premature queued claim", () => {
    const life = buildDiscoverLifecycle({ row: ROW, jobs: [], submitting: true });
    assert.equal(life.state, LIFECYCLE.SUBMITTING);
  });

  it("failed exact job stays visible over acquisition default", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "failed", error: "timeout" })],
    });
    assert.equal(life.state, LIFECYCLE.FAILED);
  });

  it("refresh failure preserves last known state", () => {
    const lastKnown = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "running" })],
    });
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [],
      refreshFailed: true,
      lastKnown,
    });
    assert.equal(life.state, LIFECYCLE.RUNNING);
    assert.equal(life.refreshFailed, true);
  });

  it("does not reuse lastKnown across different candidate_key", () => {
    const rowA = ROW;
    const rowB = {
      ...ROW,
      candidate_key: "dataset:other_source",
      dataset_id: "other_source",
      connector_id: "other_tw",
    };
    const lastKnown = buildDiscoverLifecycle({
      row: rowA,
      jobs: [job({ status: "running" })],
    });
    assert.equal(lastKnown.state, LIFECYCLE.RUNNING);
    const lifeB = buildDiscoverLifecycle({
      row: rowB,
      jobs: [],
      refreshFailed: true,
      lastKnown,
    });
    assert.equal(lifeB, null);
  });

  it("queued stages do not include approval", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "queued" })],
    });
    assert.deepEqual(life.stages, ["submitted", "queue"]);
    assert.equal(life.stages.includes("approval"), false);
  });

  it("running stages do not include approval", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "running" })],
    });
    assert.deepEqual(life.stages, ["submitted", "queue", "running"]);
    assert.equal(life.stages.includes("approval"), false);
  });

  it("approval-required stages include approval", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "pending_approval" })],
    });
    assert.ok(life.stages.includes("approval"));
  });
});

describe("projectDiscoverCandidateLifecycle (A4)", () => {
  it("projects query-ready as in-lab + query-ready, not external", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [
        job({
          status: "completed",
          registered_dataset_id: "mops_panel",
          result: { query_ready: true },
        }),
      ],
    });
    const projected = projectDiscoverCandidateLifecycle(ROW, life);
    assert.equal(projected.discover_taxonomy.key, "local-query-ready");
    assert.match(projected.discover_taxonomy.label, /Query ready/i);
    assert.equal(projected.candidate_key, ROW.candidate_key);
  });

  it("projects registered as in-lab, not query-ready", () => {
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "completed", registered_dataset_id: "mops_panel" })],
      catalog: [{ dataset_id: "mops_panel", analysis_readiness: "metadata_search" }],
    });
    assert.equal(life.state, LIFECYCLE.REGISTERED);
    const projected = projectDiscoverCandidateLifecycle(ROW, life);
    assert.equal(projected.discover_taxonomy.key, "local-connected");
    assert.match(projected.discover_taxonomy.label, /Registered/i);
    assert.notEqual(projected.discover_taxonomy.key, "local-query-ready");
  });

  it("does not project approval/queued/running into local holdings", () => {
    for (const status of ["pending_approval", "queued", "running", "failed"]) {
      const life = buildDiscoverLifecycle({
        row: ROW,
        jobs: [job({ status, error: status === "failed" ? "x" : "" })],
      });
      const projected = projectDiscoverCandidateLifecycle(ROW, life);
      assert.equal(projected.discover_taxonomy, undefined);
    }
  });
});

describe("applyLifecycleToEvaluation (A4)", () => {
  it("terminal query-ready overrides stale external decision and unknowns", () => {
    const evaluation = buildDiscoverEvaluation(ROW, new Set(), null);
    assert.match(evaluation.decision.headline, /Acquisition available|External/i);
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [
        job({
          status: "completed",
          registered_dataset_id: "mops_panel",
          result: { query_ready: true },
        }),
      ],
    });
    const next = applyLifecycleToEvaluation(evaluation, life);
    assert.equal(next.decision.headline, "In Library · Query ready");
    assert.equal(next.taxonomyKey, "local-query-ready");
    assert.equal(
      next.unknowns.some((u) => /endpoint not probed|Acquisition constraints/i.test(u)),
      false,
    );
  });

  it("registered overrides decision without claiming query-ready", () => {
    const evaluation = buildDiscoverEvaluation(ROW, new Set(), null);
    const life = buildDiscoverLifecycle({
      row: ROW,
      jobs: [job({ status: "completed", registered_dataset_id: "mops_panel" })],
    });
    const next = applyLifecycleToEvaluation(evaluation, life);
    assert.equal(next.decision.headline, "Registered in Library");
    assert.notEqual(next.taxonomyKey, "local-query-ready");
    assert.equal(
      next.unknowns.some((u) => /endpoint not probed|Acquisition constraints/i.test(u)),
      false,
    );
    assert.ok(next.unknowns.some((u) => /query path|Instant query/i.test(u)));
  });
});
