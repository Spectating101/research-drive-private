import assert from "node:assert/strict";
import test from "node:test";

import { discoverModeFromLegacy, discoverModeToUrlState } from "./discoverMode.js";

test("normalizes current and legacy Discover modes to Explore or History", () => {
  assert.deepEqual(discoverModeFromLegacy("explore"), { mode: "explore", focusAwaiting: false });
  assert.deepEqual(discoverModeFromLegacy("history"), { mode: "history", focusAwaiting: false });
  assert.deepEqual(discoverModeFromLegacy("search"), { mode: "explore", focusAwaiting: false });
  assert.deepEqual(discoverModeFromLegacy("activity"), { mode: "explore", focusAwaiting: false });
  assert.deepEqual(discoverModeFromLegacy("approvals"), { mode: "explore", focusAwaiting: true });
  assert.deepEqual(discoverModeFromLegacy("awaiting"), { mode: "explore", focusAwaiting: true });
});

test("serializes only the two supported Discover modes", () => {
  assert.equal(discoverModeToUrlState("explore"), "");
  assert.equal(discoverModeToUrlState("history"), "history");
});
