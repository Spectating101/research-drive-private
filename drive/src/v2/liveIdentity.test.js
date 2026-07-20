import test from "node:test";
import assert from "node:assert/strict";
import { applyLiveIdentity, identityLookupFromRow, liveIdentityBadge } from "./liveIdentity.js";
import { statusPillKind } from "./datasetMeta.js";

test("registered live identity never becomes Query ready", () => {
  const identity = {
    dataset_id: "day2_deploy_smoke_20260720",
    readiness: "registered",
    worker_id: "windows-01",
    run_id: "run-abc",
    job_id: "day2-deploy-smoke-20260720a",
    synthesis_expectation: { badge: "Registered", not_badge: "Query ready" },
  };
  assert.deepEqual(liveIdentityBadge(identity), { kind: "registered", label: "Registered" });
  const view = applyLiveIdentity({ dataset_id: "day2_deploy_smoke_20260720" }, identity);
  assert.equal(view.analysis_readiness, "registered");
  assert.equal(statusPillKind(view).label, "Registered");
  assert.notEqual(statusPillKind(view).label, "Query ready");
});

test("query_ready live identity keeps Query ready badge", () => {
  const identity = {
    dataset_id: "panel_x",
    readiness: "query_ready",
    synthesis_expectation: { badge: "Query ready" },
  };
  const view = applyLiveIdentity({ dataset_id: "panel_x" }, identity);
  assert.equal(statusPillKind(view).kind, "query-ready");
  assert.equal(statusPillKind(view).label, "Query ready");
});

test("identity lookup prefers explicit dataset and job ids", () => {
  assert.deepEqual(
    identityLookupFromRow({
      dataset_id: "ds1",
      event: { meta: { job_id: "job-1" } },
    }),
    { datasetId: "ds1", jobId: "job-1" },
  );
});
