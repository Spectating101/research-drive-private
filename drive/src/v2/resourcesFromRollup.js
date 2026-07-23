/** Map GET /library/desk/resources rollup → Resources ledger rows. */

import { buildLayerRows, buildProviderRows } from "@/v2/deskSourcesManifest";
import {
  buildRunningRows,
  buildStackRows,
  buildStorageRows,
} from "@/v2/resourcesLedger";

function rowBase(row) {
  return { ok: true, warn: false, showStatus: false, ...row };
}

function fmtGiB(gib) {
  if (gib == null || gib === 0) return "—";
  if (gib < 0.01) return "<0.01 GiB today";
  return `${gib} GiB today`;
}

function fmtCapGiB(bytes) {
  if (bytes == null) return null;
  const gib = Math.round(bytes / 1024 ** 3);
  return `${gib} GiB/query cap`;
}

export function buildHeroFromRollup(rollup, { health, catalogSummary, cluster } = {}) {
  if (!rollup?.hero) return null;
  const h = rollup.hero;
  const vault = h.vault || {};
  const workers = h.workers || {};
  const chips = h.chips || {};
  const online = workers.online ?? null;
  const idle = workers.idle ?? null;
  const available =
    workers.available != null
      ? workers.available
      : online != null || idle != null
        ? Number(online || 0) + Number(idle || 0)
        : null;
  return {
    composer: h.composer || {},
    mcp: rollup.ai?.mcp_tools?.total ?? null,
    queryEngine: h.query_engine || { port: ":8765", up: false },
    workers: {
      busy: workers.busy ?? 0,
      total: workers.total ?? "—",
      online,
      idle,
      stale: workers.stale ?? null,
      joined: workers.joined ?? null,
      available,
    },
    vault: {
      used: vault.used_tb,
      cap: vault.cap_tb,
      pct: vault.pct,
    },
    chips,
    catalogSummary,
    cluster,
    health,
  };
}

export function buildAiRows(rollup) {
  if (!rollup?.ai) return [];
  const ai = rollup.ai;
  const rows = [
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "composer",
      label: `Ask · ${ai.composer_model || "composer-2.5"}`,
      metric: ai.composer_configured ? "Composer + MCP" : "Composer not configured",
      ok: ai.composer_configured,
      warn: !ai.composer_configured,
      showStatus: !ai.composer_configured,
    }),
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "mcp",
      label: "Procurement MCP",
      metric: ai.mcp_tools?.total
        ? `${ai.mcp_tools.total} tools (${ai.mcp_tools.core} core · ${ai.mcp_tools.acquire} acquire · ${ai.mcp_tools.ops} ops)`
        : "—",
    }),
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "query-engine",
      label: "Query engine",
      metric: `:8765 ${rollup.hero?.query_engine?.up ? "up" : "down"}`,
      ok: rollup.hero?.query_engine?.up,
      showStatus: !rollup.hero?.query_engine?.up,
    }),
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "desk-token",
      label: "Desk token",
      metric: ai.desk_token_required ? "required" : "open",
      ok: true,
      showStatus: false,
    }),
  ];
  if (ai.composer_turns_today > 0) {
    rows.push(
      rowBase({
        section: "AI & tools",
        kind: "ai",
        key: "composer-turns",
        label: "Composer turns",
        metric: `${ai.composer_turns_today} today`,
        ok: true,
        showStatus: false,
      }),
    );
  }
  return rows;
}

