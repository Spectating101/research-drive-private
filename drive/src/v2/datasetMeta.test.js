import test from "node:test";
import assert from "node:assert/strict";
import { statusPillKind } from "./datasetMeta.js";

test("unknown readiness is never promoted to query ready", () => {
  assert.deepEqual(statusPillKind({ dataset_id: "unknown" }), {
    kind: "unknown",
    label: "Readiness unknown",
  });
  assert.deepEqual(statusPillKind({ dataset_id: "novel", analysis_readiness: "new_state" }), {
    kind: "unknown",
    label: "Readiness unknown",
  });
});

test("dataset readiness labels preserve the explicit access contract", () => {
  assert.equal(statusPillKind({ analysis_readiness: "instant" }).kind, "query-ready");
  assert.equal(statusPillKind({ analysis_readiness: "instant_or_minutes" }).kind, "query-ready");
  assert.equal(statusPillKind({ analysis_readiness: "query_ready" }).label, "Query ready");
  assert.equal(statusPillKind({ analysis_readiness: "registered" }).label, "Registered");
  assert.equal(statusPillKind({ analysis_readiness: "connected" }).kind, "connected");
  assert.equal(statusPillKind({ analysis_readiness: "dry_run_before_execution" }).kind, "connected");
  assert.equal(statusPillKind({ analysis_readiness: "metadata_search" }).label, "Metadata only");
  assert.equal(statusPillKind({ analysis_readiness: "metadata_only" }).label, "Metadata only");
  assert.equal(statusPillKind({ analysis_readiness: "procurement_planning" }).kind, "queued");
  assert.equal(statusPillKind({ analysis_readiness: "failed" }).kind, "failed");
});

test("external acquisition rows remain external regardless of readiness text", () => {
  assert.equal(statusPillKind({ collect_via: "web", analysis_readiness: "instant" }).kind, "external");
});
