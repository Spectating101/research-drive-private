import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { deskApiHealthPresentation, deskStatusBadgeLabel } from "./deskHealthPresentation.js";

describe("deskApiHealthPresentation", () => {
  it("uses one Live registry label for Header and Settings when /health is ok", () => {
    const view = deskApiHealthPresentation({ status: "ok", desk: {} }, { datasetCount: 12 });
    assert.equal(view.status, "ok");
    assert.equal(view.label, "Live registry");
    assert.equal(view.label, deskStatusBadgeLabel("ok"));
    assert.equal(view.ok, true);
    assert.match(view.detail, /Catalog/);
  });

  it("does not invent Live when health is unknown", () => {
    const view = deskApiHealthPresentation({ status: "" }, { datasetCount: 0 });
    assert.equal(view.ok, false);
    assert.equal(view.label, "Desk API offline");
    assert.notEqual(view.label, "Live registry");
  });

  it("does not promote Live from catalog count without explicit /health ok", () => {
    const view = deskApiHealthPresentation({ status: "" }, { datasetCount: 12 });
    assert.equal(view.ok, false);
    assert.notEqual(view.status, "ok");
    assert.notEqual(view.label, "Live registry");
    assert.match(view.detail, /12/);
    assert.doesNotMatch(view.detail, /Ask · jobs reachable/i);
  });

  it("maps degraded without claiming Ready", () => {
    const view = deskApiHealthPresentation({ status: "degraded", desk: {} });
    assert.equal(view.label, "Desk degraded");
    assert.equal(view.ok, false);
    assert.doesNotMatch(view.label, /Ready|Live registry/i);
  });

  it("keeps Syncing wording while /health has not arrived", () => {
    const view = deskApiHealthPresentation(null);
    assert.equal(view.label, "Syncing…");
    assert.equal(view.status, "syncing");
  });

  it("honors projected ok from health.projection when complete", () => {
    const view = deskApiHealthPresentation({
      status: "degraded",
      projection: {
        desk_status: "ok",
        status: "ok",
        label: "Live registry",
        components: { catalog: "ok", ask: "ok", jobs: "ok" },
      },
    });
    assert.equal(view.status, "ok");
    assert.equal(view.label, "Live registry");
    assert.equal(view.ok, true);
    assert.match(view.detail, /catalog/i);
  });

  it("honors projected degraded from health.projection when complete", () => {
    const view = deskApiHealthPresentation({
      status: "ok",
      projection: {
        desk_status: "degraded",
        status: "degraded",
        label: "Desk degraded",
        components: { catalog: "ok", ask: "degraded" },
      },
    });
    assert.equal(view.status, "degraded");
    assert.equal(view.label, "Desk degraded");
    assert.equal(view.ok, false);
    assert.equal(view.tone, "warn");
    assert.match(view.detail, /ask/i);
  });

  it("does not promote projection missing status to live", () => {
    const view = deskApiHealthPresentation({
      status: "",
      projection: {
        label: "Live registry",
        components: { catalog: "ok", ask: "ok", jobs: "ok" },
      },
    });
    assert.equal(view.ok, false);
    assert.notEqual(view.status, "ok");
    assert.notEqual(view.label, "Live registry");
  });

  it("summarizes nested health.projection.components without [object Object]", () => {
    const view = deskApiHealthPresentation({
      status: "ok",
      projection: {
        desk_status: "degraded",
        status: "degraded",
        label: "Desk degraded",
        components: {
          catalog: { status: "ok", datasets: 12 },
          ask: { status: "degraded", latency_ms: 2400 },
          jobs: { status: "ok", running: 1 },
        },
      },
    });
    assert.equal(view.status, "degraded");
    assert.equal(view.ok, false);
    assert.equal(view.label, "Desk degraded");
    assert.doesNotMatch(view.detail, /\[object Object\]/);
    assert.match(view.detail, /catalog:\s*ok/i);
    assert.match(view.detail, /ask:\s*degraded/i);
    assert.match(view.detail, /jobs:\s*ok/i);
    assert.doesNotMatch(view.detail, /\bReady\b|\bLive registry\b/i);
    assert.ok(view.detail.length <= 160);
  });
});