export function buildMeteredRows(rollup) {
  if (!rollup?.metered) return [];
  const m = rollup.metered;
  const bq = m.bigquery || {};
  const tv = m.tavily || {};
  const hf = m.huggingface || {};
  const cred = m.collect_credentials || {};
  const gov = m.governance_budgets || {};

  const bqCap = fmtCapGiB(bq.default_max_bytes_billed);
  const bqToday = fmtGiB(bq.gib_billed_today);

  const rows = [
    rowBase({
      section: "Metered",
      kind: "metered",
      key: "bigquery",
      label: "BigQuery",
      metric: [
        bq.project || (bq.configured ? "ADC ok" : "not configured"),
        bqCap,
        bqToday !== "—" ? bqToday : null,
      ]
        .filter(Boolean)
        .join(" · "),
      ok: bq.configured,
      warn: !bq.configured,
      showStatus: !bq.configured,
    }),
    rowBase({
      section: "Metered",
      kind: "metered",
      key: "tavily",
      label: "Tavily discover",
      metric: [
        tv.keys_loaded ? `${tv.keys_loaded} keys` : "no keys",
        tv.live_enabled ? "live on" : "live off",
        gov.max_tavily_live_per_magic != null ? `${gov.max_tavily_live_per_magic}/procure cap` : null,
        tv.calls_today ? `${tv.calls_today} today` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      ok: tv.keys_loaded > 0,
      warn: tv.live_enabled && !tv.keys_loaded,
      showStatus: tv.live_enabled && !tv.keys_loaded,
    }),
    rowBase({
      section: "Metered",
      kind: "metered",
      key: "huggingface",
      label: "HuggingFace",
      metric: hf.configured ? "token configured" : "public only",
      ok: true,
      showStatus: false,
    }),
  ];

  if (cred.total_profiles) {
    rows.push(
      rowBase({
        section: "Metered",
        kind: "metered",
        key: "collect-tokens",
        label: "Collect tokens",
        metric: `${cred.configured}/${cred.total_profiles} profiles`,
        ok: true,
        showStatus: false,
      }),
    );
  }

  return rows;
}

export function buildUsageRowsFromRollup(rollup) {
  if (!rollup?.usage) return [];
  const u = rollup.usage;
  const rows = [];

  const vault = u.vault || {};
  if (vault.used_tb != null || vault.cap_tb != null) {
    const pct = vault.pct;
    rows.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "vault",
        label: vault.label || "GDrive vault",
        metric: `${vault.used_tb ?? "?"}/${vault.cap_tb ?? "?"} TB`,
        progress: pct,
        ok: vault.ok !== false,
        warn: pct != null && pct >= 75,
        showStatus: pct != null && pct >= 75,
      }),
    );
  }

  const hot = u.hot || {};
  if (hot.used_pct != null || hot.free_gb != null) {
    const pct = Number(hot.used_pct);
    rows.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "nvme",
        label: hot.label || "NVMe hot desk",
        metric: hot.free_gb != null ? `${hot.free_gb} GB free` : `${pct}% used`,
        progress: Number.isFinite(pct) ? pct : null,
        ok: hot.headroom_ok !== false,
        warn: hot.headroom_ok === false || pct >= 85,
        showStatus: hot.headroom_ok === false || pct >= 85,
      }),
    );
  }

  const cache = u.cache || {};
  if (cache.used_gb != null || cache.total_gb != null || cache.mounted === false) {
    const mounted = cache.mounted !== false;
    const pct = cache.pct;
    rows.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "bulk-cache",
        label: cache.label || "USB bulk cache",
        metric: mounted
          ? cache.total_gb
            ? `${cache.used_gb ?? "?"}/${cache.total_gb} GB`
            : "mounted"
          : "offline",
        progress: pct,
        ok: mounted,
        warn: !mounted || (pct != null && pct >= 85),
        showStatus: !mounted || (pct != null && pct >= 85),
      }),
    );
  }

  if (u.staging_disk_free_gb != null) {
    rows.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "staging-disk",
        label: "Controller staging",
        metric: `${u.staging_disk_free_gb} GB free`,
        ok: true,
        showStatus: false,
      }),
    );
  }

  return rows;
}

export function buildMotionRowsFromRollup(rollup, jobs = []) {
  const running = buildRunningRows({
    health: { desk: { jobs: rollup?.motion?.jobs } },
    ops: {
      collection_queue: rollup?.motion?.gdelt,
      datacite_harvest: rollup?.motion?.datacite,
    },
    jobs,
  });

  const motion = rollup?.motion || {};
  const jobStats = motion.jobs || {};

  const extra = [];
  if (jobStats.pending_approval > 0) {
    extra.push(
      rowBase({
        section: "Motion",
        kind: "motion",
        key: "jobs-pending",
        label: "Awaiting approval",
        metric: `${jobStats.pending_approval} job(s) awaiting review`,
        ok: false,
        warn: true,
        showStatus: true,
        priority: 0,
      }),
    );
  }
  if (jobStats.running > 0) {
    extra.push(
      rowBase({
        section: "Motion",
        kind: "motion",
        key: "jobs-running",
        label: "Running now",
        metric: `${jobStats.running} job(s)`,
        priority: 1,
      }),
    );
  }

  const actionable = jobStats.actionable && typeof jobStats.actionable === "object" ? jobStats.actionable : {};
  const failedActionable = Number(
    jobStats.failed_actionable ?? actionable.failed_actionable ?? 0,
  );
  if (failedActionable > 0) {
    const days = Number(jobStats.recent_days ?? actionable.failed_recent_days ?? 7);
    extra.push(
      rowBase({
        section: "Motion",
        kind: "motion",
        key: "jobs-failed-actionable",
        label: "Actionable failures",
        metric: `${failedActionable} in last ${days}d`,
        ok: false,
        warn: true,
        showStatus: true,
        priority: 0,
      }),
    );
  }

  if (motion.campaigns_active > 0) {
    extra.push(
      rowBase({
        section: "Motion",
        kind: "motion",
        key: "campaigns",
        label: "Procurement campaigns",
        metric: `${motion.campaigns_active} in progress`,
        priority: 1,
      }),
    );
  }

  const dc = motion.datacite || {};
  const hasDataciteRow = running.some((r) => r.key === "datacite-harvest");
  if (dc.total_percent != null && !hasDataciteRow) {
    extra.push(
      rowBase({
        section: "Motion",
        kind: "motion",
        key: "datacite-harvest-summary",
        label: "DataCite harvest",
        metric:
          dc.shard_workers != null
            ? `${dc.total_percent}% · ${dc.shard_workers} workers`
            : `${dc.total_percent}% of index`,
        progress: Number(dc.total_percent),
        priority: 2,
      }),
    );
  }

  return [...extra, ...running.map((r) => ({ ...r, section: "Motion", showStatus: r.warn || !r.ok }))].slice(
    0,
    12,
  );
}

