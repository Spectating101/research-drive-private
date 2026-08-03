import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPickUp,
  buildRecommendedEvidence,
  buildResourceHeadroom,
  buildRecentTrail,
  projectRollupFromHealth,
} from "./homeIteration10.js";

test("pick up prefers recent library asset as primary", () => {
  const { primary, secondary } = buildPickUp({
    datasets: [
      { dataset_id: "a", name: "Alpha", analysis_readiness: "query_ready" },
      { dataset_id: "b", name: "Beta", analysis_readiness: "metadata_search" },
    ],
    jobs: [],
    health: { desk: { jobs: {} } },
  });
  assert.ok(primary);
  assert.equal(primary.kind, "library_asset");
  assert.match(primary.title, /Alpha|Beta/);
  assert.equal(secondary?.kind, "library_asset");
});

test("folder location never stringifies objects as [object Object]", () => {
  const { primary } = buildPickUp({
    datasets: [
      {
        dataset_id: "a",
        name: "Alpha",
        folder: { name: "asia_panels", path: "asia_panels" },
      },
    ],
    jobs: [],
    health: { desk: { jobs: {} } },
  });
  assert.match(primary.location, /ASIA PANELS|LIBRARY/);
  assert.doesNotMatch(primary.location, /object Object/i);
});

test("health projection lets Home paint headroom before desk/resources", () => {
  const projected = projectRollupFromHealth({
    desk: {
      composer_configured: true,
      composer_model: "default",
      storage_tiers: {
        canonical: { label: "Google Drive vault", quota_tb: 3, used_tb: 0.75, pct: 25 },
        cache: { label: "Transcend bulk cache", used_gb: 100, total_gb: 200, pct: 50, mounted: true },
      },
    },
  });
  const slots = buildResourceHeadroom(projected);
  assert.equal(slots[0].id, "vault");
  assert.equal(slots[1].id, "cache");
  assert.equal(slots[2].id, "cursor");
});

test("resource headroom prefers cache + Cursor Ask over NVMe", () => {
  const slots = buildResourceHeadroom({
    usage: {
      vault: { used_tb: 0.754, cap_tb: 3, pct: 25, label: "Google Drive vault" },
      hot: { used_pct: 83.40000000000001, free_gb: 50.9123, label: "NVMe desk" },
      cache: {
        label: "Transcend bulk cache",
        used_gb: 1136.13,
        total_gb: 1863.01,
        pct: 61,
        mounted: true,
      },
    },
    hero: { composer: { configured: true, model: "default" } },
    ai: { composer_configured: true, composer_turns_today: 50 },
  });
  assert.equal(slots.length, 3);
  assert.equal(slots[0].id, "vault");
  assert.equal(slots[1].id, "cache");
  assert.equal(slots[2].id, "cursor");
  assert.match(slots[1].headroom, /^39% headroom$/);
  assert.match(slots[2].metric, /50 turns/);
  assert.ok(!slots.some((s) => s.id === "hot"));
});

test("pending approval becomes secondary decision, not a separate Attention page", () => {
  const { secondary, pending } = buildPickUp({
    datasets: [{ dataset_id: "a", name: "Alpha" }],
    jobs: [{ id: "j1", status: "pending_approval", plan: { title: "MOPS statements" } }],
    health: { desk: { jobs: { pending_approval: 1 } } },
  });
  assert.equal(pending, 1);
  assert.equal(secondary.kind, "decision");
  assert.equal(secondary.action, "review");
  assert.match(secondary.title, /MOPS/);
});

test("resource headroom caps at three showcase slots", () => {
  const slots = buildResourceHeadroom({
    usage: {
      vault: { used_tb: 2.1, cap_tb: 5, pct: 42, label: "GDrive vault" },
      hot: { used_pct: 90, free_gb: 51, label: "Working disk", headroom_ok: false },
      cache: { used_gb: 1.8, total_gb: 2, pct: 90 },
    },
    metered: { bigquery: { configured: true, project: "demo", default_max_gib: 10, gib_billed_today: 1 } },
  });
  assert.equal(slots.length, 3);
  assert.equal(slots[0].pinned, true);
  assert.equal(slots[1].id, "cache");
  assert.equal(slots[1].warn, true);
  assert.equal(slots[2].id, "bigquery");
});

test("recommended evidence uses profile procurement recommendations", () => {
  const rows = buildRecommendedEvidence({
    procurement_recommendations: [
      { prompt: "Historical USDT transfers", source_route: "datacite", search_query: "USDT" },
      { prompt: "Issuer reserves", source_route: "vault", dataset_id: "issuer_x" },
    ],
  });
  assert.ok(rows.length <= 2);
  assert.ok(rows[0].badge);
});

test("recent trail prefers durable jobs", () => {
  const trail = buildRecentTrail({
    jobs: [
      { id: "1", status: "completed", title: "MOPS panel", updated_at: "2026-07-20T10:00:00Z" },
      { id: "2", status: "running", title: "GDELT Asia", updated_at: "2026-07-20T11:00:00Z" },
    ],
    datasets: [],
  });
  assert.equal(trail.length, 2);
  assert.match(trail[0].kind, /REFRESH|COLLECTION|PROCUREMENT/);
});

test("recent trail fences triage fixture noise and collapses duplicates", () => {
  const trail = buildRecentTrail({
    jobs: [
      {
        id: "n1",
        status: "cancelled",
        title: "Collect USDT",
        error: "triage noise: fixture_http_manifest_stuck",
        updated_at: "2026-07-21T10:00:00Z",
      },
      {
        id: "n2",
        status: "cancelled",
        title: "Collect USDT",
        error: "triage noise: fixture_http_manifest_stuck",
        updated_at: "2026-07-21T10:01:00Z",
      },
      {
        id: "ok",
        status: "completed",
        title: "TWSE governance panel",
        updated_at: "2026-07-21T09:00:00Z",
      },
    ],
    datasets: [],
  });
  assert.equal(trail.length, 1);
  assert.match(trail[0].title, /TWSE/);
  assert.equal(trail[0].kind, "COLLECTION COMPLETED");
});
