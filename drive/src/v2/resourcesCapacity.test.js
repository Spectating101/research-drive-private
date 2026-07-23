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
  it("showcases vault/cache, Cursor/BQ, and compact lab fleet", () => {
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
    assert.match(byId.fleet.metric, /3 \/ 4/);
    assert.match(byId.mcp.metric, /86 MCP/);
  });
});
