import test from "node:test";
import assert from "node:assert/strict";
import { historyLifecycleLabel } from "./historyLifecycleLabel.js";

test("cancelled list and rail share Cancelled, not Route investigating", () => {
  assert.equal(
    historyLifecycleLabel({ status: "cancelled", action: "collection_run", target: "USDT" }),
    "Cancelled",
  );
});

test("failed recovery vocabulary is shared", () => {
  assert.equal(
    historyLifecycleLabel({ status: "failed", action: "collection_run" }),
    "Failed — needs recovery",
  );
});
