import assert from "node:assert/strict";
import test from "node:test";

import { assetAuthorityContext } from "./assetAuthority.js";
import { connectorContext } from "./connectorContract.js";
import { normalizeSynthesisExecution } from "./executionLifecycle.js";
import { buildRunningRows } from "./resourcesLedger.js";

test("preserves one research asset identity across Discover, cluster execution, Synthesis, and Library", () => {
  const outputId = "stablecoin_attention_weekly_v1";

  const discover = connectorContext({
    connector_id: "reddit-archive",
    source_id: "reddit",
    access: "public",
    sync_mode: "incremental",
    cursor_field: "created_utc",
    schema: { fields: ["asset_id", "created_utc", "engagement"] },
    refresh_policy: "weekly",
  });

  const [resourceRow] = buildRunningRows({
    health: {
      cluster: {
        workers: [
          {
            id: "optiplex",
            status: "online",
            capabilities: ["python", "rclone", "http"],
          },
        ],
      },
    },
    jobs: [
      {
        id: "job-attention-v1",
        type: "registered_pipeline",
        status: "validating",
        required_capabilities: ["python", "archive"],
        assigned_worker: {
          id: "optiplex",
          status: "online",
          capabilities: ["python", "rclone", "http", "pipeline"],
        },
        progress: { current: 4, total: 5 },
        inputs: ["reddit-engagement", "wikipedia-pageviews"],
        outputs: [outputId],
        manifest_id: "manifest-attention-v1",
        plan: { title: "Build stablecoin attention panel" },
      },
    ],
  });

  const synthesis = normalizeSynthesisExecution({
    id: "syn-attention-v1",
    materialisation: "registered",
    state: {
      execution_spec: {
        input_dataset_ids: ["reddit-engagement", "wikipedia-pageviews"],
        output_dataset_id: outputId,
      },
      execution: {
        job_id: "job-attention-v1",
        status: "completed",
        worker: "optiplex",
        manifest_id: "manifest-attention-v1",
        drive_verified: true,
        rows: 3120,
        field_count: 14,
      },
    },
  });

  const library = assetAuthorityContext({
    dataset_id: outputId,
    registry_id: `registry:${outputId}`,
    revision_id: "rev-1",
    analysis_readiness: "query_ready",
    source: "Derived from registered evidence",
    verification: { state: "partial", summary: "29 of 30 entities matched" },
    lineage: {
      inputs: ["reddit-engagement", "wikipedia-pageviews"],
      source_snapshots: ["reddit@2026-07-19", "wikipedia@2026-07-19"],
    },
    manifest_id: "manifest-attention-v1",
    drive_verified: true,
    refresh_policy: "weekly",
    row_count: 3120,
    field_count: 14,
    grain: "asset-week",
  });

  assert.equal(discover.access_state, "available");
  assert.equal(discover.sync_mode, "incremental");
  assert.equal(resourceRow.lifecycle.stage, "validating");
  assert.equal(resourceRow.lifecycle.routing.status, "satisfied");
  assert.deepEqual(resourceRow.lifecycle.proof.outputs, [outputId]);
  assert.equal(synthesis.stage, "registered");
  assert.deepEqual(synthesis.proof.outputs, [outputId]);
  assert.equal(library.dataset_id, outputId);
  assert.equal(library.readiness, "query_ready");
  assert.equal(library.manifest_id, "manifest-attention-v1");
  assert.deepEqual(library.lineage_inputs, ["reddit-engagement", "wikipedia-pageviews"]);
});

test("partial payloads stay unknown instead of fabricating access, routing, or registration", () => {
  const discover = connectorContext({ source_id: "unprobed-source" });
  const [resourceRow] = buildRunningRows({
    jobs: [
      {
        id: "job-unverified",
        type: "harvest_shard",
        status: "queued",
      },
    ],
  });
  const synthesis = normalizeSynthesisExecution({
    id: "syn-unverified",
    state: {
      execution_spec: {
        input_dataset_id: "input-a",
        output_dataset_id: "output-a",
      },
    },
  });
  const library = assetAuthorityContext({
    dataset_id: "output-a",
    analysis_readiness: "metadata_only",
  });

  assert.equal(discover.access_state, "unknown");
  assert.equal(discover.probe_required, true);
  assert.equal(resourceRow.lifecycle.routing.status, "unknown");
  assert.equal(resourceRow.lifecycle.routing.warn, false);
  assert.equal(synthesis.stage, "unknown");
  assert.equal(synthesis.proof.registry_verified, false);
  assert.equal(library.readiness, "metadata_only");
  assert.equal(library.archive_verified, undefined);
});
