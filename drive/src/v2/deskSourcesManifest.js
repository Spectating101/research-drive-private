/** Merge config/desk_sources.json with live desk telemetry (providers, not datasets). */

import manifest from "../../config/desk_sources.json";

export const DESK_SOURCE_MANIFEST = manifest;

function row(ok = true, warn = false, extra = {}) {
  return { ok, warn, ...extra };
}

export function buildLayerRows({ health, queryUp = true } = {}) {
  const engineUp = queryUp && (health?.status === "ok" || health?.status === "demo");
  const composerOk = !!health?.desk?.composer_configured;

  return (manifest.layers || []).map((layer) => {
    let ok = true;
    let warn = false;
    if (layer.id === "registry_catalog") ok = engineUp;
    if (layer.id === "web_discover" || layer.id === "probe_url") warn = !composerOk;

    return row(ok, warn, {
      kind: "layer",
      key: `layer-${layer.id}`,
      section: "Layers",
      label: layer.label,
      metric: layer.route,
      detail: layer.detail,
    });
  });
}

export function buildProviderRows({ health, ops, catalogSummary } = {}) {
  const desk = health?.desk || {};
  const dh = ops?.datacite_harvest;

  return (manifest.sources || [])
    .map((src) => {
    let ok = true;
    let warn = false;

    if (src.id === "gdrive_vault") {
      ok = desk.gdrive?.ok !== false;
      warn = desk.gdrive?.warn;
    }
    if (src.id === "datacite") {
      ok = dh?.ok !== false && dh?.status !== "warn" && dh?.status !== "degraded";
      warn = dh?.warn || dh?.status === "warn" || dh?.status === "degraded";
    }
    if (src.id === "bigquery") {
      warn = !desk.legacy_llm_configured && !desk.composer_configured;
    }
    // Never force vendor providers "ok" — readiness comes from live desk/ops only.

    const queueNote =
      catalogSummary?.queue_tasks != null
        ? `${catalogSummary.runnable_queue_tasks ?? 0}/${catalogSummary.queue_tasks} queue tasks`
        : null;

    return row(ok, warn, {
      kind: "source",
      key: `source-${src.id}`,
      section: "Sources",
      label: src.label,
      endpoint: src.endpoint,
      layers: (src.layers || []).join(" · "),
      routes: src.routes,
      collect_via: (src.collect_via || []).join(", "),
      metric: src.routes,
      detail: queueNote,
      manifest: src,
    });
  });
}

export function buildCapacitySnapshot({ health, catalogSummary, cluster }) {
  const desk = health?.desk || {};
  const tiers = desk.storage_tiers || {};
  const canonical = tiers.canonical || desk.archive || {};
  const mcp = desk.mcp_tools || {};
  const pools = desk.worker_pools;
  const wl = cluster?.worker_pools?.windows_lab;

  const vaultUsed = canonical.used_tb;
  const vaultCap = canonical.quota_tb ?? canonical.pool_tb;
  const vaultPct = vaultUsed != null && vaultCap ? Math.round((vaultUsed / vaultCap) * 100) : null;

  const curatedSources = manifest.sources || [];

  return {
    sourceCount: curatedSources.length,
    layerCount: (manifest.layers || []).length,
    tools: {
      mcp: mcp.total ?? null,
      connectors: catalogSummary?.connectors ?? null,
    },
    vault: { used: vaultUsed, cap: vaultCap, pct: vaultPct, ok: desk.gdrive?.ok !== false },
    workers: {
      busy: pools?.busy ?? wl?.joined ?? 0,
      total: pools?.total ?? wl?.total ?? "—",
    },
    composer: {
      model: desk.composer_model || "composer-2.5",
      ok: !!desk.composer_configured,
      legacy: !!desk.legacy_llm_configured,
    },
    queryEngine: {
      up: health?.status === "ok" || health?.status === "demo",
      port: ":8765",
    },
  };
}
