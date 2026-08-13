/** Demo catalog — loaded from config when API is offline (Playwright / local dev). */

import demoCatalog from "../../config/desk_demo_catalog.json";

export const DEMO_LABEL = demoCatalog.label || "DEMO";
export const SEED_DATASETS = demoCatalog.datasets || [];
export const DISCOVER_SUGGESTIONS = demoCatalog.discover_suggestions || [];
export const DISCOVER_SAMPLES = demoCatalog.discover_samples || [];

const UNMEASURED_DESK = {
  jobs: {},
  composer_configured: false,
  composer_model: "",
  mcp_tools: { total: 0, core: 0, acquire: 0, ops: 0 },
  storage_tiers: { canonical: { quota_tb: 5, used_tb: 0 }, cache: { used_pct: 0 } },
  gdrive: { ok: null },
  worker_pools: { busy: 0, total: 0 },
};

export const FALLBACK_HEALTH = {
  status: "demo",
  datasets: SEED_DATASETS.length,
  desk: { ...UNMEASURED_DESK },
};

export function resolveCatalog(liveRows) {
  const live = Array.isArray(liveRows) ? liveRows : [];
  if (live.length) return { catalog: live, usingSeed: false };
  return { catalog: SEED_DATASETS, usingSeed: true };
}

const NEUTRAL_DESK = { ...UNMEASURED_DESK };

/** Live desk health — never blend demo job fiction when API reports ok. */
export function mergeHealth(live) {
  const liveOk = live?.status === "ok";
  if (live && (liveOk || live.datasets || live.desk)) {
    return {
      ...live,
      status: live.status || (liveOk ? "ok" : "unknown"),
      datasets: live.datasets != null ? live.datasets : undefined,
      desk: liveOk
        ? { ...NEUTRAL_DESK, ...(live.desk || {}) }
        : { ...FALLBACK_HEALTH.desk, ...(live.desk || {}) },
    };
  }
  return FALLBACK_HEALTH;
}

/** Offline preview when query engine is unreachable — from catalog JSON only. */
export function previewSampleRows(dataset) {
  if (!dataset) return [];
  if (Array.isArray(dataset.preview_rows) && dataset.preview_rows.length) {
    return dataset.preview_rows;
  }
  const keys = dataset.join_keys?.length ? dataset.join_keys : ["date", "value"];
  const row = {};
  keys.forEach((k, i) => {
    if (k.includes("date") || k === "week") row[k] = "2026-04-30";
    else if (k.includes("country")) row[k] = "TW";
    else row[k] = i === 0 ? "sample" : "—";
  });
  return [row];
}

/** Filter demo discover rows when API discover/search is empty (offline dev / Playwright). */
export function discoverDemoSearch(query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  return DISCOVER_SAMPLES.filter((row) => {
    const hay = [
      row.title,
      row.name,
      row.dataset_id,
      row.source,
      row.description,
      row.collect_via,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q) || q.split(/\s+/).some((tok) => tok.length > 2 && hay.includes(tok));
  });
}

export function deskPipelineStrips(health, acquisitions = []) {
  const running = acquisitions.filter((a) => (a.stage || "running") === "running").slice(0, 3);
  if (running.length) return running;
  return [];
}
