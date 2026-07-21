import { useMemo, useState } from "react";
import {
  buildAccountSummaryRows,
  buildActionRows,
  buildActivityRows,
  spendingPeriodLabel,
} from "@/v2/resourcesSpending";
import { buildCapacityAccessPairs, groupSourceCapabilities } from "@/v2/resourcesCapacity";
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

function CapacityAccessGrid({ rollup, selectedKey, onSelect }) {
  const pairs = buildCapacityAccessPairs(rollup);
  return (
    <div className="rd-v2-res-capacity-pairs" data-testid="resources-capacity-grid" aria-label="Capacity and access">
      {pairs.map((pair) => (
        <section key={pair.id} className="rd-v2-res-capacity-pair" aria-label={pair.title}>
          <header className="rd-v2-res-capacity-pair-head">
            <span>{pair.title}</span>
          </header>
          <div className="rd-v2-res-capacity-pair-grid">
            {pair.meters.map((meter) => {
              const key = `capacity-${meter.id}`;
              const pct = meter.pct;
              return (
                <button
                  key={meter.id}
                  type="button"
                  className={`rd-v2-res-capacity-meter${selectedKey === key ? " on" : ""}${meter.warn ? " warn" : ""}`}
                  onClick={() =>
                    onSelect?.({
                      key,
                      label: meter.name,
                      metric: meter.metric,
                      kind: "usage",
                      section: pair.id,
                      progress: pct,
                      warn: meter.warn,
                    })
                  }
                >
                  <span className="rd-v2-res-capacity-meter-name">{meter.name}</span>
                  <strong>{meter.metric}</strong>
                  {pct != null ? (
                    <span className="rd-v2-res-capacity-meter-bar" aria-hidden>
                      <i style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                    </span>
                  ) : (
                    <span className="rd-v2-res-capacity-meter-bar empty" aria-hidden />
                  )}
                  <em>
                    {meter.available || (pct != null ? `${pct}%` : "—")}
                    {meter.action ? ` · ${meter.action}` : ""}
                  </em>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function SourceCapabilityLedger({ panels, selectedKey, onSelect }) {
  const families = groupSourceCapabilities([
    { rows: panels?.providers || [] },
    { rows: panels?.layers || [] },
  ]);
  if (!families.length) {
    return <p className="rd-v2-res-idle">Source capability rows appear when the desk reports routes.</p>;
  }
  return (
    <div className="rd-v2-res-source-ledger" data-testid="resources-source-ledger">
      <header className="rd-v2-res-source-ledger-head">
        <span>Source</span>
        <span>Access</span>
        <span>Authority</span>
      </header>
      {families.map((family) => (
        <section key={family.id} className="rd-v2-res-source-family" aria-label={family.title}>
          <h3>{family.title}</h3>
          {family.rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`rd-v2-res-source-row${selectedKey === row.id || selectedKey === row.row?.key ? " on" : ""}`}
              onClick={() => onSelect?.(row.row || row)}
            >
              <strong>{row.name}</strong>
              <span>{row.access}</span>
              <em data-authority={row.authority}>{row.authority}</em>
            </button>
          ))}
        </section>
      ))}
    </div>
  );
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
                  className={`rd-v2-res-activity-row${selectedKey === r.key ? " on" : ""}`}
                  onClick={() => onSelectRow?.(r)}
                >
                  <span className="rd-v2-res-activity-time">{r.sublabel}</span>
                  <span className="rd-v2-res-activity-main">
                    <strong>{shortText(r.label, 96)}</strong>
                    <em>
                      {r.actionLabel || r.metric}
                      {item.count > 1 ? ` · ${item.count} runs` : ""}
                    </em>
                  </span>
                  <span className={`rd-v2-res-activity-meter${costLabel === "—" ? " empty" : ""}`}>
                    {costLabel}
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
  const sources = buildPinnedSourceRows(panels.providers || [], panels.layers || []);
  return [
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
      sources,
      "Route",
      "Routes the desk can use to find, probe, and collect missing data.",
    ),
  ].filter((section) => section.rows.length);
}

function ResearchCapability({ cluster, panels, rollup, catalogSummary }) {
  const platform = cluster?.platform_state || cluster || {};
  const registry = platform.registry_datasets ?? catalogSummary?.registry_datasets;
  const instant = platform.instant_datasets ?? catalogSummary?.instant_datasets;
  const partitions = platform.professor_partitions ?? catalogSummary?.partitions;
  const routeCount = buildPinnedSourceRows(panels.providers || [], panels.layers || []).length;
  const workers = rollup?.hero?.workers || {};
  const collectorCount = workers.online ?? workers.joined ?? workers.busy ?? workers.total;
  const collectorLabel = workers.total != null && collectorCount != null
    ? `${collectorCount}/${workers.total} collectors available`
    : collectorCount != null
      ? `${collectorCount} collectors available`
      : "Collector state pending";
  const bigQuery = (panels.metered || []).find((row) => row.key === "bigquery");

  return (
    <section className="rd-v2-res-capability" aria-label="Research capability">
      <header>
        <div>
          <p>What this enables</p>
          <span>Verified capability available to the lab today.</span>
        </div>
      </header>
      <div className="rd-v2-res-capability-lines">
        <div>
          <span>Reusable research estate</span>
          <strong>
            {registry != null ? `${registry} registered assets` : "Registered estate available"}
            {instant != null ? ` · ${instant} query ready` : ""}
          </strong>
          <em>{partitions != null ? `${partitions} organized collections available in Library.` : "Registered assets remain available in Library."}</em>
        </div>
        <div>
          <span>Evidence acquisition reach</span>
          <strong>{routeCount || "Configured"} source routes</strong>
          <em>{collectorLabel}. Discover can probe and collect within the available access rules.</em>
        </div>
        <div>
          <span>Guarded remote analysis</span>
          <strong>{bigQuery ? resourceQuota(bigQuery) : "Query limit available"}</strong>
          <em>Remote table work is estimated before execution, rather than silently spending quota.</em>
        </div>
      </div>
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
  const primarySections = sections.filter((section) => section.id !== "sources");
  const sourceSection = sections.find((section) => section.id === "sources");
  const total = primarySections.reduce((sum, section) => sum + section.rows.length, 0);
  const sourceRoutes = sourceSection?.rows.length || 0;
  return (
    <section className="rd-v2-res-inventory" aria-label="Capacity and access">
      <div className="rd-v2-res-inventory-head">
        <h2>Capacity &amp; access</h2>
        <span>{total} resources</span>
      </div>
      {primarySections.map((section) => (
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
      {sourceSection ? (
        <details className="rd-v2-res-routes">
          <summary>
            <span>
              <strong>Available source routes</strong>
              <em>{sourceRoutes} configured routes used by Discover when evidence is missing.</em>
            </span>
            <b>Show routes</b>
          </summary>
          <div className="rd-v2-res-routes-body">
            <p>Routes remain available for inspection here; sourcing choices and collection progress stay in Discover.</p>
            {sourceSection.rows.map((item) => (
              <ResourceInventoryRow
                key={item.id}
                item={item}
                selected={selectedKey === item.row.key}
                onSelect={onSelect}
              />
            ))}
          </div>
        </details>
      ) : null}
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
  const isInitialLoading = rollupLoading && rollup === undefined;
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
  const activity = useMemo(
    () => (showActivityFeed ? buildActivityRows(viewRollup, effectiveActivityFilter) : []),
    [viewRollup, effectiveActivityFilter, showActivityFeed],
  );
  const periodLabel = useMemo(() => spendingPeriodLabel(viewRollup), [viewRollup]);
  const actionRows = useMemo(() => buildActionRows(viewRollup), [viewRollup]);
  const reviewRows = useMemo(
    () => actionRows.filter((row) => row.issue?.section === "motion" || String(row.issue?.key || "").includes("jobs")),
    [actionRows],
  );

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
      lead="Sources · usage · evidence-movement method."
      toolbar={
        <>
          <Chip
            active={mode === "sources" || mode === "spending"}
            onClick={() => onModeChange?.("sources")}
          >
            Sources
          </Chip>
          <Chip
            active={mode === "usage" || mode === "activity"}
            onClick={() => onModeChange?.("usage")}
          >
            Usage
          </Chip>
          <Chip active={mode === "method"} onClick={() => onModeChange?.("method")}>
            Method
          </Chip>
          <WorkersToolbarStat workers={viewRollup?.hero?.workers} />
          {(mode === "sources" || mode === "spending") && periodLabel ? (
            <span className="rd-v2-toolbar-meta">{periodLabel}</span>
          ) : filterLabel ? (
            <Chip active onClick={() => onClearActivityFilter?.()}>
              {filterLabel} ×
            </Chip>
          ) : null}
          {freshness ? <span className="rd-v2-toolbar-meta">Updated {freshness}</span> : null}
          {rollupLoading ? <span className="rd-v2-toolbar-meta">Syncing…</span> : null}
          <Chip onClick={() => onRefresh?.()}>Refresh</Chip>
        </>
      }
    >
      {rollup === null && !rollupLoading ? (
        <p className="rd-v2-res-offline" role="status">
          Desk API unreachable — start <code>python -m scripts.research_query_engine.server</code> on :8765.
        </p>
      ) : null}

      {mode === "sources" || mode === "spending" ? (
        isInitialLoading ? (
          <p className="rd-v2-res-loading" role="status">
            Loading resources…
          </p>
        ) : (
          <>
            <section className="rd-v2-res-wire-band" aria-label="Sources overview">
              <h2 className="rd-v2-res-wire-title">Capacity &amp; access</h2>
              <CapacityAccessGrid
                rollup={viewRollup}
                selectedKey={selectedKey}
                onSelect={onSelectRow}
              />
            </section>
            <section className="rd-v2-res-wire-band" aria-label="Source capabilities">
              <h2 className="rd-v2-res-wire-title">Source capabilities</h2>
              <SourceCapabilityLedger
                panels={panels}
                selectedKey={selectedKey}
                onSelect={onSelectRow}
              />
              <ResearchCapability
                cluster={health?.cluster || cluster}
                panels={panels}
                rollup={viewRollup}
                catalogSummary={catalogSummary}
              />
            </section>
          </>
        )
      ) : mode === "method" ? (
        <section className="rd-v2-res-method-wire" data-testid="resources-method" aria-label="Evidence movement method">
          <h2 className="rd-v2-res-wire-title">Evidence movement</h2>
          <ol className="rd-v2-res-method-map">
            <li>
              <strong>Find</strong>
              <span>Discover ranks candidate evidence against the research need.</span>
            </li>
            <li>
              <strong>Acquire</strong>
              <span>Approved requests become durable collection jobs.</span>
            </li>
            <li>
              <strong>Execute</strong>
              <span>Workers run the chosen route under dry-run protection.</span>
            </li>
            <li>
              <strong>Promote</strong>
              <span>Archive + registry read-back yields a Library asset.</span>
            </li>
          </ol>
          <div className="rd-v2-res-method-progress">
            <h3>Current method progress</h3>
            <ol className="rd-v2-res-method-stages">
              <li className={reviewRows.length ? "pending" : "idle"}>Find</li>
              <li className={reviewRows.length ? "active" : "idle"}>Acquire</li>
              <li className="idle">Execute</li>
              <li className="idle">Promote</li>
            </ol>
            <p>
              {reviewRows.length
                ? `${reviewRows.length} item${reviewRows.length === 1 ? "" : "s"} need researcher review on Discover History before collection continues.`
                : "No method decisions waiting. Active routes appear here when collection is in flight."}
            </p>
          </div>
        </section>
      ) : (
        <>
          <section className="rd-v2-res-wire-band" aria-label="Usage">
            <h2 className="rd-v2-res-wire-title">Recorded expenditure</h2>
            <p className="rd-v2-res-usage-hierarchy muted small">
              Period totals → daily history → attribution. Approvals stay on Discover History / Needs you — not here.
            </p>
            <ActivityFilterBar
              value={activityFilter ? null : activityKind}
              onChange={(next) => {
                onClearActivityFilter?.();
                setActivityKind(next);
              }}
            />
            <ActivityUsageSummary rollup={viewRollup} />
          </section>
          {showActivityFeed ? (
            <ActivityLog rows={activity} selectedKey={selectedKey} onSelectRow={onSelectRow} />
          ) : (
            <p className="rd-v2-res-idle">No usage rows in this period.</p>
          )}
        </>
      )}
    </PageShell>
  );
}
