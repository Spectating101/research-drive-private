/** Resources — running jobs, stack, storage (sources/layers live in deskSourcesManifest.js). */

function fracProgress(text) {
  const m = String(text || "").match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
  if (!m) return null;
  const num = Number(m[1]);
  const den = Number(m[2]);
  if (!den) return null;
  return Math.round((num / den) * 100);
}

function rowBase(row) {
  return { ok: true, warn: false, ...row };
}

const ACTIVE_JOB_STATUS = new Set(["running", "pending_approval", "queued"]);

export function buildRunningRows({ health, ops, jobs = [] }) {
  const list = [];
  const desk = health?.desk || {};
  const cq = ops?.collection_queue;
  const dh = ops?.datacite_harvest;

  const activeJobs = jobs.filter((job) => ACTIVE_JOB_STATUS.has(String(job.status || "")));
  for (const job of activeJobs.slice(0, 8)) {
    const st = job.status || "unknown";
    const title = job.plan?.title || job.type || job.name || job.id;
    list.push(
      rowBase({
        section: "Running",
        kind: "active",
        key: `job-${job.id}`,
        label: title,
        metric: st.replace(/_/g, " "),
        ok: st === "completed" || st === "running",
        warn: st === "pending_approval" || st === "queued",
        job,
        priority: st === "pending_approval" ? 0 : st === "running" ? 1 : 2,
      }),
    );
  }

  const gdelt = desk.jobs?.gdelt_progress ?? cq?.gdelt_progress;
  if (gdelt) {
    list.push(
      rowBase({
        section: "Running",
        kind: "active",
        key: "gdelt",
        label: "GDELT pipeline",
        metric: String(gdelt),
        progress: fracProgress(gdelt),
        priority: 3,
        meta: cq,
      }),
    );
  }

  if (dh && typeof dh === "object") {
    const workers = dh.running ?? dh.active_workers;
    list.push(
      rowBase({
        section: "Running",
        kind: "active",
        key: "datacite-harvest",
        label: "DataCite harvest",
        metric: workers != null ? `${workers} workers` : dh.status || "running",
        ok: dh.ok !== false && dh.status !== "warn" && dh.status !== "degraded",
        warn: dh.warn || dh.status === "warn" || dh.status === "degraded",
        priority: 2,
        meta: dh,
      }),
    );
  }

  const open = cq?.pending ?? cq?.queued ?? cq?.open;
  if (open != null && Number(open) > 0) {
    list.push(
      rowBase({
        section: "Running",
        kind: "active",
        key: "collection_queue",
        label: "Collection queue",
        metric: `${open} open`,
        priority: 4,
        meta: cq,
      }),
    );
  }

  return list.sort((a, b) => (a.priority ?? 9) - (b.priority ?? 9));
}

