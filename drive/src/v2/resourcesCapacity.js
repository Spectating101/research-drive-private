/**
 * Resources · Capacity & access band
 * Storage (vault/cache) · Services (Cursor Ask / BigQuery) · Desk (query engine / Tavily)
 */

import { identifyProviderMarkId } from "./providerMarkIds.js";

function pctOf(used, cap) {
  const u = Number(used);
  const c = Number(cap);
  if (!Number.isFinite(u) || !Number.isFinite(c) || c <= 0) return null;
  return Math.round((u / c) * 100);
}

function fmtGiB(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return null;
  if (v >= 100) return `${Math.round(v)} GiB`;
  if (v >= 10) return `${v.toFixed(1)} GiB`;
  return `${v.toFixed(2)} GiB`;
}

function meter({ id, name, metric, pct, available, warn = false, action = null, markId = null }) {
  return {
    id,
    name,
    metric,
    pct: Number.isFinite(pct) ? pct : null,
    available: available || null,
    warn: Boolean(warn),
    action,
    markId: markId || id,
  };
}

/**
 * Showcase-relevant capacity: vault + cache, Cursor Ask usage, BigQuery quota,
 * query engine, and Tavily keys. Drops NVMe / collectors / host parallel meters
 * (still available elsewhere in rollup if needed).
 */
export function buildCapacityAccessPairs(rollup) {
  const usage = rollup?.usage || {};
  const hero = rollup?.hero || {};
  const ai = rollup?.ai || {};
  const metered = rollup?.metered || {};
  const vault = usage.vault || hero.vault || {};
  const cache = usage.cache || {};
  const composer = hero.composer || {};
  const bq = metered.bigquery || {};

  const vaultPctRaw =
    vault.pct != null ? Number(vault.pct) : pctOf(vault.used_tb, vault.cap_tb);
  const vaultUsedRaw = vault.used_tb;
  const vaultCapRaw = vault.cap_tb;
  const vaultUsed =
    vaultUsedRaw === null || vaultUsedRaw === undefined || vaultUsedRaw === ""
      ? null
      : Number(vaultUsedRaw);
  const vaultCap =
    vaultCapRaw === null || vaultCapRaw === undefined || vaultCapRaw === ""
      ? null
      : Number(vaultCapRaw);
  const vaultObserved = vault.observed !== false && Number.isFinite(vaultUsed);
  const vaultPct = vaultObserved && Number.isFinite(vaultPctRaw) ? vaultPctRaw : null;
  const cachePct =
    cache.pct != null ? Number(cache.pct) : pctOf(cache.used_gb, cache.total_gb);

  const turnsToday = Number(ai.composer_turns_today ?? 0);
  const composerOk = Boolean(composer.configured ?? ai.composer_configured);
  const bqCapGiB =
    bq.default_max_gib != null
      ? Number(bq.default_max_gib)
      : bq.default_max_bytes_billed != null
        ? Number(bq.default_max_bytes_billed) / (1024 ** 3)
        : null;
  const bqToday = Number(bq.gib_billed_today ?? 0);
  const bqPct =
    Number.isFinite(bqCapGiB) && bqCapGiB > 0 ? pctOf(bqToday, bqCapGiB) : null;

  const storage = [
    meter({
      id: "vault",
      markId: "vault",
      name: vault.label || "Google Drive vault",
      metric: vaultObserved
        ? vaultUsed === 0 && Number.isFinite(vaultCap)
          ? `Empty · ${vaultCap} TB capacity`
          : `${vaultUsed}/${Number.isFinite(vaultCap) ? vaultCap : "?"} TB`
        : Number.isFinite(vaultCap)
          ? `${vaultCap} TB · use not observed`
          : "NOT OBSERVED",
      pct: vaultPct,
      available: vaultObserved
        ? Number.isFinite(vaultCap) && Number.isFinite(vaultUsed)
          ? `${Math.max(0, vaultCap - vaultUsed).toFixed(1)} TB available`
          : null
        : "NOT OBSERVED",
      warn: vaultPct != null && vaultPct >= 85,
    }),
    meter({
      id: "cache",
      markId: "cache",
      name: cache.label || "USB bulk cache",
      metric:
        cache.used_gb != null || cache.total_gb != null
          ? `${cache.used_gb ?? "?"}/${cache.total_gb ?? "?"} GB`
          : cache.mounted
            ? "Mounted"
            : "Not mounted",
      pct: cachePct,
      available:
        cache.total_gb != null && cache.used_gb != null
          ? `${Math.max(0, Number(cache.total_gb) - Number(cache.used_gb)).toFixed(0)} GB available`
          : null,
      warn: cachePct != null && cachePct >= 85,
      action: cachePct != null && cachePct >= 85 ? "CHECK" : null,
    }),
  ];

  const services = [
    meter({
      id: "cursor",
      markId: "cursor",
      name: "Cursor Ask",
      metric: composerOk
        ? turnsToday > 0
          ? `${turnsToday} turns today`
          : "Composer ready"
        : "Not configured",
      pct: null,
      available: composerOk
        ? `API key live · ${composer.model || ai.composer_model || "default"}`
        : "Set CURSOR_API_KEY for Ask",
      warn: !composerOk,
      action: composerOk ? null : "NEED",
    }),
    meter({
      id: "bigquery",
      markId: "bigquery",
      name: "BigQuery",
      metric: bq.configured
        ? [
            bq.project || "ADC ok",
            Number.isFinite(bqCapGiB) ? `${fmtGiB(bqCapGiB)} / query` : null,
          ]
            .filter(Boolean)
            .join(" · ")
        : "Not configured",
      pct: bqPct,
      available: bq.configured
        ? `${fmtGiB(bqToday) || "0 GiB"} billed today`
        : "ADC / project missing",
      warn: !bq.configured,
      action: bq.configured ? null : "NEED",
    }),
  ];

  // Desk = lab machines + Ask toolkit — not a raw :8765 port readout.
  const workers = hero.workers || {};
  const availableWorkers = (() => {
    if (workers.available != null) return Number(workers.available);
    if (workers.online != null || workers.idle != null) {
      return Number(workers.online || 0) + Number(workers.idle || 0);
    }
    return null;
  })();
  const identitiesReady = Number(availableWorkers ?? workers.ready ?? 0);
  const identitiesTotal = Number(workers.total ?? 0);
  const hostsJoined = Number(workers.joined ?? 0);
  const mcp = ai.mcp_tools || {};
  const mcpTotal = Number(mcp.total ?? hero.mcp_tools ?? 0);
  const mcpCore = Number(mcp.core ?? 0);
  const mcpAcquire = Number(mcp.acquire ?? 0);

  const desk = [
    meter({
      id: "fleet",
      markId: "fleet",
      name: "Lab fleet",
      metric:
        identitiesTotal > 0
          ? `${identitiesReady} / ${identitiesTotal} collectors`
          : "Fleet pending",
      pct: identitiesTotal > 0 ? pctOf(identitiesReady, identitiesTotal) : null,
      available:
        hostsJoined > 0 || workers.idle != null
          ? [
              hostsJoined > 0 ? `${hostsJoined} hosts joined` : null,
              workers.idle != null ? `${workers.idle ?? 0} idle` : null,
              workers.busy != null ? `${workers.busy ?? 0} busy` : null,
            ]
              .filter(Boolean)
              .join(" · ")
          : "Windows lab pool",
    }),
    meter({
      id: "mcp",
      markId: "mcp",
      name: "Ask tools",
      metric: mcpTotal > 0 ? `${mcpTotal} MCP tools` : composerOk ? "Composer ready" : "Not reported",
      pct: null,
      available:
        mcpTotal > 0
          ? [
              mcpCore > 0 ? `${mcpCore} core` : null,
              mcpAcquire > 0 ? `${mcpAcquire} acquire` : null,
              "procure · search · ops",
            ]
              .filter(Boolean)
              .join(" · ")
          : composerOk
            ? "Cursor Composer + desk MCP"
            : "Wire desk MCP for Ask",
      warn: mcpTotal <= 0 && !composerOk,
    }),
  ];

  return [
    { id: "storage", title: "Storage", meters: storage },
    { id: "services", title: "Services", meters: services },
    { id: "desk", title: "Desk", meters: desk },
  ];
}