export function buildComputeRowsFromRollup(rollup) {
  if (!rollup?.compute) return [];
  const c = rollup.compute;
  const wl = c.windows_lab || {};
  const heroWorkers = rollup?.hero?.workers || {};
  const q = c.queue || {};
  const online = heroWorkers.online ?? wl.online ?? null;
  const idle = heroWorkers.idle ?? wl.idle ?? null;
  const available =
    heroWorkers.available != null
      ? heroWorkers.available
      : online != null || idle != null
        ? Number(online || 0) + Number(idle || 0)
        : null;
  const busy = heroWorkers.busy ?? wl.busy ?? null;
  const joined = heroWorkers.joined ?? wl.joined ?? null;
  const total = heroWorkers.total ?? wl.total;
  const loadPct =
    typeof busy === "number" && typeof total === "number" && total > 0
      ? Math.round((busy / total) * 100)
      : null;
  const availability =
    available != null && total != null
      ? `${available}/${total} available`
      : joined != null && total != null
        ? `${joined}/${total} joined`
        : busy != null && total != null
          ? `${busy}/${total} busy`
          : "—";
  const detailParts = [];
  if (online != null || idle != null) {
    detailParts.push(`online ${online ?? 0} · idle ${idle ?? 0}`);
  }
  if (wl.max_parallel) detailParts.push(`max parallel ${wl.max_parallel}`);

  return [
    rowBase({
      section: "Compute",
      kind: "compute",
      key: "controller",
      label: `Controller · ${c.controller || "optiplex"}`,
      metric: "UI · orchestration",
    }),
    rowBase({
      section: "Compute",
      kind: "compute",
      key: "workers",
      label: "windows_lab",
      metric: availability,
      progress: loadPct,
      detail: detailParts.length ? detailParts.join(" · ") : null,
    }),
    rowBase({
      section: "Compute",
      kind: "compute",
      key: "queue-tasks",
      label: "Collection queue",
      metric:
        q.runnable_tasks != null && q.total_tasks != null
          ? `${q.runnable_tasks}/${q.total_tasks} runnable`
          : q.open != null
            ? `${q.open} open`
            : "—",
    }),
  ];
}

