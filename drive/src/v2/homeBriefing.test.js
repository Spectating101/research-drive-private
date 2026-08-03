import assert from "node:assert/strict";
import test from "node:test";
import { buildHomeBriefing } from "./homeBriefing.js";

test("home briefing derives judgment from pending jobs only", () => {
  const briefing = buildHomeBriefing({
    datasets: [],
    jobs: [{ id: "job-1", title: "MOPS financial statements", status: "pending_approval" }],
    health: { status: "ok", desk: { jobs: { pending_approval: 1, running: 0 } } },
  });
  assert.equal(briefing.needsJudgment.length, 1);
  assert.equal(briefing.needsJudgment[0].kind, "approval");
  assert.match(briefing.needsJudgment[0].title, /MOPS/);
  assert.equal(briefing.empty.continue, true);
});

test("home briefing continues from catalog when recent list is empty", () => {
  const briefing = buildHomeBriefing({
    datasets: [{ dataset_id: "a", name: "Panel A", analysis_readiness: "instant" }],
    jobs: [],
  });
  assert.equal(briefing.continueWork?.id, "a");
  assert.equal(briefing.continueWork?.previewAllowed, true);
  assert.equal(briefing.empty.continue, false);
});

test("home briefing does not invent gap chips without profile recommendations", () => {
  const briefing = buildHomeBriefing({
    datasets: [{ dataset_id: "a", name: "Panel A", analysis_readiness: "instant" }],
    jobs: [],
    health: { status: "ok", desk: { jobs: {} } },
    profile: null,
  });
  assert.ok(briefing.nextActions.every((action) => !/TWSE|MOPS filings|stablecoin/i.test(action.label)));
  assert.ok(briefing.nextActions.some((action) => /Library|Continue|Browse/i.test(action.label)));
});

test("home briefing marks evidence freshness unknown when timestamps are absent", () => {
  const briefing = buildHomeBriefing({
    datasets: [{ dataset_id: "a", name: "Panel A", analysis_readiness: "instant" }],
    jobs: [],
  });
  assert.equal(briefing.evidence.length, 1);
  assert.equal(briefing.evidence[0].freshnessUnknown, true);
});

test("home briefing includes profile search recommendations as actions", () => {
  const briefing = buildHomeBriefing({
    datasets: [],
    jobs: [],
    profile: {
      procurement_recommendations: [{ search_query: "TWSE governance" }],
    },
  });
  assert.ok(briefing.nextActions.some((action) => action.searchQuery === "TWSE governance"));
});

test("continue work prefers query-ready over newer receipt_only rows by authoritative fields", () => {
  const briefing = buildHomeBriefing({
    datasets: [
      {
        dataset_id: "receipt_recovery_newest",
        name: "Registered recovery row",
        analysis_readiness: "registered",
        updated_at: "2026-07-24T12:00:00Z",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
        query_allowed: false,
      },
      {
        dataset_id: "usable_panel",
        name: "Asia daily panel",
        analysis_readiness: "instant",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    jobs: [],
  });
  assert.equal(briefing.continueWork?.id, "usable_panel");
  assert.equal(briefing.continueWork?.previewAllowed, true);
  assert.equal(briefing.continueWork?.tab, "library");
});

test("receipt_only rows are not ordinary reusable evidence and never offer preview", () => {
  const briefing = buildHomeBriefing({
    datasets: [
      {
        dataset_id: "receipt_a",
        name: "Recovery A",
        analysis_readiness: "registered",
        updated_at: "2026-07-24T12:00:00Z",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
      },
      {
        dataset_id: "ready_b",
        name: "Ready B",
        analysis_readiness: "query_ready",
        updated_at: "2026-06-01T00:00:00Z",
      },
      {
        dataset_id: "registered_ok",
        name: "Legitimate registered",
        analysis_readiness: "registered",
        updated_at: "2026-05-01T00:00:00Z",
        catalog_reconciliation: { state: "reconciled", query_allowed: false },
      },
    ],
    jobs: [],
  });
  const evidenceIds = briefing.evidence.map((row) => row.id);
  assert.ok(evidenceIds.includes("ready_b"));
  assert.ok(evidenceIds.includes("registered_ok"));
  assert.ok(!evidenceIds.includes("receipt_a"));
  assert.ok(briefing.evidence.every((row) => row.previewAllowed !== true || row.id === "ready_b"));
  assert.equal(
    briefing.evidence.find((row) => row.id === "registered_ok")?.metric,
    "Registered",
  );
});

test("when only receipt_only assets exist, classify them as reconciliation pending without preview", () => {
  const briefing = buildHomeBriefing({
    datasets: [
      {
        dataset_id: "only_receipt",
        name: "Sole recovery",
        analysis_readiness: "registered",
        updated_at: "2026-07-24T12:00:00Z",
        catalog_reconciliation: { state: "receipt_only", query_allowed: false },
        query_allowed: false,
      },
    ],
    jobs: [],
  });
  assert.equal(briefing.continueWork, null);
  assert.equal(briefing.empty.continue, true);
  assert.equal(briefing.evidence.length, 1);
  assert.equal(briefing.evidence[0].id, "only_receipt");
  assert.equal(briefing.evidence[0].kind, "receipt");
  assert.match(briefing.evidence[0].metric, /reconciliation pending/i);
  assert.equal(briefing.evidence[0].previewAllowed, false);
  assert.ok(
    briefing.evidence[0].tab === "library" || briefing.evidence[0].discoverMode === "history",
  );
  assert.ok(!briefing.nextActions.some((action) => /Preview|query/i.test(action.label)));
});
