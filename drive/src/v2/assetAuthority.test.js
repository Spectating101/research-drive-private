import assert from "node:assert/strict";
import test from "node:test";

import { assetAuthorityContext, normalizeAssetAuthority } from "./assetAuthority.js";

test("keeps metadata-only distinct from registered and query-ready", () => {
  const metadata = normalizeAssetAuthority({ dataset_id: "a", analysis_readiness: "metadata_only" });
  const registered = normalizeAssetAuthority({ dataset_id: "b", registry_id: "registry:b", analysis_readiness: "registered" });
  const ready = normalizeAssetAuthority({ dataset_id: "c", analysis_readiness: "instant" });

  assert.equal(metadata.readiness.state, "metadata_only");
  assert.equal(metadata.readiness.registered, false);
  assert.equal(registered.readiness.state, "registered");
  assert.equal(registered.readiness.query_ready, false);
  assert.equal(ready.readiness.state, "query_ready");
  assert.equal(ready.readiness.registered, true);
});

test("preserves source, verification, revision, manifest, and lineage proof", () => {
  const authority = normalizeAssetAuthority({
    dataset_id: "attention-v2",
    registry_id: "registry:attention-v2",
    revision_id: "rev-2",
    analysis_readiness: "query_ready",
    source: { name: "Derived from registered evidence", version: "2026-07-19" },
    verification: { state: "partial", summary: "29 of 30 entities matched" },
    lineage: { inputs: [{ dataset_id: "reddit" }, "wikipedia"], source_snapshots: ["reddit@2026-07-18"] },
    manifest_id: "manifest-22",
    checksum: "sha256:abc",
    drive_verified: true,
    row_count: 3120,
    field_count: 14,
    entity_count: 29,
    grain: "asset-week",
  });

  assert.equal(authority.identity.revision_id, "rev-2");
  assert.equal(authority.source.version, "2026-07-19");
  assert.equal(authority.verification.state, "partial");
  assert.deepEqual(authority.lineage.inputs, ["reddit", "wikipedia"]);
  assert.equal(authority.lineage.manifest_id, "manifest-22");
  assert.equal(authority.storage.archive_verified, true);
  assert.equal(authority.shape.rows, 3120);
  assert.equal(authority.shape.grain, "asset-week");
});

test("does not claim verification or archive proof when absent", () => {
  const authority = normalizeAssetAuthority({ dataset_id: "self-upload", analysis_readiness: "instant", source: "Self-provided" });

  assert.equal(authority.readiness.state, "query_ready");
  assert.equal(authority.verification.state, "not_checked");
  assert.equal(authority.storage.archive_verified, false);
});

test("builds compact Ask context without empty arrays or null fields", () => {
  const context = assetAuthorityContext({
    dataset_id: "panel-v1",
    analysis_readiness: "registered",
    source_id: "mops",
    derived_from: ["mops-filings", "twse-prices"],
    refresh_policy: "monthly",
  });

  assert.equal(context.dataset_id, "panel-v1");
  assert.equal(context.readiness, "registered");
  assert.equal(context.source, "mops");
  assert.deepEqual(context.lineage_inputs, ["mops-filings", "twse-prices"]);
  assert.equal(context.refresh_policy, "monthly");
  assert.equal("manifest_id" in context, true);
  assert.equal(context.manifest_id, undefined);
});
