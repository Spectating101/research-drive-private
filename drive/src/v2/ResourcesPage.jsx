import { useMemo, useState } from "react";
import {
  buildAccountSummaryRows,
  buildActionRows,
  buildActivityRows,
  spendingPeriodLabel,
} from "@/v2/resourcesSpending";
import { mergeJobsIntoActivity } from "@/v2/jobActivityRows";
import { jobStatusLabel } from "@/v2/askArtifacts";
import { buildResourcesPanels } from "@/v2/resourcesFromRollup";
import { Chip, PageShell, StatementRow, StatementSection } from "@/v2/ui";

const PLACEHOLDER_ROLLUP = {
  hero: {
    composer: { model: "composer-2.5", configured: true, legacy_configured: false },
    workers: {},
    vault: {},
    query_engine: { port: 8765, up: true },
  },
  ai: { composer_model: "composer-2.5", mcp_tools: {} },
  metered: {
    bigquery: { configured: true },
    tavily: { keys_loaded: 0 },
  },
  spending: {
    period: { totals: {}, daily: [] },
    today: {},
    drivers: [],
  },
  activity: { events: [] },
  motion: { jobs: {} },
  issues: [],
};

function shortText(value, max = 92) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function fmtGiBValue(value) {
  const num = Number(value || 0);
  if (num === 0) return "0 GiB";
  if (num < 0.01) return "<0.01 GiB";
  return `${num} GiB`;
}

function fmtCount(value, unit) {
  const num = Number(value || 0);
  return `${num} ${unit}${num === 1 ? "" : "s"}`;
}

function aggregateCostLabel(costs) {
  const parts = [];
  if (costs.bq_gib) parts.push(`Remote tables ${fmtGiBValue(costs.bq_gib)}`);
  if (costs.tavily) parts.push(`Web ${costs.tavily}`);
  if (costs.composer) parts.push(`Ask ${costs.composer}`);
  return parts.length ? parts.join(" · ") : "—";
}

function addCosts(acc, cost = {}) {
  const safeCost = cost && typeof cost === "object" ? cost : {};
  return {
    bq_gib: Number(acc.bq_gib || 0) + Number(safeCost.bq_gib || 0),
    tavily: Number(acc.tavily || 0) + Number(safeCost.tavily || 0),
    composer: Number(acc.composer || 0) + Number(safeCost.composer || 0),
  };
}

function activityDateKey(ts) {
  if (!ts) return "unknown";
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "unknown";
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  } catch {
    return "unknown";
  }
}

function activityDayLabel(ts) {
  if (!ts) return "Undated";
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "Undated";
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const key = d.toDateString();
    if (key === today.toDateString()) return "Today";
    if (key === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "Undated";
  }
}

function groupActivityRows(rows) {
  const sections = [];
  const sectionMap = new Map();

  for (const row of rows) {
    const ts = row.event?.ts;
    const dateKey = activityDateKey(ts);
    let section = sectionMap.get(dateKey);
    if (!section) {
      section = { key: dateKey, label: activityDayLabel(ts), items: [], itemMap: new Map() };
      sectionMap.set(dateKey, section);
      sections.push(section);
    }

    const groupKey = `${dateKey}|${row.actionLabel || row.metric}|${row.label}|${row.target || ""}`;
    let item = section.itemMap.get(groupKey);
    if (!item) {
      item = {
        key: groupKey,
        row,
        count: 0,
        costs: {},
      };
      section.itemMap.set(groupKey, item);
      section.items.push(item);
    }
    item.count += 1;
    item.costs = addCosts(item.costs, row.event?.cost);
  }

  return sections.map((section) => ({
    ...section,
    count: section.items.reduce((sum, item) => sum + item.count, 0),
  }));
}

function facultyOpsLabel(label, key) {
  const map = {
    "Ask / model turns": "Ask usage",
    Workers: "Collection workers",
    Vault: "Lab vault",
    "Query engine": "Desk connection",
  };
  return map[label] || label;
}

function facultyOpsSub(label, key, sub) {
  if (key === "statement-ask") return "Procurement chat this month";
  if (label === "Query engine") return "Catalog and query service";
  return sub;
}

