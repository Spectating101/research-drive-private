/** Resources — Spending | Activity model from desk rollup. */

import { buildMotionRowsFromRollup } from "@/v2/resourcesFromRollup";

function rowBase(row) {
  return { ok: true, warn: false, ...row };
}

function fmtGiB(gib) {
  if (gib == null) return "—";
  if (gib === 0) return "0 GiB";
  if (gib < 0.01) return "<0.01 GiB";
  return `${gib} GiB`;
}

function fmtCost(cost) {
  if (!cost || typeof cost !== "object") return "—";
  const parts = [];
  if (cost.bq_gib) parts.push(`BQ ${fmtGiB(cost.bq_gib)}`);
  if (cost.tavily) parts.push(`Tavily ${cost.tavily}`);
  if (cost.composer) parts.push(`Composer ${cost.composer}`);
  return parts.length ? parts.join(" · ") : "—";
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function cleanTarget(target) {
  const text = String(target || "");
  return text.startsWith("[context:") && text.includes("]") ? text.split("]").slice(1).join("]").trim() : text;
}

function cleanActivitySubject(target, action) {
  let text = cleanTarget(target).replace(/\s+/g, " ").trim();
  if (!text) return ACTION_LABELS[action] || action || "Activity";

  const currentRun = text.match(/^Explain the current procurement run:\s*([^.]+?)(?:\s*\(|\.|$)/i);
  if (currentRun?.[1]) return currentRun[1].trim();

  const datasetSearch = text.match(/^Find datasets for:\s*(.+)$/i);
  if (datasetSearch?.[1]) return datasetSearch[1].trim();

  const meter = text.match(/^Explain this Resources spending meter:\s*([^(.]+)(?:\s*\(|\.|$)/i);
  if (meter?.[1]) return `${meter[1].trim()} spending meter`;

  return text;
}

const ACTION_LABELS = {
  ask: "Ask",
  discover: "Browse discover",
  bq_dry_run: "BQ dry-run",
  bq_read: "BQ read",
  procure: "Procure",
  query: "Query dataset",
  preview: "Preview",
  job_submit: "Job submitted",
  job_approve: "Job approved",
  approve_collect: "Collect approved",
};

export function buildCapacityCards(rollup) {
  if (!rollup?.hero) return [];
  const h = rollup.hero;
  const composer = h.composer || {};
  const workers = h.workers || {};
  const vault = h.vault || {};
  const qe = h.query_engine || {};
  return [
    rowBase({
      kind: "capacity",
      key: "cap-ask",
      label: "Ask",
      metric: composer.model || "composer-2.5",
      sublabel: composer.configured ? "Composer + MCP" : "Composer not configured",
      ok: composer.configured,
      warn: !composer.configured,
      section: "capacity",
      detail: { mcp: rollup.ai?.mcp_tools?.total },
    }),
    rowBase({
      kind: "capacity",
      key: "cap-workers",
      label: "Workers",
      metric: `${workers.busy ?? "—"}/${workers.total ?? "—"} busy`,
      sublabel: "windows_lab",
      section: "capacity",
    }),
    rowBase({
      kind: "capacity",
      key: "cap-vault",
      label: "Vault",
      metric: vault.used_tb != null ? `${vault.used_tb}/${vault.cap_tb ?? "?"} TB` : "—",
      sublabel: vault.pct != null ? `${vault.pct}% used` : "quota pending",
      progress: vault.pct,
      section: "capacity",
    }),
    rowBase({
      kind: "capacity",
      key: "cap-engine",
      label: "Query engine",
      metric: `:${qe.port ?? 8765} ${qe.up ? "up" : "down"}`,
      sublabel: "research library API",
      ok: qe.up,
      showStatus: !qe.up,
      section: "capacity",
    }),
  ];
}

export function buildSpendingMeters(rollup) {
  if (!rollup) return [];
  const m = rollup.metered || {};
  const bq = m.bigquery || {};
  const tv = m.tavily || {};
  const period = rollup.spending?.period?.totals || {};
  const today = rollup.spending?.today || {};
  const drivers = rollup.spending?.drivers || [];

  const rows = [
    rowBase({
      kind: "meter",
      meterId: "bigquery",
      key: "meter-bigquery",
      label: "BigQuery",
      metric: `${fmtGiB(period.bq_gib_billed)} period · ${fmtGiB(today.bq_gib_billed)} today`,
      periodValue: fmtGiB(period.bq_gib_billed),
      todayValue: fmtGiB(today.bq_gib_billed),
      unitLabel: "billed this month",
      sublabel: bq.project || (bq.configured ? "configured" : "not configured"),
      ok: bq.configured,
      warn: !bq.configured,
      section: "spending",
      drivers,
      detail: bq,
    }),
    rowBase({
      kind: "meter",
      meterId: "tavily",
      key: "meter-tavily",
      label: "Tavily",
      metric: `${period.tavily_calls ?? 0} period · ${today.tavily_calls ?? 0} today`,
      periodValue: String(period.tavily_calls ?? 0),
      todayValue: String(today.tavily_calls ?? 0),
      unitLabel: "web calls this month",
      sublabel: tv.keys_loaded ? `${tv.keys_loaded} keys` : "no keys",
      ok: (tv.keys_loaded || 0) > 0,
      section: "spending",
      detail: tv,
    }),
    rowBase({
      kind: "meter",
      meterId: "composer",
      key: "meter-composer",
      label: "Composer",
      metric: `${period.composer_turns ?? 0} turns · ${today.composer_turns ?? 0} today`,
      periodValue: String(period.composer_turns ?? 0),
      todayValue: String(today.composer_turns ?? 0),
      unitLabel: "Ask turns this month",
      sublabel: rollup.ai?.composer_model || "composer-2.5",
      section: "spending",
      detail: rollup.ai,
    }),
    rowBase({
      kind: "meter",
      meterId: "probes",
      key: "meter-probes",
      label: "Source probes",
      metric: `${period.probe_calls ?? 0} period · ${today.probe_calls ?? 0} today`,
      periodValue: String(period.probe_calls ?? 0),
      todayValue: String(today.probe_calls ?? 0),
      unitLabel: "URL probes this month",
      sublabel: "classify before collect",
      section: "spending",
    }),
  ];
  return rows;
}

export function buildAccountSummaryRows(rollup) {
  if (!rollup) return [];
  const period = rollup.spending?.period?.totals || {};
  const today = rollup.spending?.today || {};
  const jobs = rollup.motion?.jobs || {};
  const workers = rollup.hero?.workers || {};
  const vault = rollup.hero?.vault || {};
  const usage = rollup.usage || {};

  return [
    rowBase({
      kind: "statement",
      key: "statement-ask",
      label: "Ask / model turns",
      metric: `${period.composer_turns ?? 0} month`,
      sublabel: `${today.composer_turns ?? 0} today`,
      detail: rollup.ai?.composer_model || "composer-2.5",
      section: "account",
    }),
    rowBase({
      kind: "statement",
      key: "statement-workers",
      label: "Workers",
      metric: `${workers.busy ?? "—"}/${workers.total ?? "—"} busy`,
      sublabel: `${jobs.pending_approval || 0} approvals`,
      detail: `${jobs.running || 0} running`,
      warn: (jobs.pending_approval || 0) > 0,
      section: "account",
    }),
    rowBase({
      kind: "statement",
      key: "statement-vault",
      label: "Vault",
      metric: vault.used_tb != null ? `${vault.used_tb}/${vault.cap_tb ?? "?"} TB` : "quota pending",
      sublabel: `cache ${usage.cache?.pct ?? "—"}%`,
      detail: `hot ${usage.hot?.used_pct ?? "—"}%`,
      section: "account",
    }),
  ];
}

export function buildActionRows(rollup) {
  return needsAttention(rollup).map((issue) =>
    rowBase({
      kind: "statement",
      key: `action-${issue.key}`,
      label: issue.label,
      metric: issue.section === "motion" ? "Approval needed" : "Check",
      sublabel: issue.section || "resources",
      detail: issue.section === "motion" ? "Review" : "Inspect",
      warn: true,
      section: "actions",
      issue,
    }),
  );
}

export function buildActiveRows(rollup, jobs = []) {
  const motion = buildMotionRowsFromRollup(rollup, jobs);
  const visibleKeys = new Set(["jobs-pending", "jobs-running", "gdelt"]);
  return motion
    .filter((r) => r.job || visibleKeys.has(r.key))
    .slice(0, 4)
    .map((r) => ({
      ...r,
      kind: "active",
      section: "active",
    }));
}

export function buildActivityRows(rollup, filter = null) {
  const events = rollup?.activity?.events || [];
  return events
    .filter((ev) => {
      if (!filter) return true;
      if (filter.hasCost) {
        return !!(ev.cost && Object.keys(ev.cost).length);
      }
      if (filter.actionGroup === "jobs") {
        return ["job_submit", "job_approve", "approve_collect"].includes(ev.action);
      }
      if (filter.actions) {
        return filter.actions.includes(ev.action);
      }
      if (filter.meterId === "bigquery") {
        return ev.cost?.bq_gib > 0;
      }
      if (filter.meterId === "tavily") {
        return ev.cost?.tavily > 0 || ev.action === "discover";
      }
      if (filter.meterId === "composer") {
        return ev.action === "ask" || ev.cost?.composer;
      }
      if (filter.action) {
        return ev.action === filter.action;
      }
      return true;
    })
    .map((ev) =>
      rowBase({
        kind: "activity",
        key: `act-${ev.id}`,
        label: cleanActivitySubject(ev.target, ev.action),
        metric: ACTION_LABELS[ev.action] || ev.action,
        actionLabel: ACTION_LABELS[ev.action] || ev.action,
        target: cleanTarget(ev.target),
        sublabel: fmtTime(ev.ts),
        costLabel: fmtCost(ev.cost),
        section: "activity",
        event: ev,
        ok: true,
      }),
    );
}

export function spendingDailySeries(rollup) {
  return rollup?.spending?.period?.daily || [];
}

export function spendingPeriodLabel(rollup) {
  const p = rollup?.spending?.period;
  if (!p?.start || !p?.end) return "Last 30 days";
  return `${p.start} – ${p.end}`;
}

export function needsAttention(rollup) {
  const issues = rollup?.issues || [];
  const pending = rollup?.motion?.jobs?.pending_approval || 0;
  const out = [...issues];
  if (pending > 0 && !out.some((i) => i.key === "jobs-pending")) {
    out.push({ key: "jobs-pending", label: `${pending} job(s) awaiting approval`, section: "motion" });
  }
  return out;
}
