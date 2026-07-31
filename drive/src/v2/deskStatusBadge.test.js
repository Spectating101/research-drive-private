import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { deskStatusBadge, visibleIntegrationChips } from "./deskStatusBadge.js";

describe("deskStatusBadge", () => {
  it("maps each desk state to one label", () => {
    assert.deepEqual(deskStatusBadge("ok"), { label: "Live registry", tone: "ok" });
    assert.deepEqual(deskStatusBadge("syncing"), { label: "Syncing…", tone: "muted" });
    assert.deepEqual(deskStatusBadge("empty"), { label: "Empty registry", tone: "warn" });
    assert.deepEqual(deskStatusBadge("degraded"), { label: "Desk degraded", tone: "warn" });
    assert.deepEqual(deskStatusBadge("demo"), { label: "Demo catalog", tone: "warn" });
  });

  it("treats a seeded catalog as demo regardless of status", () => {
    assert.equal(deskStatusBadge("unknown", true).label, "Demo catalog");
  });

  it("falls back to offline rather than claiming health for an unknown state", () => {
    assert.equal(deskStatusBadge("nonsense").label, "Desk API offline");
    assert.equal(deskStatusBadge(undefined).label, "Desk API offline");
  });
});

describe("visibleIntegrationChips", () => {
  it("drops a chip that only restates the status badge", () => {
    // Production rendered exactly this: a "Desk degraded" badge and a
    // "Desk degraded" chip, side by side in the header.
    const chips = [
      { id: "a", label: "Desk degraded", tone: "warn" },
      { id: "b", label: "NVMe 87%", tone: "warn" },
    ];
    const out = visibleIntegrationChips(chips, "Desk degraded");
    assert.deepEqual(out.map((c) => c.id), ["b"]);
  });

  it("matches the badge case-insensitively and ignoring surrounding space", () => {
    const chips = [{ id: "a", label: "  desk degraded ", tone: "warn" }];
    assert.equal(visibleIntegrationChips(chips, "Desk degraded").length, 0);
  });

  it("keeps only attention tones", () => {
    const chips = [
      { id: "a", label: "All good", tone: "ok" },
      { id: "b", label: "Broken", tone: "error" },
      { id: "c", label: "Quiet", tone: "muted" },
    ];
    assert.deepEqual(visibleIntegrationChips(chips, "Live registry").map((c) => c.id), ["b"]);
  });

  it("collapses chips duplicated among themselves", () => {
    const chips = [
      { id: "a", label: "NVMe 87%", tone: "warn" },
      { id: "b", label: "NVMe 87%", tone: "warn" },
    ];
    assert.deepEqual(visibleIntegrationChips(chips, "Live registry").map((c) => c.id), ["a"]);
  });

  it("survives absent or malformed input", () => {
    assert.deepEqual(visibleIntegrationChips(null, "Live registry"), []);
    assert.deepEqual(visibleIntegrationChips([null, { tone: "warn" }], "Live registry"), []);
  });
});