function StatusStripCell({ label, value, sub, tone = "" }) {
  return (
    <div className={`rd-v2-res-status-cell${tone ? ` ${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{sub}</em>
    </div>
  );
}

function ResourcesStatusStrip({ rollup }) {
  const rows = buildAccountSummaryRows(rollup);
  const qe = rollup?.hero?.query_engine || {};
  if (!rows.length && qe.port == null) return null;

  return (
    <section className="rd-v2-res-status-strip" aria-label="Operations status">
      {rows.map((row) => (
        <StatusStripCell
          key={row.key}
          label={facultyOpsLabel(row.label, row.key)}
          value={row.metric}
          sub={facultyOpsSub(row.label, row.key, row.detail || row.sublabel)}
          tone={row.warn ? "warn" : ""}
        />
      ))}
      <StatusStripCell
        label="Desk connection"
        value={qe.up ? "Connected" : "Offline"}
        sub="Catalog and query service"
        tone={qe.up === false ? "off" : ""}
      />
    </section>
  );
}

function ActivityUsageSummary({ rollup }) {
  const period = rollup?.spending?.period?.totals || {};
  const today = rollup?.spending?.today || {};
  const cells = [
    ["Remote tables", fmtGiBValue(period.bq_gib_billed), `${fmtGiBValue(today.bq_gib_billed)} today`],
    ["Web search", fmtCount(period.tavily_calls, "call"), `${today.tavily_calls ?? 0} today`],
    ["Ask usage", fmtCount(period.composer_turns, "turn"), `${today.composer_turns ?? 0} today`],
    ["Source probes", fmtCount(period.probe_calls, "probe"), `${today.probe_calls ?? 0} today`],
  ];
  return (
    <section className="rd-v2-res-status-strip rd-v2-res-status-strip-activity" aria-label="Usage report">
      {cells.map(([label, value, sub]) => (
        <StatusStripCell key={label} label={label} value={value} sub={sub} />
      ))}
    </section>
  );
}

function ActivityLog({ rows, selectedKey, onSelectRow }) {
  if (!rows.length) {
    return <p className="rd-v2-res-idle">No log entries for this view.</p>;
  }
  const sections = groupActivityRows(rows);
  return (
    <div className="rd-v2-res-log">
      <div className="rd-v2-res-log-title">
        <h2>Run log</h2>
        <span>{rows.length} event{rows.length === 1 ? "" : "s"}</span>
      </div>
      {sections.map((section) => (
        <section key={section.key} className="rd-v2-res-log-section">
          <div className="rd-v2-res-log-day">
            <span>{section.label}</span>
            <small>{section.count} event{section.count === 1 ? "" : "s"}</small>
          </div>
          <div className="rd-v2-res-activity-table">
            {section.items.map((item) => {
              const r = item.row;
              const costLabel = aggregateCostLabel(item.costs);
              return (
                <button
                  key={item.key}
                  type="button"
                  className={`rd-v2-res-activity-row${selectedKey === r.key ? " on" : ""}${r.job ? " job" : ""}`}
                  onClick={() => onSelectRow?.(r)}
                >
                  <span className="rd-v2-res-activity-time">{r.sublabel}</span>
                  <span className="rd-v2-res-activity-main">
                    <strong>{shortText(r.label, 96)}</strong>
                    <em>
                      {r.actionLabel || r.metric}
                      {item.count > 1 ? ` · ${item.count} runs` : ""}
                    </em>
                    {r.jobProgress != null ? (
                      <span className="rd-v2-res-job-progress" aria-label={`Progress ${r.jobProgress}%`}>
                        <span className="rd-v2-res-job-progress-bar" style={{ width: `${r.jobProgress}%` }} />
                      </span>
                    ) : null}
                  </span>
                  <span
                    className={`rd-v2-res-activity-meter${costLabel === "—" && !r.job ? " empty" : ""}${r.job ? " job" : ""}`}
                  >
                    {r.job ? (
                      <span className={`rd-v2-pill sm${r.warn ? " warn" : ""}`}>{jobStatusLabel(r.job.status)}</span>
                    ) : (
                      costLabel
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function ActivityFilterBar({ value, onChange }) {
  const filters = [
    ["all", "All"],
    ["review", "Review"],
    ["jobs", "Jobs"],
    ["ask", "Ask"],
    ["discovery", "Discovery"],
    ["query", "Query"],
    ["metered", "Metered"],
  ];
  return (
    <div className="rd-v2-res-filterbar">
      {filters.map(([id, label]) => (
        <Chip key={id} active={value === id} onClick={() => onChange(id)}>
          {label}
        </Chip>
      ))}
    </div>
  );
}

function WorkersToolbarStat({ workers }) {
  const online = workers?.online ?? workers?.joined;
  const busy = workers?.busy;
  const total = workers?.total;
  if (online == null && busy == null && total == null) return null;

  const count = online ?? busy ?? total;
  const qualifier = online != null ? "online" : busy != null ? "busy" : "configured";
  const value = total != null && count !== total ? `${count}/${total} ${qualifier}` : `${count} ${qualifier}`;

  return (
    <span className="rd-v2-toolbar-stat" aria-label={`Collection workers ${value}`}>
      <span>Collectors</span>
      <strong>{value}</strong>
    </span>
  );
}

function resourceStatus(row) {
  if (row.warn) return "Check";
  if (row.ok === false) return "Offline";
  return null;
}

function resourceTone(row) {
  if (row.warn) return " warn";
  if (row.ok === false) return " off";
  return "";
}

const PINNED_STORAGE_KEYS = new Set(["vault", "nvme"]);
const PINNED_ACCOUNT_KEYS = new Set(["bigquery", "tavily", "collect-tokens"]);

function needsAttention(row) {
  return row.warn || row.ok === false;
}

function sourceGroupRow({ rows, keys, key, label, endpoint, metric, detail }) {
  const members = keys.map((id) => rows.find((row) => row.key === id)).filter(Boolean);
  if (!members.length) return null;
  return {
    kind: "source",
    key,
    section: "Source routes",
    group: true,
    label,
    endpoint,
    metric,
    detail,
    ok: members.some((row) => row.ok !== false),
    warn: members.every((row) => needsAttention(row)),
    members: members.map((row) => row.label),
  };
}

function buildPinnedSourceRows(providers = [], layers = []) {
  return [
    sourceGroupRow({
      rows: providers,
      keys: ["source-sec_edgar", "source-twse", "source-mops", "source-yfinance", "source-coingecko"],
      key: "source-market-filings",
      label: "Market data & filings",
      endpoint: "SEC · TWSE · MOPS · Yahoo · CoinGecko",
      metric: "Official filings, market series, crypto prices",
      detail: "Structured public finance routes",
    }),
    sourceGroupRow({
      rows: providers,
      keys: ["source-datacite", "source-huggingface", "source-open_research"],
      key: "source-research-catalogs",
      label: "Catalog APIs",
      endpoint: "DataCite · Hugging Face · Zenodo/OpenAlex",
      metric: "DOI and dataset catalog search",
      detail: "Academic dataset discovery",
    }),
    sourceGroupRow({
      rows: layers,
      keys: ["layer-discover_search", "layer-web_discover", "layer-probe_url"],
      key: "route-discovery-intake",
      label: "Discovery & intake",
      endpoint: "Discover search · Web discover · Source probe",
      metric: "Find candidates, classify URLs",
      detail: "Before collection",
    }),
    sourceGroupRow({
      rows: providers,
      keys: ["source-web_generic"],
      key: "source-public-web",
      label: "Public web",
      endpoint: "Public URL",
      metric: "Probe, then collect",
      detail: "One-off URLs and pages",
    }),
    sourceGroupRow({
      rows: providers,
      keys: ["source-bigquery"],
      key: "source-remote-tables",
      label: "Remote tables",
      endpoint: "BigQuery public datasets",
      metric: "Dry-run, then query",
      detail: "Remote datasets without local download",
    }),
  ].filter(Boolean);
}

function resourceDetail(row) {
  if (row.kind === "usage") {
    if (row.key === "vault") return "Long-term archive";
    if (row.key === "nvme") return "Local working space";
    if (row.key === "bulk-cache") return "Large downloads";
    if (row.key === "staging-disk") return "Before archiving";
  }
  if (row.kind === "metered") {
    if (row.key === "bigquery") return "Remote table queries";
    if (row.key === "tavily") return "Web search";
    if (row.key === "huggingface") return "Dataset discovery";
    if (row.key === "collect-tokens") return "External account access";
  }
  if (row.kind === "source") {
    if (row.key === "source-route-summary") return "Connector details stay in Activity unless a route needs attention";
    if (row.key === "source-market-filings") return "Official market data and filings";
    if (row.key === "source-research-catalogs") return "Academic metadata and dataset APIs";
    if (row.key === "route-discovery-intake") return "Candidate discovery and URL classification";
    if (row.key === "source-public-web") return "Probe and browser collect";
    if (row.key === "source-remote-tables") return "Dry-run protected remote query";
    if (row.key === "source-sec_edgar") return "Company filings";
    if (row.key === "source-twse") return "Taiwan market data";
    if (row.key === "source-mops") return "Taiwan company filings";
    if (row.key === "source-coingecko") return "Crypto market data";
    if (row.key === "source-bigquery") return "Remote tables";
    if (row.key === "source-datacite") return "Research datasets";
    if (row.key === "source-huggingface") return "Community datasets";
    if (row.key === "source-web_generic") return "Any public URL";
  }
  return row.endpoint || row.detail || row.layers || row.collect_via || row.sublabel || row.section || "—";
}

function cleanCapText(value) {
  return value.replace("/query cap", " cap per query").replace("/procure cap", " per request");
}

function resourceQuota(row) {
  if (row.progress != null) {
    if (row.key === "bulk-cache") {
      const usage = String(row.metric || "").match(/([\d.]+)\/([\d.]+) GB/);
      if (usage) {
        const free = Math.round(Number(usage[2]) - Number(usage[1]));
        if (Number.isFinite(free) && free >= 0) return `${free} GB free · ${row.progress}% used`;
      }
    }
    return `${row.metric || "—"} · ${row.progress}% used`;
  }
  if (row.kind === "usage" && row.key === "vault" && String(row.metric || "").startsWith("?/")) {
    return `${String(row.metric).slice(2)} cap · usage pending`;
  }
  if (row.kind === "metered") {
    if (row.key === "bigquery") {
      const parts = String(row.metric || "")
        .split(" · ")
        .filter((part) => part.includes("GiB") || part.includes("today"))
        .map(cleanCapText);
      return parts.join(" · ") || "Dry-run protected";
    }
    if (row.key === "tavily") {
      const raw = String(row.metric || "");
      const keys = raw.match(/(\d+) keys/)?.[1];
      const today = raw.match(/(\d+) today/)?.[1];
      return [
        keys ? `${keys} keys ready` : null,
        today ? `${today} today` : null,
      ]
        .filter(Boolean)
        .join(" · ") || "Search access";
    }
    if (row.key === "huggingface") return row.metric === "token configured" ? "Token ready" : "Public access";
    if (row.key === "collect-tokens") {
      const profiles = String(row.metric || "").match(/(\d+)\/(\d+) profiles/);
      if (profiles) return `${profiles[1]} of ${profiles[2]} accounts ready`;
    }
  }
  if (row.kind === "source") {
    if (row.key === "source-route-summary") return row.metric || "Configured source routes";
    if (row.key === "source-market-filings") return "Official feeds and queue scripts";
    if (row.key === "source-research-catalogs") return "DOI lookup and dataset import";
    if (row.key === "route-discovery-intake") return "Search and probe before collect";
    if (row.key === "source-public-web") return "Probe, then collect";
    if (row.key === "source-remote-tables") return "Query with dry-run limit";
    if (row.key === "source-sec_edgar") return "Download queue";
    if (row.key === "source-twse") return "Download queue";
    if (row.key === "source-mops") return "Browser collector";
    if (row.key === "source-coingecko") return "API fetch";
    if (row.key === "source-bigquery") return "Remote query";
    if (row.key === "source-datacite") return "DOI lookup";
    if (row.key === "source-huggingface") return "Dataset import";
    if (row.key === "source-web_generic") return "Probe, then collect";
    return row.collect_via || row.layers || "Available";
  }
  return row.metric || row.routes || "—";
}

function resourceName(row) {
  if (row.key === "vault") return "Drive vault";
  if (row.key === "nvme") return "Working disk";
  if (row.key === "bulk-cache") return "Bulk cache";
  if (row.key === "staging-disk") return "Staging space";
  if (row.key === "tavily") return "Web discovery";
  if (row.key === "huggingface") return "Hugging Face";
  if (row.key === "collect-tokens") return "Collector accounts";
  if (row.key === "source-route-summary") return "Source routes";
  if (row.key === "source-market-filings") return "Market & filings";
  if (row.key === "source-research-catalogs") return "Catalog APIs";
  if (row.key === "route-discovery-intake") return "Discovery & intake";
  if (row.key === "source-public-web") return "Open web";
  if (row.key === "source-remote-tables") return "Remote tables";
  if (row.key === "source-twse") return "TWSE";
  if (row.key === "source-bigquery") return "BigQuery";
  if (row.key === "source-web_generic") return "Public web";
  return row.label;
}

function resourceType(row, fallback) {
  if (row.key === "vault") return "Archive";
  if (row.key === "nvme") return "Workspace";
  if (row.key === "bulk-cache") return "Cache";
  if (row.key === "staging-disk") return "Staging";
  if (row.key === "bigquery") return "Query account";
  if (row.key === "tavily") return "Search account";
  if (row.key === "huggingface") return "Dataset account";
  if (row.key === "collect-tokens") return "Credentials";
  if (row.kind === "source") return row.endpoint || fallback;
  return fallback;
}

function inventorySection(id, title, rows, type, description) {
  return {
    id,
    title,
    description,
    rows: rows.map((row) => ({
      id: `${id}-${row.key || row.label}`,
      type: resourceType(row, type),
      row,
      name: resourceName(row),
      quota: resourceQuota(row),
      source: resourceDetail(row),
      status: resourceStatus(row),
    })),
  };
}

function buildResourceInventorySections(panels) {
  const storage = (panels.usage || []).filter((row) => PINNED_STORAGE_KEYS.has(row.key) || needsAttention(row));
  const metered = (panels.metered || []).filter((row) => PINNED_ACCOUNT_KEYS.has(row.key) || needsAttention(row));
  const sources = buildPinnedSourceRows(panels.providers || [], panels.layers || []).slice(0, 3);
  const sourceSummary = sources.length
    ? [
        {
          kind: "source",
          key: "source-route-summary",
          section: "Source routes",
          label: "Source routes",
          endpoint: "Finance, catalogs, and intake",
          metric: `${sources.length} routes configured`,
          detail: "Connector details stay in Activity unless a route needs attention.",
          ok: sources.some((row) => row.ok !== false),
          warn: sources.every((row) => needsAttention(row)),
          members: sources.map((row) => resourceName(row)),
        },
      ]
    : [];
  const motion = (panels.motion || []).filter((row) => row.job || row.warn || !row.ok);
  return [
    inventorySection(
      "motion",
      "Procurement jobs",
      motion,
      "Job",
      "Active collection jobs and approvals. Select a row to inspect or open in Discover.",
    ),
    inventorySection(
      "storage",
      "Storage",
      storage,
      "Storage",
      "Where collected data is archived or staged. Check capacity before large downloads.",
    ),
    inventorySection(
      "metered",
      "Accounts & limits",
      metered,
      "Account",
      "Accounts that may incur cost. Review before heavy search or remote queries.",
    ),
    inventorySection(
      "sources",
      "Source routes",
      sourceSummary,
      "Route",
      "Overview only. Open Activity for connector-level details.",
    ),
  ].filter((section) => section.rows.length);
}

function DatabankStatusStrip({ cluster, health, catalogSummary, datasets = [], partitions = [] }) {
  const inv = cluster?.platform_state;
  const summary = catalogSummary?.summary || catalogSummary || {};
  const instantFromDatasets = datasets.filter((d) => /instant|query/i.test(String(d.analysis_readiness || ""))).length;
  const partitionCount = partitions.length;
  const registryValue = cluster?.registry_datasets ?? inv?.registry_datasets ?? summary.registry_datasets ?? health?.datasets;
  if (registryValue == null && !inv) return null;
  const registry = registryValue ?? "—";
  const instant = cluster?.instant_datasets ?? inv?.instant_datasets ?? summary.instant_datasets ?? (instantFromDatasets || "syncing");
  const partitionTotal = cluster?.professor_partitions ?? inv?.professor_partitions ?? summary.professor_partitions ?? (partitionCount || "syncing");
  const refinitiv = inv?.refinitiv_datasets ?? 0;
  const unassigned = inv?.unassigned_registry_ids ?? 0;
  const incomplete = cluster?.incomplete_items?.length ?? 0;
  return (
    <section className="rd-v2-res-databank" aria-label="Databank inventory">
      <div className="rd-v2-res-databank-head">
        <h2>Databank</h2>
        <span>
          {registry} registry · {instant} instant · {partitionTotal} partitions
          {refinitiv ? ` · ${refinitiv} Refinitiv` : ""}
          {unassigned === 0 ? " · fully mapped" : ` · ${unassigned} unmapped`}
        </span>
      </div>
      <p className="rd-v2-res-databank-note">
        {cluster?.refinitiv_frozen
          ? "Refinitiv harvest frozen (2026-07-06-complete) — query-ready institutional spine."
          : "Neutral catalog inventory from platform_progress."}
        {incomplete ? ` ${incomplete} activation item(s) tracked.` : ""}
      </p>
    </section>
  );
}

function ResourceInventoryRow({ item, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`rd-v2-res-inventory-row${selected ? " on" : ""}${resourceTone(item.row)}`}
      data-kind={item.row.kind}
      onClick={() => onSelect?.(item.row)}
    >
      <span className="rd-v2-res-inventory-name">
        <strong>{item.name}</strong>
        <em>{item.type}</em>
      </span>
      <span className="rd-v2-res-inventory-quota">{item.quota}</span>
      <span className="rd-v2-res-inventory-source">{item.source}</span>
      {item.status ? <span className="rd-v2-res-inventory-status">{item.status}</span> : null}
    </button>
  );
}

function ResourceInventory({ sections, selectedKey, onSelect }) {
  if (!sections.length) return null;
  const total = sections.reduce((sum, section) => sum + section.rows.length, 0);
  const sourceSection = sections.find((section) => section.id === "sources");
  const sourceRoutes = sourceSection?.rows[0]?.row?.members?.length || sourceSection?.rows.length || 0;
  return (
    <section className="rd-v2-res-inventory" aria-label="Key resources">
      <div className="rd-v2-res-inventory-head">
        <h2>Key resources</h2>
        <span>{total} shown · {sourceRoutes} source routes</span>
      </div>
      {sections.map((section) => (
        <div key={section.id} className="rd-v2-res-inventory-section">
          <div className="rd-v2-res-inventory-section-head">
            <div className="rd-v2-res-inventory-section-title">
              <span>{section.title}</span>
              {section.description ? <em>{section.description}</em> : null}
            </div>
            <small>{section.rows.length}</small>
          </div>
          <div className="rd-v2-res-inventory-body">
            {section.rows.map((item) => (
              <ResourceInventoryRow
                key={item.id}
                item={item}
                selected={selectedKey === item.row.key}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export function ResourcesPage({
  rollup,
  rollupLoading = false,
  health,
  ops,
  jobs = [],
  catalogSummary,
  cluster,
  datasets = [],
  partitions = [],
  mode = "spending",
  onModeChange,
  activityFilter = null,
  onClearActivityFilter,
  selectedKey,
  onRefresh,
  refreshedAt = null,
  onSelectRow,
}) {
  const [activityKind, setActivityKind] = useState("all");
  const hasEarlyContext = Boolean(health || ops || jobs.length || catalogSummary || cluster);
  const isInitialLoading = rollupLoading && rollup === undefined && !hasEarlyContext;
  const viewRollup = isInitialLoading ? null : rollup || PLACEHOLDER_ROLLUP;
  const panels = useMemo(
    () =>
      buildResourcesPanels({
        rollup,
        rollupLoading,
        health,
        ops,
        jobs,
        catalogSummary,
        cluster,
      }),
    [rollup, rollupLoading, health, ops, jobs, catalogSummary, cluster],
  );
  const effectiveActivityFilter = useMemo(() => {
    if (activityFilter) return activityFilter;
    if (activityKind === "metered") return { hasCost: true };
    if (activityKind === "jobs") return { actionGroup: "jobs" };
    if (activityKind === "ask") return { action: "ask" };
    if (activityKind === "discovery") return { actions: ["discover"] };
    if (activityKind === "query") return { actions: ["query", "bq_dry_run", "bq_read", "preview"] };
    return null;
  }, [activityFilter, activityKind]);
  const showActivityFeed = activityFilter || activityKind !== "review";
  const activity = useMemo(() => {
    const base = showActivityFeed ? buildActivityRows(viewRollup, effectiveActivityFilter) : [];
    if (!showActivityFeed) return base;
    if (effectiveActivityFilter?.meterId) return base;
    return mergeJobsIntoActivity(base, jobs);
  }, [viewRollup, effectiveActivityFilter, showActivityFeed, jobs]);
  const periodLabel = useMemo(() => spendingPeriodLabel(viewRollup), [viewRollup]);
  const actionRows = useMemo(() => buildActionRows(viewRollup), [viewRollup]);
  const reviewRows = useMemo(
    () => actionRows.filter((row) => row.issue?.section === "motion" || String(row.issue?.key || "").includes("jobs")),
    [actionRows],
  );
  const inventorySections = useMemo(() => buildResourceInventorySections(panels), [panels]);
  const showActivityAttention = reviewRows.length > 0 && !activityFilter;

  const selectIssue = (issue) =>
    onSelectRow?.({
      key: issue.key,
      label: issue.label,
      metric: "Action required",
      kind: "active",
      section: issue.section,
      warn: true,
      ok: false,
    });

  const freshness =
    refreshedAt != null ? `${Math.max(0, Math.round((Date.now() - refreshedAt) / 1000))}s ago` : null;

  const filterLabel =
    activityFilter?.meterId === "bigquery"
      ? "Remote table events"
      : activityFilter?.meterId === "tavily"
        ? "Web discovery events"
        : activityFilter?.meterId === "composer"
          ? "Ask turns"
          : null;

  return (
    <PageShell
      title="Resources"
      lead="Storage, account limits, and procurement routes"
      toolbar={
        <>
          <Chip active={mode === "spending"} onClick={() => onModeChange?.("spending")}>
            Overview
          </Chip>
          <Chip active={mode === "activity"} onClick={() => onModeChange?.("activity")}>
            Activity
          </Chip>
          <WorkersToolbarStat workers={viewRollup?.hero?.workers} />
          {mode === "spending" ? (
            <span className="rd-v2-toolbar-meta">{periodLabel}</span>
          ) : filterLabel ? (
            <Chip active onClick={() => onClearActivityFilter?.()}>
              {filterLabel} ×
            </Chip>
          ) : null}
          {freshness ? <span className="rd-v2-toolbar-meta">Updated {freshness}</span> : null}
          {rollupLoading ? <span className="rd-v2-toolbar-meta">Refreshing inventory…</span> : null}
          <Chip onClick={() => onRefresh?.()}>Refresh</Chip>
        </>
      }
    >
      {rollup === null && !rollupLoading ? (
        <p className="rd-v2-res-offline" role="status">
          Desk API unreachable — start <code>python -m scripts.research_query_engine.server</code> on :8765.
        </p>
      ) : null}

      {mode === "spending" ? (
        isInitialLoading ? (
          <p className="rd-v2-res-loading" role="status">
            Loading resources…
          </p>
        ) : (
          <>
            <ResourcesStatusStrip rollup={viewRollup} />
            <DatabankStatusStrip
              cluster={health?.cluster || cluster}
              health={health}
              catalogSummary={catalogSummary}
              datasets={datasets}
              partitions={partitions}
            />
            <ResourceInventory
              sections={inventorySections}
              selectedKey={selectedKey}
              onSelect={onSelectRow}
            />
          </>
        )
      ) : (
        <>
          <ActivityFilterBar
            value={activityFilter ? null : activityKind}
            onChange={(next) => {
              onClearActivityFilter?.();
              setActivityKind(next);
            }}
          />
          <ActivityUsageSummary rollup={viewRollup} />
          {showActivityAttention ? (
            <StatementSection title="Review queue">
              {reviewRows.map((r) => {
                const { key, issue, ...rowProps } = r;
                return (
                  <StatementRow
                    key={key}
                    {...rowProps}
                    active={selectedKey === key}
                    onClick={() => issue ? selectIssue(issue) : onSelectRow?.(r)}
                  />
                );
              })}
            </StatementSection>
          ) : null}
          {showActivityFeed ? (
            <ActivityLog rows={activity} selectedKey={selectedKey} onSelectRow={onSelectRow} />
          ) : reviewRows.length ? null : (
            <p className="rd-v2-res-idle">No review items right now.</p>
          )}
        </>
      )}
    </PageShell>
  );
}
