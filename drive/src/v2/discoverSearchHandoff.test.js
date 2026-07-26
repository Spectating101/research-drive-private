import assert from "node:assert/strict";
import { test } from "node:test";
import { discoverSearchHandoff } from "./discoverSearchHandoff.js";

test("Profile Search carries a non-empty query into Discover Explore", () => {
  const handoff = discoverSearchHandoff("  TWSE listed firms  ");
  assert.deepEqual(handoff, {
    tab: "browse",
    q: "TWSE listed firms",
    discoverSearchQuery: "TWSE listed firms",
  });
});

test("empty Profile Search does not invent a Discover query", () => {
  assert.equal(discoverSearchHandoff(""), null);
  assert.equal(discoverSearchHandoff("   "), null);
  assert.equal(discoverSearchHandoff(null), null);
});
