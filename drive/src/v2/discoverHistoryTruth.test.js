import assert from "node:assert/strict";
import test from "node:test";
import {
  durableHistoryToEvents,
  historyEventForJob,
  historyHoldingTruth,
  historyLibraryHandoff,
  historyLifecycleBucket,
} from "./discoverAdapters.js";

test("durableHistoryToEvents preserves candidate/source/connector/job identities", () => {
  const [event] = durableHistoryToEvents({
    items: [
      {
        kind: "collection_run",
        id: "hist-1",
        title: "TWSE Open API",
        status: "pending_approval",
        updated_at: "2026-07-24T00:00:00Z",
        job_id: "job-abc",
        candidate_key: "source:taiwan_stock_exchange:twse_official",
        source_id: "twse_official",
        connector_id: "twse",
        summary: "Awaiting approval",
      },
    ],
  });
  assert.equal(event.meta.job_id, "job-abc");
  assert.equal(event.meta.candidate_key, "source:taiwan_stock_exchange:twse_official");
  assert.equal(event.meta.source_id, "twse_official");
  assert.equal(event.meta.connector_id, "twse");
  assert.equal(event.candidate_key, "source:taiwan_stock_exchange:twse_official");
  assert.equal(event.job_id, "job-abc");
});

test("historyHoldingTruth never promotes receipt_only to query-ready", () => {
  const [event] = durableHistoryToEvents({
    items: [
      {
        kind: "registered_asset",
        id: "rev_live2",
        title: "rev_live2",
        status: "query_ready",
        query_ready: true,
        readiness: "query_ready",
        dataset_id: "rev_live2",
        job_id: "042816e2f8af",
        summary: "Archive verified · registry verified · query-ready on desk",
        catalog_reconciliation: {
          state: "receipt_only",
          registry_row_loaded: false,
          query_allowed: false,
        },
      },
    ],
  });
  const truth = historyHoldingTruth(event);
  assert.equal(truth.queryReady, false);
  assert.equal(truth.stages.queryReady, false);
  assert.equal(truth.stages.registered, true);
  assert.equal(truth.stages.collected, true);
  assert.equal(truth.receiptOnly, true);
  assert.match(truth.label, /Registered/);
  assert.notEqual(truth.label, "Query-ready");
  // Triad stays distinct — collected does not imply query-ready.
  assert.notDeepEqual(
    { c: truth.stages.collected, r: truth.stages.registered, q: truth.stages.queryReady },
    { c: true, r: true, q: true },
  );
});

test("historyLibraryHandoff carries identities without claiming query-ready on receipts", () => {
  const [event] = durableHistoryToEvents({
    items: [
      {
        kind: "registered_asset",
        id: "rev_live2",
        title: "rev_live2",
        status: "query_ready",
        query_ready: true,
        readiness: "query_ready",
        dataset_id: "rev_live2",
        job_id: "042816e2f8af",
        candidate_key: "source:example:rev",
        source_id: "example",
        connector_id: "ex",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
      },
    ],
  });
  const handoff = historyLibraryHandoff(event);
  assert.equal(handoff.dataset_id, "rev_live2");
  assert.equal(handoff.job_id, "042816e2f8af");
  assert.equal(handoff.candidate_key, "source:example:rev");
  assert.equal(handoff.source_id, "example");
  assert.equal(handoff.connector_id, "ex");
  assert.equal(handoff.analysis_readiness, "registered");
  assert.equal(handoff.catalog_reconciliation.state, "receipt_only");
});

test("historyEventForJob synthesizes plan identities into History handoff shape", () => {
  const match = historyEventForJob([], {
    id: "job-9",
    status: "pending_approval",
    plan: {
      title: "TWSE daily quotes",
      candidate_key: "source:taiwan_stock_exchange:twse_official",
      source_id: "twse_official",
      catalog_connector_id: "twse",
    },
  });
  assert.equal(match.meta.job_id, "job-9");
  assert.equal(match.meta.candidate_key, "source:taiwan_stock_exchange:twse_official");
  assert.equal(match.meta.source_id, "twse_official");
  assert.equal(match.meta.connector_id, "twse");
  assert.equal(historyLifecycleBucket(match), "needs_approval");
});

test("historyLifecycleBucket treats receipt_only registered assets as ready lifecycle without query claim", () => {
  const [event] = durableHistoryToEvents({
    items: [
      {
        kind: "registered_asset",
        id: "x",
        title: "x",
        status: "query_ready",
        dataset_id: "x",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
      },
    ],
  });
  assert.equal(historyLifecycleBucket(event), "ready");
  assert.equal(historyHoldingTruth(event).queryReady, false);
});