export function buildStackRows({ health, catalogSummary, cluster }) {
  const list = [];
  const desk = health?.desk || {};
  const mcp = desk.mcp_tools || {};
  const pools = desk.worker_pools;
  const wl = cluster?.worker_pools?.windows_lab;

  const composerOk = !!desk.composer_configured;
  list.push(
    rowBase({
      section: "Desk stack",
      kind: "stack",
      key: "composer",
      label: `Ask · ${desk.composer_model || "composer-2.5"}`,
      metric: composerOk ? "Composer + MCP" : "Composer not configured",
      ok: composerOk,
      warn: !composerOk,
    }),
  );

  if (mcp.total) {
    list.push(
      rowBase({
        section: "Desk stack",
        kind: "stack",
        key: "mcp",
        label: "Procurement MCP",
        metric: `${mcp.total} tools · ${mcp.core} core · ${mcp.acquire} acquire · ${mcp.ops} ops`,
      }),
    );
  }

  if (catalogSummary) {
    list.push(
      rowBase({
        section: "Desk stack",
        kind: "stack",
        key: "connectors",
        label: "Saved connectors",
        metric: `${catalogSummary.connectors ?? 0} source URLs`,
      }),
    );
    list.push(
      rowBase({
        section: "Desk stack",
        kind: "stack",
        key: "queue-tasks",
        label: "Collection queue",
        metric: `${catalogSummary.runnable_queue_tasks ?? 0} runnable of ${catalogSummary.queue_tasks ?? 0} tasks`,
      }),
    );
    if (catalogSummary.pipelines) {
      list.push(
        rowBase({
          section: "Desk stack",
          kind: "stack",
          key: "pipelines",
          label: "Worker pipelines",
          metric: `${catalogSummary.pipelines} registered`,
        }),
      );
    }
  }

  const controller = cluster?.controller || "optiplex";
  list.push(
    rowBase({
      section: "Desk stack",
      kind: "stack",
      key: "controller",
      label: `Controller · ${controller}`,
      metric: "UI · orchestration",
    }),
  );

  if (pools?.total != null || pools?.busy != null) {
    list.push(
      rowBase({
        section: "Desk stack",
        kind: "stack",
        key: "workers",
        label: "windows_lab",
        metric: `${pools.busy ?? 0}/${pools.total ?? "—"} busy`,
        progress:
          typeof pools.total === "number" && pools.total > 0
            ? Math.round(((pools.busy ?? 0) / pools.total) * 100)
            : null,
      }),
    );
  } else if (wl) {
    list.push(
      rowBase({
        section: "Desk stack",
        kind: "stack",
        key: "workers",
        label: "windows_lab",
        metric: `${wl.joined ?? 0}/${wl.total ?? "—"} hosts`,
        ok: (wl.joined ?? 0) > 0,
        warn: (wl.total ?? 0) > 0 && (wl.joined ?? 0) < wl.total,
      }),
    );
  }

  return list;
}

export function buildStorageRows({ health }) {
  const list = [];
  const desk = health?.desk || {};
  const tiers = desk.storage_tiers || {};
  const canonical = tiers.canonical || desk.archive;
  const hot = tiers.hot || {};
  const cache = tiers.cache || desk.bulk_storage;

  if (canonical) {
    const used = canonical.used_tb;
    const quota = canonical.quota_tb ?? canonical.pool_tb;
    const pct = used != null && quota ? Math.round((used / quota) * 100) : null;
    list.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "vault",
        label: canonical.label || "GDrive vault",
        metric: `${used ?? "?"}/${quota ?? "?"} TB`,
        progress: pct,
        ok: desk.gdrive?.ok !== false,
        warn: pct != null && pct >= 75,
      }),
    );
  }

  if (hot && (hot.used_pct != null || hot.free_gb != null)) {
    const pct = Number(hot.used_pct);
    list.push(
      rowBase({
        section: "Usage",
        kind: "usage",
        key: "nvme",
        label: hot.label || "NVMe hot desk",
        metric: hot.free_gb != null ? `${hot.free_gb} GB free` : `${pct}% used`,
        progress: Number.isFinite(pct) ? pct : null,
        ok: hot.headroom_ok !== false,
        warn: hot.headroom_ok === false || pct >= 85,
      }),
    );
  }

  if (cache) {
    const mounted = cache.mounted !== false;
    list.push(
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
        ok: mounted,
        warn: !mounted,
      }),
    );
  }

  return list;
}

export function countBlockers(...rowSets) {
  return rowSets.flat().filter((r) => r.warn || !r.ok).length;
}

export function filterResourcesView(
  view,
  { providers, layers, stack, storage, running },
) {
  if (view === "sources") return { providers, layers: [], stack: [], storage: [], running: [] };
  if (view === "layers") return { providers: [], layers, stack: [], storage: [], running: [] };
  if (view === "stack") return { providers: [], layers: [], stack, storage: [], running: [] };
  if (view === "usage") return { providers: [], layers: [], stack: [], storage, running: [] };
  if (view === "running") return { providers: [], layers: [], stack: [], storage: [], running };
  if (view === "issues") {
    const bad = (rows) => rows.filter((r) => r.warn || !r.ok);
    return {
      providers: bad(providers),
      layers: bad(layers),
      stack: bad(stack),
      storage: bad(storage),
      running: bad(running),
    };
  }
  return { providers, layers, stack, storage, running };
}
