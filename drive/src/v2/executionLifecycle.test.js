import assert from "node:assert/strict";
import test from "node:test";

import {
  executionSortPriority,
  isExecutionVisible,
  normalizeExecutionLifecycle,
  normalizeSynthesisExecution,
} from "./executionLifecycle.js";
import { buildRunningRows } from "./resourcesLedger.js";

test("normalizes a running cluster job without inventing progress", () => {
  const result = normalizeExecutionLifecycle({
    id: "job-17",
    status: "executing",
    assigned_worker: "asus-02",
    worker_pool: "windows_lab",
  });

  assert.equal(result.stage, "running");
  assert.equal(result.label, "running");
  assert.equal(result.progress, null);
  assert.equal(result.detail, "worker asus-02");
  assert.equal(result.proof.run_id, "job-17");
  assert.equal(result.proof.pool, "windows_lab");
  assert.equal(result.visible, true);
  assert.equal(result.terminal, false);
});

test("uses explicit bounded progress and preserves output proof", () => {
  const result = normalizeExecutionLifecycle({
    id: "job-18",
    lifecycle: {
      stage: "verifying",
      progress: { current: 3, total: 4 },
      worker: { name: "optiplex" },
      outputs: [{ dataset_id: "twse_panel_v2" }],
      events: [
        { event_type: "START", timestamp: "2026-07-19T09:00:00Z" },
        { event_type: "validating", timestamp: "2026-07-19T09:05:00Z" },
      ],
    },
  });

  assert.equal(result.stage, "validating");
  assert.equal(result.progress, 75);
  assert.equal(result.detail, "worker optiplex · 1 output");
  assert.deepEqual(result.proof.outputs, ["twse_panel_v2"]);
  assert.equal(result.proof.event_count, 2);
});

test("surfaces failed and blocked jobs as attention items", () => {
  const failed = normalizeExecutionLifecycle({ status: "error", attempt: 2, retryable: true });
  const blocked = normalizeExecutionLifecycle({ status: "stalled" });

  assert.equal(failed.stage, "failed");
  assert.equal(failed.warn, true);
  assert.equal(failed.retryable, true);
  assert.match(failed.detail, /attempt 2/);
  assert.equal(blocked.stage, "blocked");
  assert.equal(isExecutionVisible(blocked), true);
  assert.equal(executionSortPriority(failed), 0);
});

test("distinguishes completed execution from registered research asset", () => {
  const completed = normalizeExecutionLifecycle({ status: "succeeded", outputs: ["panel-v1"] });
  const registered = normalizeExecutionLifecycle({
    status: "registered",
    outputs: ["panel-v1"],
    manifest_id: "manifest-7",
    drive_verified: true,
    registration_id: "registry:panel-v1",
  });

  assert.equal(completed.stage, "completed");
  assert.equal(completed.proof.registry_verified, false);
  assert.equal(registered.stage, "registered");
  assert.equal(registered.terminal, true);
  assert.equal(registered.visible, false);
  assert.equal(registered.proof.manifest_id, "manifest-7");
  assert.equal(registered.proof.archive_verified, true);
  assert.equal(registered.proof.registry_verified, true);
});

test("normalizes a Synthesis thread into the shared execution contract", () => {
  const result = normalizeSynthesisExecution({
    id: "syn-4",
    materialisation: "registered",
    state: {
      execution_spec: {
        input_dataset_id: "reddit-events",
        output_dataset_id: "attention-index-v1",
      },
      execution: {
        job_id: "job-syn-4",
        status: "completed",
        worker: "optiplex",
        manifest_id: "manifest-syn-4",
        drive_verified: true,
        rows: 3120,
        field_count: 14,
      },
    },
  });

  assert.equal(result.stage, "registered");
  assert.equal(result.proof.run_id, "job-syn-4");
  assert.equal(result.proof.worker, "optiplex");
  assert.deepEqual(result.proof.inputs, ["reddit-events"]);
  assert.deepEqual(result.proof.outputs, ["attention-index-v1"]);
  assert.equal(result.proof.rows, 3120);
  assert.equal(result.proof.fields, 14);
  assert.equal(result.proof.registry_verified, true);
});

test("Resources rows expose worker, explicit progress, and failed jobs", () => {
  const rows = buildRunningRows({
    jobs: [
      {
        id: "job-running",
        status: "running",
        assigned_worker: "asus-03",
        progress: { current: 2, total: 5 },
        plan: { title: "Collect MOPS filings" },
      },
      {
        id: "job-failed",
        status: "failed",
        attempt: 3,
        type: "scraper_run",
      },
      { id: "job-done", status: "completed", type: "archive_upload" },
    ],
  });

  assert.equal(rows.length, 2);
  assert.equal(rows[0].key, "job-job-failed");
  assert.equal(rows[0].warn, true);
  assert.equal(rows[0].detail, "attempt 3");
  assert.equal(rows[1].label, "Collect MOPS filings");
  assert.equal(rows[1].detail, "worker asus-03");
  assert.equal(rows[1].progress, 40);
  assert.equal(rows[1].lifecycle.proof.worker, "asus-03");
});
