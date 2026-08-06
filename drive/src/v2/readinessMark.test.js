import assert from "node:assert/strict";
import test from "node:test";

import { isHeldRow, readinessMark } from "./readinessMark.js";

test("smoke proof wins and carries its date", () => {
  const mark = readinessMark({
    analysis_readiness: "instant",
    query_verified: true,
    query_verified_at: "2026-08-04T14:34:20+00:00",
  });
  assert.equal(mark.label, "Verified 2026-08-04");
  assert.equal(mark.state, "verified");
});

test("unproven instant is registered, never query-ready", () => {
  const mark = readinessMark({ analysis_readiness: "instant" });
  assert.equal(mark.label, "Registered");
  assert.notEqual(mark.label, "Query-ready");
});

test("entitled metadata rows read as a route, not a dead end", () => {
  const mark = readinessMark({
    analysis_readiness: "metadata_search",
    entitlement_status: "entitled",
  });
  assert.equal(mark.label, "Route ready");
  assert.equal(mark.tone, "route");
});

test("unentitled metadata rows stay metadata only", () => {
  const mark = readinessMark({ analysis_readiness: "metadata_search" });
  assert.equal(mark.label, "Metadata only");
});

test("find_datasets rows stay leads", () => {
  assert.equal(readinessMark({ shelf_hint: "find_datasets" }).label, "Where to find it");
});

test("held detection accepts placement, local_ready and lab membership", () => {
  assert.equal(isHeldRow({ placement: "held" }), true);
  assert.equal(isHeldRow({ local_ready: true }), true);
  assert.equal(isHeldRow({ dataset_id: "a" }, new Set(["a"])), true);
  assert.equal(isHeldRow({ dataset_id: "b" }, new Set(["a"])), false);
});
