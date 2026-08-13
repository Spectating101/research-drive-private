import assert from "node:assert/strict";
import test from "node:test";

import {
  demotionSentence,
  statusPillKind,
} from "./datasetMeta.js";

test("instant readiness is not query-ready when local panel is missing at runtime", () => {
  const pill = statusPillKind({
    analysis_readiness: "instant",
    runtime_readiness_reason: "local_panel_missing",
  });
  assert.notEqual(pill.kind, "query-ready");
  assert.notEqual(pill.label, "Query-ready");
});

test("declared instant without a runtime reason stays query-ready", () => {
  const pill = statusPillKind({ analysis_readiness: "instant" });
  assert.equal(pill.kind, "query-ready");
});

test("demotion sentence names the measured gap, not a generic warning", () => {
  assert.equal(
    demotionSentence({
      analysis_readiness: "instant",
      runtime_readiness_reason: "local_panel_missing",
    }),
    "Declared queryable; local panel is missing.",
  );
  assert.equal(
    demotionSentence({ runtime_readiness_reason: "local_bytes_missing" }),
    "Declared queryable; local bytes are missing.",
  );
  assert.equal(demotionSentence({ analysis_readiness: "instant" }), "");
});

test("any runtime readiness reason blocks Query-ready, including unknown future reasons", () => {
  const pill = statusPillKind({
    analysis_readiness: "instant",
    runtime_readiness_reason: "new_engine_reason_v2",
  });
  assert.notEqual(pill.kind, "query-ready");
  assert.equal(
    demotionSentence({
      analysis_readiness: "instant",
      runtime_readiness_reason: "new_engine_reason_v2",
    }),
    "Declared queryable; runtime readiness is not confirmed.",
  );
});
