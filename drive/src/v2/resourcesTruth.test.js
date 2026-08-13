import assert from "node:assert/strict";
import test from "node:test";

import { measuredComposerLabel, rollupIsMeasured, unmeasuredResourcesPanels } from "./resourcesTruth.js";

test("missing composer model is Not reported, not a fabricated model id", () => {
  assert.equal(measuredComposerLabel(""), "Not reported");
  assert.equal(measuredComposerLabel(null), "Not reported");
  assert.equal(measuredComposerLabel("composer-2.5"), "composer-2.5");
});

test("placeholder or missing rollup is not a measured desk", () => {
  assert.equal(rollupIsMeasured(null), false);
  assert.equal(rollupIsMeasured(undefined), false);
  assert.equal(rollupIsMeasured({ _placeholder: true, hero: { query_engine: { up: false } } }), false);
  assert.equal(rollupIsMeasured({ hero: { query_engine: { up: true } } }), true);
});

test("unmeasured Resources panels contain no inventory rows", () => {
  const panels = unmeasuredResourcesPanels();
  assert.equal(panels.unmeasured, true);
  assert.equal(panels.hero, null);
  assert.deepEqual(panels.ai, []);
  assert.deepEqual(panels.motion, []);
  assert.equal(panels.connect.source_count, 0);
});
