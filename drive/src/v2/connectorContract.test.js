import assert from "node:assert/strict";
import test from "node:test";

import { connectorContext, normalizeConnectorContract } from "./connectorContract.js";

test("normalizes an available incremental connector with discovered schema", () => {
  const contract = normalizeConnectorContract({
    connector_id: "mops-api",
    source_id: "mops",
    endpoint: "https://example.test/mops",
    connector: {
      configured: true,
      sync_mode: "incremental",
      cursor_field: "published_at",
      schema: { fields: [{ name: "company_id" }, { name: "published_at" }] },
      primary_key: ["company_id", "published_at"],
      rate_limit: "60/min",
    },
  });

  assert.equal(contract.access.state, "available");
  assert.equal(contract.sync.mode, "incremental");
  assert.deepEqual(contract.schema.fields, ["company_id", "published_at"]);
  assert.deepEqual(contract.schema.primary_key, ["company_id", "published_at"]);
});

test("keeps credential requirements explicit", () => {
  const contract = normalizeConnectorContract({
    source_id: "licensed-feed",
    access_state: "credential required",
    credential_profile: "faculty-license",
    license: "institutional",
  });

  assert.equal(contract.access.state, "credential_required");
  assert.equal(contract.access.credential_required, true);
  assert.equal(contract.access.credential_profile, "faculty-license");
  assert.equal(contract.execution.supported, true);
});

test("treats rate limits as retryable rather than unsupported", () => {
  const contract = normalizeConnectorContract({ status: "rate limited", quota_remaining: 0 });
  assert.equal(contract.access.state, "rate_limited");
  assert.equal(contract.execution.retryable, true);
  assert.equal(contract.execution.supported, true);
});

test("does not claim a connector is available when access is unknown", () => {
  const contract = normalizeConnectorContract({ source_id: "unknown-source" });
  assert.equal(contract.access.state, "unknown");
  assert.equal(contract.execution.probe_required, true);
});

test("builds compact Discover Ask context", () => {
  const context = connectorContext({
    connector_id: "datacite",
    access: "public",
    refresh_policy: "weekly",
    schema: { fields: ["doi", "title"] },
    estimated_bytes: 2048,
  });

  assert.equal(context.connector_id, "datacite");
  assert.equal(context.access_state, "available");
  assert.equal(context.refresh_policy, "weekly");
  assert.deepEqual(context.schema_fields, ["doi", "title"]);
  assert.equal(context.estimated_bytes, 2048);
});
