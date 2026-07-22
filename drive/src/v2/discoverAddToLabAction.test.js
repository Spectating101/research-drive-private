import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDiscoverAddToLabPrimary,
  discoverCollectShouldEnterBusyState,
  railActionAccessibleName,
} from "./discoverAddToLabAction.js";

const PROBE_TARGET = {
  url: "https://example.test/data.csv",
  title: "Example CSV",
};

test("pre-probe Add to lab stays disabled with exact accessible name", () => {
  const preflight = { canAdd: false };
  const action = buildDiscoverAddToLabPrimary({
    collectBusy: false,
    probeLoading: false,
    preflight,
    onAddToLab: () => {},
    target: PROBE_TARGET,
  });
  assert.equal(action.disabled, true);
  assert.equal(railActionAccessibleName(action), "Add to lab");
  assert.notEqual(railActionAccessibleName(action), "Queuing…");
});

test("probing keeps Add to lab disabled without Queuing label", () => {
  const preflight = { canAdd: false };
  const action = buildDiscoverAddToLabPrimary({
    collectBusy: false,
    probeLoading: true,
    preflight,
    onAddToLab: () => {},
    target: PROBE_TARGET,
  });
  assert.equal(action.disabled, true);
  assert.equal(railActionAccessibleName(action), "Add to lab");
});

test("actual collection submission shows Queuing busy label", () => {
  const preflight = { canAdd: true };
  const action = buildDiscoverAddToLabPrimary({
    collectBusy: true,
    probeLoading: false,
    preflight,
    onAddToLab: () => {},
    target: PROBE_TARGET,
  });
  assert.equal(action.disabled, true);
  assert.equal(railActionAccessibleName(action), "Queuing…");
});

test("collect busy state requires a ready connector", () => {
  assert.equal(discoverCollectShouldEnterBusyState(""), false);
  assert.equal(discoverCollectShouldEnterBusyState(undefined), false);
  assert.equal(discoverCollectShouldEnterBusyState("direct_file"), true);
});
