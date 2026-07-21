/**
 * Resources · Sources capacity band — RESOURCES_FULL_SCALE_FREEZE §2.2
 * Three paired rows: Storage | Access | Execution (max 6 meters).
 */

function pctOf(used, cap) {
  const u = Number(used);
  const c = Number(cap);
  if (!Number.isFinite(u) || !Number.isFinite(c) || c <= 0) return null;
  return Math.round((u / c) * 100);
}

function meter({ id, name, metric, pct, available, warn = false, action = null }) {
  return {
    id,
    name,
    metric,
    pct: Number.isFinite(pct) ? pct : null,
    available: available || null,
    warn: Boolean(warn),
    action,
  };
}

export function buildCapacityAccessPairs(rollup) {
  const usage = rollup?.usage || {};
  const hero = rollup?.hero || {};
  const vault = usage.vault || hero.vault || {};
  const cache = usage.cache || {};
  const hot = usage.hot || {};
  const workers = hero.workers || {};
  const connect = rollup?.connect || {};
  const compute = rollup?.compute || {};

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
  const hotPct = hot.used_pct != null ? Number(hot.used_pct) : null;

  const identitiesReady = Number(connect.identities_ready ?? connect.ready ?? workers.ready ?? 0);
  const identitiesTotal = Number(connect.identities_total ?? connect.total ?? workers.total ?? 0);
  const hostsJoined = Number(connect.hosts_joined ?? connect.joined ?? compute.hosts_joined ?? 0);
  const hostsTotal = Number(connect.hosts_total ?? connect.total_hosts ?? compute.hosts_total ?? 0);
  const parallelActive = Number(workers.busy ?? compute.parallel_active ?? 0);
  const parallelMax = Number(workers.total ?? compute.parallel_max ?? 0);

  const storage = [
    meter({
      id: "vault",
      name: vault.label || "GDrive vault",
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

  const access = [
    meter({
      id: "hot",
      name: hot.label || "Working disk",
      metric:
        hotPct != null && hot.free_gb != null
          ? `${Math.round(Number(hot.free_gb) * 10) / 10} GB free · ${Math.round(hotPct)}% used`
          : hot.free_gb != null
            ? `${Math.round(Number(hot.free_gb) * 10) / 10} GB free`
            : hotPct != null
              ? `${Math.round(hotPct)}% used`
              : "Capacity pending",
      pct: hotPct,
      available: hotPct != null ? `${Math.max(0, 100 - Math.round(hotPct))}% headroom` : null,
      warn: hot.headroom_ok === false || (hotPct != null && hotPct >= 85),
    }),
    meter({
      id: "identities",
      name: "Collector identities",
      metric:
        identitiesTotal > 0
          ? `${identitiesReady} / ${identitiesTotal} ready`
          : workers.total != null
            ? `${workers.busy ?? 0} / ${workers.total} busy`
            : "Not reported",
      pct: identitiesTotal > 0 ? pctOf(identitiesReady, identitiesTotal) : null,
    }),
  ];

  const execution = [
    meter({
      id: "hosts",
      name: "Connected hosts",
      metric: hostsTotal > 0 ? `${hostsJoined} / ${hostsTotal} joined` : "Cluster pending",
      pct: hostsTotal > 0 ? pctOf(hostsJoined, hostsTotal) : null,
    }),
    meter({
      id: "parallel",
      name: "Parallel capacity",
      metric: parallelMax > 0 ? `${parallelActive} / ${parallelMax} active` : "Not reported",
      pct: parallelMax > 0 ? pctOf(parallelActive, parallelMax) : null,
    }),
  ];

  return [
    { id: "storage", title: "Storage", meters: storage },
    { id: "access", title: "Access", meters: access },
    { id: "execution", title: "Execution", meters: execution },
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
        access: row.detail || row.sublabel || row.access || row.route || "Access not described",
        authority: sourceAuthorityLabel(row),
        row,
      });
    }
  }
  return Object.values(families).filter((f) => f.rows.length);
}
