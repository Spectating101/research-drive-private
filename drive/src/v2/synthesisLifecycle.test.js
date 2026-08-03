import test from "node:test";
import assert from "node:assert/strict";

import { buildStageDetail, executionTrack } from "./synthesisLifecycle.js";

const row = (track, label) => track.find((entry) => entry.label === label);

/* ── Build stage: a specification is not approval ─────────────────────── */

test("an accepted specification without approval is not called approved", () => {
  const thread = { state: { execution_spec: { input_dataset_id: "a", output_dataset_id: "b" } } };
  assert.equal(buildStageDetail(thread), "Execution specified");
});

test("pending approval asks for a decision instead of claiming approval", () => {
  const thread = {
    state: {
      execution_spec: { input_dataset_id: "a", output_dataset_id: "b" },
      execution: { status: "pending_approval" },
    },
  };
  assert.equal(buildStageDetail(thread), "Approval required");
});

test("only post-approval lifecycle states describe execution as approved", () => {
  for (const status of ["queued", "running", "registering", "archiving", "registered", "query_ready", "completed"]) {
    const thread = { state: { execution_spec: { output_dataset_id: "b" }, execution: { status } } };
    assert.equal(buildStageDetail(thread), "Approved execution", `status ${status}`);
  }
});

test("a thread with no specification makes no execution claim", () => {
  assert.equal(buildStageDetail({ state: {} }), "Execution record");
  assert.equal(buildStageDetail(undefined), "Execution record");
});

/* ── Execution track: completed != archived != registered != query-ready ─ */

test("completed worker leaves archive and registry unverified", () => {
  const track = executionTrack("completed", false, false);
  assert.equal(row(track, "Worker build").detail, "Completed");
  assert.equal(row(track, "Archive + registry").detail, "Awaiting verification");
  assert.notEqual(row(track, "Archive + registry").state, "done");
  assert.equal(row(track, "Library handoff").detail, "Not registered");
});

test("pending approval does not advance the worker or archive rows", () => {
  const track = executionTrack("pending_approval", false, false);
  assert.equal(row(track, "Researcher approval").detail, "Decision required");
  assert.equal(row(track, "Worker build").detail, "Waiting");
  assert.equal(row(track, "Archive + registry").detail, "Waiting");
});

test("registered verifies archive but does not imply query readiness", () => {
  const track = executionTrack("registered", true, false);
  assert.equal(row(track, "Archive + registry").detail, "Verified");
  assert.equal(row(track, "Archive + registry").state, "done");
  assert.equal(row(track, "Library handoff").detail, "Registered · query readiness unverified");
});

test("query readiness requires the explicit query_ready lifecycle", () => {
  const track = executionTrack("query_ready", true, true);
  assert.equal(row(track, "Archive + registry").detail, "Verified");
  assert.equal(row(track, "Library handoff").detail, "Query-ready asset");
});

test("an unrequested execution claims nothing", () => {
  const track = executionTrack("", false, false);
  assert.equal(row(track, "Researcher approval").detail, "Not requested");
  assert.equal(row(track, "Worker build").detail, "Waiting");
  assert.equal(row(track, "Archive + registry").detail, "Waiting");
  assert.equal(row(track, "Library handoff").detail, "Not registered");
});

test("hyphenated and mixed-case statuses normalize", () => {
  const track = executionTrack("Query-Ready", true, true);
  assert.equal(row(track, "Archive + registry").detail, "Verified");
});
