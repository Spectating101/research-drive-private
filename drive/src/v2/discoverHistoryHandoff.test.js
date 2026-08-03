import assert from "node:assert/strict";
import test from "node:test";
import {
  durableHistoryToEvents,
  historyEventForJob,
  historyHoldingTruth,
  historyLibraryHandoff,
  mergeHistoryEvents,
  sourceResultToCandidate,
} from "./discoverAdapters.js";

test("historyEventForJob selects the durable History object for a job id", () => {
  const events = mergeHistoryEvents(
    [
      {
        id: "hist-job-pending-1",
        target: "MOPS financial statements",
        meta: {
          job_id: "job-pending-1",
          status: "pending_approval",
          candidate_key: "source:mops:mops_taiwan",
          source_id: "mops_taiwan",
          connector_id: "mops",
        },
        status: "pending_approval",
      },
    ],
    [],
  );
  const match = historyEventForJob(events, {
    id: "job-pending-1",
    plan: { title: "MOPS financial statements" },
  });
  assert.equal(match.id, "hist-job-pending-1");
  assert.equal(match.meta.job_id, "job-pending-1");
  assert.equal(match.meta.candidate_key, "source:mops:mops_taiwan");
  assert.equal(match.meta.source_id, "mops_taiwan");
  assert.equal(match.meta.connector_id, "mops");
});

test("historyEventForJob synthesizes identities when ledger has no row yet", () => {
  const match = historyEventForJob([], {
    id: "job-recovery-9",
    status: "failed",
    plan: {
      title: "Blocked harvest",
      candidate_key: "source:x:y",
      source_id: "y",
      connector_id: "x",
    },
  });
  assert.equal(match.id, "job-recovery-9");
  assert.equal(match.meta.job_id, "job-recovery-9");
  assert.match(String(match.target), /Blocked harvest/);
  assert.equal(match.meta.candidate_key, "source:x:y");
  assert.equal(match.meta.source_id, "y");
  assert.equal(match.meta.connector_id, "x");
});

test("durableHistoryToEvents preserves candidate/source/connector/job identities", () => {
  const [event] = durableHistoryToEvents({
    items: [
      {
        kind: "collection_run",
        id: "run-1",
        title: "Collect TWSE",
        status: "cancelled",
        job_id: "job-abc",
        candidate_key: "source:taiwan_stock_exchange:twse_official",
        source_id: "twse_official",
        connector_id: "twse",
        updated_at: "2026-07-23T17:07:00+00:00",
      },
    ],
  });
  assert.equal(event.job_id, "job-abc");
  assert.equal(event.candidate_key, "source:taiwan_stock_exchange:twse_official");
  assert.equal(event.source_id, "twse_official");
  assert.equal(event.connector_id, "twse");
  assert.equal(event.meta.job_id, "job-abc");
  assert.equal(event.meta.candidate_key, event.candidate_key);
});

test("receipt_only History never promotes to query-ready; handoff keeps identities", () => {
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
        job_id: "job-42",
        candidate_key: "source:twse:rev",
        source_id: "twse_official",
        connector_id: "twse",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
        summary: "Archive verified · query-ready on desk",
      },
    ],
  });
  const truth = historyHoldingTruth(event);
  assert.equal(truth.queryReady, false);
  assert.equal(truth.stages.queryReady, false);
  assert.equal(truth.stages.registered, true);
  assert.equal(truth.stages.collected, true);
  assert.notEqual(truth.label, "Query-ready");
  assert.match(truth.label, /Registered/);

  const handoff = historyLibraryHandoff(event);
  assert.equal(handoff.dataset_id, "rev_live2");
  assert.equal(handoff.job_id, "job-42");
  assert.equal(handoff.candidate_key, "source:twse:rev");
  assert.equal(handoff.source_id, "twse_official");
  assert.equal(handoff.connector_id, "twse");
  assert.equal(handoff.analysis_readiness, "registered");
  assert.equal(handoff.catalog_reconciliation.state, "receipt_only");
});

test("completed, registered, and query_ready stay distinct in holding truth", () => {
  const collectedOnly = historyHoldingTruth({
    status: "completed",
    meta: { job_id: "j1", status: "completed" },
  });
  assert.equal(collectedOnly.queryReady, false);
  assert.equal(collectedOnly.stages.registered, false);
  assert.equal(collectedOnly.completed, false);
  assert.equal(collectedOnly.collected, true);
  assert.equal(collectedOnly.label, "Collected");

  const completed = historyHoldingTruth({
    status: "completed",
    meta: {
      dataset_id: "ds0",
      readiness: "completed",
      status: "completed",
      catalog_reconciliation: { state: "reconciled", query_allowed: false },
    },
  });
  assert.equal(completed.queryReady, false);
  assert.equal(completed.completed, true);
  assert.equal(completed.label, "Completed");
  assert.notEqual(completed.label, "Registered");
  assert.notEqual(completed.label, "Query-ready");
  assert.equal(
    historyLibraryHandoff({
      status: "completed",
      meta: {
        dataset_id: "ds0",
        readiness: "completed",
        status: "completed",
        catalog_reconciliation: { state: "reconciled", query_allowed: false },
      },
    }).analysis_readiness,
    "completed",
  );

  const registered = historyHoldingTruth({
    status: "registered",
    meta: {
      dataset_id: "ds1",
      readiness: "registered",
      status: "registered",
      catalog_reconciliation: { state: "reconciled", query_allowed: false },
    },
  });
  assert.equal(registered.queryReady, false);
  assert.equal(registered.completed, false);
  assert.equal(registered.label, "Registered");

  const queryReady = historyHoldingTruth({
    status: "query_ready",
    meta: {
      dataset_id: "ds2",
      readiness: "query_ready",
      query_ready: true,
      catalog_reconciliation: { state: "reconciled", query_allowed: true },
    },
  });
  assert.equal(queryReady.queryReady, true);
  assert.equal(queryReady.completed, false);
  assert.equal(queryReady.label, "Query-ready");
});

test("Explore source candidates retain identity fields for preview/handoff", () => {
  const row = sourceResultToCandidate({
    source_id: "mops_taiwan",
    connector_id: "mops",
    desk_connector_id: "mops",
    candidate_key: "source:twse_mops:mops_taiwan",
    title: "Taiwan MOPS / governance procured",
    provider: "TWSE MOPS",
    endpoint: "mops.twse.com.tw",
    preview_supported: true,
  });
  assert.equal(row.source_id, "mops_taiwan");
  assert.equal(row.connector_id, "mops");
  assert.equal(row.candidate_key, "source:twse_mops:mops_taiwan");
  assert.equal(row.preview_supported, true);
});
