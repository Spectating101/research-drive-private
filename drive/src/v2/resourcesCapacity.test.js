import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildCapacityAccessPairs } from "./resourcesCapacity.js";

const sampleRollup = {
  hero: {
    composer: { model: "default", configured: true },
    mcp_tools: 86,
    vault: { used_tb: 0.754, cap_tb: 3, pct: 25 },
    workers: { busy: 0, total: 4, online: 0, idle: 3, joined: 3, available: 3 },
  },
  ai: {
    composer_configured: true,
    composer_turns_today: 50,
    composer_model: "default",
    mcp_tools: { total: 86, core: 34, acquire: 14, ops: 38 },
  },
  metered: {
    bigquery: {
      configured: true,
      project: "search-485108",
      default_max_gib: 10,
      gib_billed_today: 0,
    },
    tavily: { keys_loaded: 4, live_enabled: false, calls_today: 0 },
  },
  usage: {
    vault: { label: "Google Drive vault", used_tb: 0.754, cap_tb: 3, pct: 25 },
    cache: {
      label: "Transcend bulk cache",
      mounted: true,
      used_gb: 1136.13,
      total_gb: 1863.01,
      pct: 61,
    },
    hot: { label: "NVMe desk", used_pct: 82, free_gb: 58 },
  },
};

describe("buildCapacityAccessPairs", () => {
  it("showcases vault/cache, Cursor/BQ, and compact collector fleet", () => {
    const pairs = buildCapacityAccessPairs(sampleRollup);
    assert.deepEqual(
      pairs.map((p) => p.id),
      ["storage", "services", "desk"],
    );
    const ids = pairs.flatMap((p) => p.meters.map((m) => m.id));
    assert.deepEqual(ids, ["vault", "cache", "cursor", "bigquery", "fleet", "mcp"]);
    assert.ok(!ids.includes("hot"));
    assert.ok(!ids.includes("query_engine"));
    assert.ok(!ids.includes("hosts"));
    assert.ok(!ids.includes("parallel"));

    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.match(byId.vault.name, /Google Drive/i);
    assert.match(byId.cache.name, /Transcend/i);
    assert.match(byId.cursor.metric, /50 turns/);
    assert.match(byId.bigquery.metric, /search-485108/);
    // VC-4: the fleet headline uses the shared collector vocabulary so the
    // card, toolbar, and rail cannot disagree. Identity readiness moved to the
    // detail line because it is a different operational dimension.
    assert.match(byId.fleet.metric, /^\d+ registered/);
    assert.match(byId.fleet.available, /3\/4 identities ready/);
    assert.match(byId.mcp.metric, /86 MCP/);
  });

  it("shows Composer unverified rather than Ready when /health.desk.composer_runtime is configured but not verified", () => {
    // Regression: desk_resources.py's hero.composer only ever carries
    // "configured", never a verified/runtime signal — the rollup alone can't
    // tell "key present" from "confirmed live." /health can, and it's
    // already available in the same view, so this must use it rather than
    // repeat the fabricated "Ready" claim that Settings had.
    const health = {
      desk: {
        composer_runtime: { status: "unverified", configured: true, verified: false, checked_at: null },
      },
    };
    const pairs = buildCapacityAccessPairs(sampleRollup, health);
    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.equal(byId.cursor.metric, "Unverified");
    assert.equal(byId.cursor.warn, true);
    assert.doesNotMatch(byId.cursor.metric, /^Composer ready$/);
  });

  it("keeps Composer ready when /health confirms a live-verified probe", () => {
    const health = {
      desk: {
        composer_runtime: { status: "ready", configured: true, verified: true, checked_at: "2026-08-12T10:00:00Z" },
      },
    };
    const pairs = buildCapacityAccessPairs(sampleRollup, health);
    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.match(byId.cursor.metric, /50 turns/);
    assert.equal(byId.cursor.warn, false);
  });

  it("shows Degraded rather than Ready for a failed probe, even though verified is true", () => {
    // Regression (caught in review): record_composer_failure() sets
    // verified: true because a real probe DID run — it just failed.
    const health = {
      desk: {
        composer_runtime: { status: "degraded", configured: true, verified: true, error_category: "timeout" },
      },
    };
    const pairs = buildCapacityAccessPairs(sampleRollup, health);
    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.equal(byId.cursor.metric, "Degraded");
    assert.equal(byId.cursor.warn, true);
    assert.doesNotMatch(byId.cursor.metric, /^Composer ready$/);
  });

  it("shows Needs recheck for a stale observation, distinct from never-probed", () => {
    const health = {
      desk: {
        composer_runtime: { status: "stale", configured: true, verified: false, age_seconds: 999 },
      },
    };
    const pairs = buildCapacityAccessPairs(sampleRollup, health);
    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.equal(byId.cursor.metric, "Needs recheck");
    assert.equal(byId.cursor.warn, true);
  });

  it("falls back to the prior configured-only behavior when no /health signal is available", () => {
    const pairs = buildCapacityAccessPairs(sampleRollup);
    const byId = Object.fromEntries(pairs.flatMap((p) => p.meters.map((m) => [m.id, m])));
    assert.match(byId.cursor.metric, /50 turns/);
    assert.equal(byId.cursor.warn, false);
  });
});