export function buildFallbackPanels(ctx) {
  const { health, ops, jobs, catalogSummary, cluster } = ctx;
  const desk = health?.desk || {};
  const stackRows = buildStackRows({ health, catalogSummary, cluster });
  const storageRows = buildStorageRows({ health }).map((r) => ({
    ...r,
    showStatus: r.warn || !r.ok,
  }));

  const aiKeys = new Set(["composer", "mcp"]);
  const ai = stackRows
    .filter((r) => aiKeys.has(r.key))
    .map((r) => ({
      ...r,
      section: "AI & tools",
      kind: "ai",
      showStatus: r.warn || !r.ok,
    }));

  const compute = stackRows
    .filter((r) => !aiKeys.has(r.key))
    .map((r) => ({
      ...r,
      section: "Compute",
      kind: "compute",
      showStatus: r.warn || !r.ok,
    }));

  const metered = [
    rowBase({
      section: "Metered",
      kind: "metered",
      key: "bigquery",
      label: "BigQuery",
      metric: "check Settings when API offline",
      ok: true,
      showStatus: false,
    }),
    rowBase({
      section: "Metered",
      kind: "metered",
      key: "tavily",
      label: "Tavily discover",
      metric: "rollup unavailable",
      ok: true,
      showStatus: false,
    }),
  ];

  const motion = buildRunningRows({ health, ops, jobs }).map((r) => ({
    ...r,
    section: "Motion",
    showStatus: r.warn || !r.ok,
  }));

  const extraAi = [
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "query-engine",
      label: "Query engine",
      metric: `:8765 ${health?.status === "ok" ? "up" : "down"}`,
      ok: health?.status === "ok" || health?.status === "demo",
      showStatus: health?.status !== "ok" && health?.status !== "demo",
    }),
    rowBase({
      section: "AI & tools",
      kind: "ai",
      key: "desk-token",
      label: "Desk token",
      metric: desk.desk_token_required ? "required" : "open",
    }),
  ];

  const providers = buildProviderRows({ health, ops, catalogSummary });
  const layers = buildLayerRows({ health });

  const allRows = [...ai, ...extraAi, ...metered, ...storageRows, ...motion, ...compute, ...providers, ...layers];

  return {
    hero: null,
    ai: [...ai, ...extraAi],
    metered,
    usage: storageRows,
    motion,
    compute,
    providers,
    layers,
    connect: { source_count: providers.length, layer_count: layers.length },
    issuesCount: allRows.filter((r) => r.warn || !r.ok).length,
    issuesFromRollup: [],
    offline: true,
  };
}

export function buildResourcesPanels({
  rollup,
  rollupLoading = false,
  health,
  ops,
  jobs,
  catalogSummary,
  cluster,
  queryUp = true,
}) {
  const ctx = { health, ops, jobs, catalogSummary, cluster, queryUp };
  const providers = buildProviderRows({ health, ops, catalogSummary });
  const layers = buildLayerRows({ health, queryUp });
  if (!rollup) {
    if (rollupLoading) {
      return {
        hero: null,
        ai: [],
        metered: [],
        usage: [],
        motion: [],
        compute: [],
        providers,
        layers,
        connect: { source_count: providers.length, layer_count: layers.length },
        issuesCount: 0,
        issuesFromRollup: [],
        offline: false,
        syncing: true,
      };
    }
    return buildFallbackPanels(ctx);
  }

  const ai = buildAiRows(rollup);
  const metered = buildMeteredRows(rollup);
  const usage = buildUsageRowsFromRollup(rollup);
  const motion = buildMotionRowsFromRollup(rollup, jobs);
  const compute = buildComputeRowsFromRollup(rollup);
  const issuesFromRollup = rollup?.issues || [];
  const issuesCount = rollup?.issues_count ?? issuesFromRollup.length;

  return {
    hero: buildHeroFromRollup(rollup, ctx),
    ai,
    metered,
    usage,
    motion,
    compute,
    providers,
    layers,
    connect: rollup?.connect || {
      source_count: providers.length,
      layer_count: layers.length,
    },
    issuesCount,
    issuesFromRollup,
    offline: false,
    syncing: Boolean(rollupLoading),
  };
}

export function filterResourcesViewV2(view, panels) {
  const { ai, metered, usage, motion, compute, providers, layers } = panels;
  const bad = (rows) => rows.filter((r) => r.warn || !r.ok);
  const attention = [
    ...bad(ai),
    ...bad(metered),
    ...bad(usage),
    ...bad(motion),
    ...bad(compute),
    ...bad(providers),
    ...bad(layers),
  ];

  const empty = {
    ai: [],
    metered: [],
    usage: [],
    motion: [],
    compute: [],
    providers: [],
    layers: [],
    attention: [],
  };

  if (view === "overview") {
    return { ...empty, attention };
  }
  if (view === "ai") {
    return { ...empty, ai, compute };
  }
  if (view === "usage") {
    return { ...empty, metered, usage };
  }
  if (view === "motion" || view === "running") {
    return { ...empty, motion };
  }
  if (view === "connect") {
    return { ...empty, providers, layers };
  }
  if (view === "issues") {
    return {
      ...empty,
      ai: bad(ai),
      metered: bad(metered),
      usage: bad(usage),
      motion: bad(motion),
      compute: bad(compute),
      providers: bad(providers),
      layers: bad(layers),
      attention: bad(attention),
    };
  }
  return { ...empty, ai, metered, usage, motion, compute, providers, layers, attention };
}
