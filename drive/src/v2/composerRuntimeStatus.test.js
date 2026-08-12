import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { composerRuntimeRead } from "./composerRuntimeStatus.js";

describe("composerRuntimeRead", () => {
  it("returns null when no runtime object is present", () => {
    assert.equal(composerRuntimeRead(undefined), null);
    assert.equal(composerRuntimeRead(null), null);
    assert.equal(composerRuntimeRead("not-an-object"), null);
  });

  it("treats ready as the only truthful Ready state", () => {
    const read = composerRuntimeRead({ status: "ready", verified: true, configured: true });
    assert.equal(read.ready, true);
    assert.equal(read.warn, false);
    assert.equal(read.short, "Ready");
  });

  it("does not render Ready for a degraded (failed probe) runtime even though verified is true", () => {
    // Regression: record_composer_failure() sets verified: true because a
    // real probe DID run — it just failed. verified alone must never be
    // read as "healthy."
    const read = composerRuntimeRead({ status: "degraded", verified: true, configured: true, error_category: "timeout" });
    assert.equal(read.ready, false);
    assert.equal(read.warn, true);
    assert.equal(read.short, "Degraded");
  });

  it("treats stale as its own distinct state, not folded into unverified", () => {
    const read = composerRuntimeRead({ status: "stale", verified: false, configured: true, age_seconds: 999 });
    assert.equal(read.ready, false);
    assert.equal(read.warn, true);
    assert.equal(read.short, "Needs recheck");
  });

  it("treats unverified (never probed) as its own state", () => {
    const read = composerRuntimeRead({ status: "unverified", verified: false, configured: true, checked_at: null });
    assert.equal(read.ready, false);
    assert.equal(read.warn, true);
    assert.equal(read.short, "Unverified");
  });

  it("treats unavailable (not configured) as its own state", () => {
    const read = composerRuntimeRead({ status: "unavailable", verified: false, configured: false });
    assert.equal(read.ready, false);
    assert.equal(read.warn, true);
    assert.equal(read.short, "Not configured");
  });

  it("never defaults an unrecognized status to Ready", () => {
    const read = composerRuntimeRead({ status: "something_new_the_frontend_does_not_know", verified: true });
    assert.equal(read.ready, false);
    assert.equal(read.warn, true);
  });
});