/** Freeze authority vocabulary for source capability rows. */
export function sourceAuthorityLabel(row) {
  const status = String(row?.status || row?.authority || row?.access || "").toLowerCase();
  if (/observed|healthy|live|ok/.test(status)) return "OBSERVED";
  if (/unavailable|offline|denied|blocked/.test(status)) return "UNAVAILABLE";
  if (/conditional|probe|entitlement|approval/.test(status)) return "CONDITIONAL";
  if (/not[_ -]?checked|unknown|pending/.test(status)) return "NOT CHECKED";
  if (/route|defined|configured|ready/.test(status)) return "ROUTE DEFINED";
  if (row?.configured === false) return "UNAVAILABLE";
  if (row?.configured === true || row?.route) return "ROUTE DEFINED";
  return "NOT CHECKED";
}

export function groupSourceCapabilities(panels = []) {
  const families = {
    licensed: { id: "licensed", title: "Licensed / institutional", rows: [] },
    market: { id: "market", title: "Public market & filings", rows: [] },
    research: { id: "research", title: "Research & open data", rows: [] },
  };
  for (const panel of panels) {
    for (const row of panel?.rows || []) {
      const key = String(row.key || row.id || row.label || "").toLowerCase();
      const label = String(row.label || "");
      let family = "research";
      if (/lseg|crsp|capital.?iq|wrds|refinitiv|compustat/.test(key + label)) family = "licensed";
      else if (/sec|edgar|twse|mops|yahoo|coingecko|market|filing/.test(key + label)) family = "market";
      families[family].rows.push({
        id: row.key || row.id || label,
        name: label,
        access:
          row.metric ||
          row.route ||
          row.access ||
          row.sublabel ||
          row.detail ||
          "Access not described",
        authority: sourceAuthorityLabel(row),
        markId: identifyProviderMarkId(row),
        row,
      });
    }
  }
  return Object.values(families).filter((f) => f.rows.length);
}
