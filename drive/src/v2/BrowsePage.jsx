import { useEffect, useMemo, useRef, useState } from "react";
import { ListFilter } from "lucide-react";
import { discoverSearch, discoverSources, semanticDiscover, unifiedSearch, webDiscover } from "@/v2/api";
import { sourcesResponseToRows } from "@/v2/discoverAdapters";
import {
  discoverCandidateState,
  discoverStageCounts,
} from "@/v2/browseMeta";
import { browseTargetKey, webHitsToRows, discoverCandidateUrl } from "@/v2/discoverActions";
import {
  bindJobsToCandidates,
  jobToCandidateRow,
  pendingApprovalJobs,
} from "@/v2/procurementJobs";
import { loadUserEmail } from "@/v2/deskSession";
import { discoverDemoSearch } from "@/v2/deskSeed";
import { DiscoverHistoryPanel } from "@/v2/DiscoverHistoryPanel";
import { DiscoverEmptyState, DiscoverSuggestedCards } from "@/v2/DiscoverEmptyState";
import { discoverSuggestedRows } from "@/v2/discoverSuggested";
import { displayName, formatMetaValue, isEmptyishMetaValue } from "@/v2/datasetMeta";
import { Chip, PageShell, SourceRibbon } from "@/v2/ui";

const ACCESS_FILTERS = [
  { id: "all", label: "All" },
  { id: "external", label: "External" },
  { id: "in_lab", label: "In lab" },
];

const RELATIONSHIP_FILTERS = [
  { id: "", label: "Any" },
  { id: "in_lab", label: "In vault" },
  { id: "external", label: "Not in vault" },
];

const EMPTY_FACETS = {
  access: "all",
  sourceType: "",
  grain: "",
  relationship: "",
};

function rowSourceType(row) {
  return formatMetaValue(row?.source || row?.publisher || row?.backend || row?.collect_via || row?.source_route);
}

function rowGrain(row) {
  return formatMetaValue(row?.grain);
}

function collectFacetOptions(rows = []) {
  const sources = new Set();
  const grains = new Set();
  for (const row of rows) {
    const source = rowSourceType(row);
    const grain = rowGrain(row);
    if (source) sources.add(source);
    if (grain) grains.add(grain);
  }
  return {
    sourceTypes: [...sources].sort((a, b) => a.localeCompare(b)),
    grains: [...grains].sort((a, b) => a.localeCompare(b)),
  };
}

function activeFacetEntries(facets = EMPTY_FACETS) {
  const out = [];
  if (facets.access && facets.access !== "all") {
    out.push({
      key: "access",
      label: ACCESS_FILTERS.find((f) => f.id === facets.access)?.label || facets.access,
    });
  }
  if (facets.relationship) {
    out.push({
      key: "relationship",
      label: RELATIONSHIP_FILTERS.find((f) => f.id === facets.relationship)?.label || facets.relationship,
    });
  }
  if (facets.sourceType) out.push({ key: "sourceType", label: facets.sourceType });
  if (facets.grain) out.push({ key: "grain", label: facets.grain });
  return out;
}

function rowMatchesFacets(row, facets = EMPTY_FACETS, labIds, jobs) {
  const stateKey = discoverCandidateState(row, labIds, jobs).key;
  if (facets.access === "external" && stateKey === "in_lab") return false;
  if (facets.access === "in_lab" && stateKey !== "in_lab") return false;
  if (facets.relationship === "in_lab" && stateKey !== "in_lab") return false;
  if (facets.relationship === "external" && stateKey === "in_lab") return false;
  if (facets.sourceType && rowSourceType(row) !== facets.sourceType) return false;
  if (facets.grain && rowGrain(row) !== facets.grain) return false;
  return true;
}

function DiscoverQueueStrip({ rows = [], selectedId, onSelectJob }) {
  if (!rows.length) return null;
  return (
    <section className="rd-v2-discover-queue-strip" data-testid="discover-queue-strip" aria-label="Discover requests needing review">
      <div className="rd-v2-discover-queue-strip__head">
        <span>Needs your review</span>
        <small>{rows.length} request{rows.length === 1 ? "" : "s"}</small>
      </div>
      <div className="rd-v2-discover-queue-strip__rows">
        {rows.slice(0, 3).map((row) => {
          const selected = String(selectedId || "") === String(row.dataset_id || row.id || "");
          return (
            <button
              key={row.id || row.dataset_id || row.title}
              type="button"
              className={selected ? "on" : ""}
              data-testid="discover-queue-row"
              aria-pressed={selected}
              onClick={() => onSelectJob?.(row)}
            >
              <strong>{row.title || "Collection request"}</strong>
              <span>{row.status_label || "Approval required"}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function DiscoverModeTabs({ mode = "explore", pendingCount = 0, onChange }) {
  const tabs = [
    { id: "explore", label: "Explore" },
    { id: "history", label: pendingCount ? `History · ${pendingCount}` : "History" },
  ];
  return (
    <div className="rd-v2-discover-modes" role="tablist" aria-label="Discover mode">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={mode === tab.id}
          className={mode === tab.id ? "on" : ""}
          onClick={() => onChange?.(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/** Shared Discover chrome — intent is search mode only; shell geometry stays fixed. */
function DiscoverToolbar({
  draftQuery,
  setDraftQuery,
  searchInputRef,
  placeholder,
  onCommit,
  onSemanticSearch,
  onClear,
  filterControl = null,
  trailing = null,
}) {
  const [intent, setIntent] = useState("catalog");
  const researchMode = intent === "research";

  const submit = (value) => {
    const next = String(value || "").trim();
    if (!next) return;
    if (researchMode) {
      onSemanticSearch?.(next);
      return;
    }
    onCommit?.(next);
  };

  return (
    <div className="rd-v2-discover-toolbar" data-testid="discover-toolbar">
      <div className="rd-v2-discover-intent" role="group" aria-label="Discover method">
        <button
          type="button"
          className={!researchMode ? "on" : ""}
          aria-pressed={!researchMode}
          data-testid="discover-intent-catalog"
          onClick={() => setIntent("catalog")}
        >
          Catalog
        </button>
        <button
          type="button"
          className={researchMode ? "on" : ""}
          aria-pressed={researchMode}
          data-testid="discover-intent-research"
          onClick={() => setIntent("research")}
        >
          Research question
        </button>
      </div>
      <label className="rd-v2-discover-search" aria-label="Discover search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="m21 21-4.2-4.2m1.2-5.3a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        <input
          ref={searchInputRef}
          value={draftQuery}
          placeholder={
            researchMode
              ? "Describe the evidence, comparison, or data gap you need…"
              : placeholder
          }
          aria-label="Discover datasets"
          data-testid="discover-search-input"
          data-intent={researchMode ? "research" : "catalog"}
          onChange={(e) => setDraftQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit(e.currentTarget.value);
            }
          }}
        />
        {draftQuery ? (
          <button
            type="button"
            className="rd-v2-discover-search-clear"
            aria-label="Clear discover search"
            onClick={onClear}
          >
            Clear
          </button>
        ) : null}
      </label>
      <div className="rd-v2-discover-toolbar-controls">
        {filterControl}
        <div className="rd-v2-discover-toolbar-action" data-testid="discover-toolbar-action">
          <button
            type="button"
            className="rd-v2-discover-action-btn"
            data-testid="discover-search-action"
            disabled={!draftQuery.trim()}
            onClick={() => submit(draftQuery)}
          >
            {researchMode ? "Search by meaning" : "Search catalog"}
          </button>
        </div>
      </div>
      {trailing}
    </div>
  );
}

function DiscoverFilterControl({
  facets = EMPTY_FACETS,
  onChange,
  options = { sourceTypes: [], grains: [] },
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const sourceTypes = options.sourceTypes || [];
  const grains = options.grains || [];
  const active = activeFacetEntries(facets);
  const count = active.length;

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const setFacet = (key, value) => onChange?.({ ...facets, [key]: value });
  const clearFacet = (key) => {
    if (key === "access") onChange?.({ ...facets, access: "all" });
    else onChange?.({ ...facets, [key]: "" });
  };
  const clearAll = () => onChange?.({ ...EMPTY_FACETS });

  return (
    <div className="rd-v2-discover-filter" ref={wrapRef} data-testid="discover-result-filters">
      <button
        type="button"
        className={`rd-v2-discover-filter-trigger${open || count ? " on" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={count ? `Filters, ${count} active` : "Filters"}
        data-testid="discover-filter-trigger"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <ListFilter size={15} strokeWidth={2} aria-hidden="true" />
        <span>Filter</span>
        {count ? <strong data-testid="discover-filter-count">{count}</strong> : null}
      </button>
      {open ? (
        <div
          className="rd-v2-discover-filter-panel"
          role="dialog"
          aria-label="Discover filters"
          data-testid="discover-filter-panel"
        >
          {count ? (
            <div className="rd-v2-discover-filter-chips" aria-label="Active filters">
              {active.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="rd-v2-discover-filter-chip"
                  data-testid="discover-filter-chip"
                  aria-label={`Remove ${chip.label} filter`}
                  onClick={() => clearFacet(chip.key)}
                >
                  {chip.label}
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
          ) : null}
          <div className="rd-v2-discover-filter-section">
            <span>Access state</span>
            <div className="rd-v2-discover-filter-options">
              {ACCESS_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={facets.access === f.id ? "on" : ""}
                  aria-pressed={facets.access === f.id}
                  onClick={() => setFacet("access", f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="rd-v2-discover-filter-section">
            <span>Local relationship</span>
            <div className="rd-v2-discover-filter-options">
              {RELATIONSHIP_FILTERS.map((f) => (
                <button
                  key={f.id || "any"}
                  type="button"
                  className={facets.relationship === f.id ? "on" : ""}
                  aria-pressed={facets.relationship === f.id}
                  onClick={() => setFacet("relationship", f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          {sourceTypes.length ? (
            <div className="rd-v2-discover-filter-section">
              <span>Source type</span>
              <div className="rd-v2-discover-filter-options">
                <button
                  type="button"
                  className={!facets.sourceType ? "on" : ""}
                  aria-pressed={!facets.sourceType}
                  onClick={() => setFacet("sourceType", "")}
                >
                  Any
                </button>
                {sourceTypes.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={facets.sourceType === value ? "on" : ""}
                    aria-pressed={facets.sourceType === value}
                    onClick={() => setFacet("sourceType", value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {grains.length ? (
            <div className="rd-v2-discover-filter-section">
              <span>Grain</span>
              <div className="rd-v2-discover-filter-options">
                <button
                  type="button"
                  className={!facets.grain ? "on" : ""}
                  aria-pressed={!facets.grain}
                  onClick={() => setFacet("grain", "")}
                >
                  Any
                </button>
                {grains.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={facets.grain === value ? "on" : ""}
                    aria-pressed={facets.grain === value}
                    onClick={() => setFacet("grain", value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {count ? (
            <button type="button" className="rd-v2-discover-filter-clear" onClick={clearAll}>
              Clear filters
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function candidateId(row) {
  return browseTargetKey(row) || "external";
}

function candidateTitle(row) {
  return row?.title || row?.name || row?.dataset_id || row?.doi || row?.url || "External dataset";
}

function hostLabel(value) {
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function uniqueParts(parts) {
  const seen = new Set();
  const out = [];
  for (const part of parts) {
    const text = String(part || "").trim();
    const key = text.toLowerCase();
    if (!text || seen.has(key) || isEmptyishMetaValue(text)) continue;
    seen.add(key);
    out.push(text);
  }
  return out;
}

function isEmptyishText(value) {
  return isEmptyishMetaValue(value);
}

function plainText(value) {
  return String(value || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

function shortText(value, max = 180) {
  const text = plainText(value).replace(/\s+/g, " ").trim();
  if (isEmptyishText(text)) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trim()}…`;
}

function candidateRoute(row) {
  const host = hostLabel(row?.url);
  const source = formatMetaValue(row?.publisher || row?.source || row?.domain || host || row?.backend);
  const route = formatMetaValue(row?.collect_via || row?.source_route || row?.access_mode);
  return uniqueParts([source, route]).join(" · ") || "Public source";
}

/** Zenodo-ish badge line — status lives in the right pill; keep this to access/coverage only. */
function candidateBadgeLine(row, state) {
  const access =
    state.key === "in_lab"
      ? "Vaulted"
      : row?.license || row?.access || (row?.url ? "Public" : null);
  return uniqueParts([
    formatMetaValue(access),
    formatMetaValue(row?.coverage || row?.date_range || row?.temporal_coverage),
  ]).join(" · ");
}

function candidateSnippet(row) {
  return shortText(row?.description || row?.recommended_use || row?.subtitle || "", 140);
}

/** Single provenance line under the snippet — publisher once, then grain/format. */
function candidateMetaLine(row) {
  return uniqueParts([
    formatMetaValue(row?.publisher || row?.source || row?.backend),
    formatMetaValue(row?.grain),
    formatMetaValue(row?.format || row?.collect_via || row?.source_route),
  ]).join(" · ");
}

function contextField(dataset, key) {
  const value = dataset?.[key];
  return formatMetaValue(value);
}

function discoverContextQueries(dataset) {
  if (!dataset?.dataset_id) return [];
  const title = displayName(dataset);
  const source = contextField(dataset, "source") || contextField(dataset, "publisher") || "";
  const grain = contextField(dataset, "grain") || "";
  const coverage = contextField(dataset, "coverage") || contextField(dataset, "date_range") || "";
  const compactTitle = title
    .replace(/\b(panel|dataset|daily|country)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return uniqueParts([
    compactTitle,
    source && !/local|vault|query/i.test(source) ? `${source} related data` : null,
    grain ? `${grain} external panel` : null,
    coverage ? `${compactTitle} ${coverage}` : null,
  ]).slice(0, 4);
}

function contextStatus(dataset, labIds) {
  const inLab = Boolean(dataset?.dataset_id && labIds?.has?.(dataset.dataset_id));
  return inLab ? "In lab" : "External";
}

function DiscoverContextPanel({ dataset, labIds, pendingCount = 0, onSearch }) {
  if (!dataset?.dataset_id) return null;
  const title = displayName(dataset);
  const status = contextStatus(dataset, labIds);
  const grain = contextField(dataset, "grain");
  const source =
    contextField(dataset, "source") ||
    contextField(dataset, "publisher") ||
    contextField(dataset, "backend");
  const meta = uniqueParts([
    status,
    grain,
    source,
    pendingCount ? `${pendingCount} review${pendingCount === 1 ? "" : "s"}` : null,
  ]).join(" · ");
  const queries = discoverContextQueries(dataset).slice(0, 2);
  return (
    <section
      className="rd-v2-discover-context rd-v2-discover-context--compact"
      aria-label="Discover dataset context"
      data-testid="discover-research-context"
    >
      <div className="rd-v2-discover-context-line">
        <span className="rd-v2-discover-context-kicker">Working from</span>
        <strong className="rd-v2-discover-context-title">{title}</strong>
        {meta ? <span className="rd-v2-discover-context-meta">{meta}</span> : null}
      </div>
      {queries.length ? (
        <div className="rd-v2-discover-context-actions" aria-label="Suggested context searches">
          {queries.map((query) => (
            <button
              key={query}
              type="button"
              className="rd-v2-discover-query-chip"
              onClick={() => onSearch?.(query)}
            >
              {query}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function DiscoverContextSourceList({ rows = [], labIds, selectedId, onSelectRow, onSearchTitle }) {
  if (!rows.length) return null;
  return (
    <section className="rd-v2-discover-source-list rd-v2-discover-source-list--results" data-testid="discover-suggested">
      <div className="rd-v2-discover-source-list-head">
        <span>Suggested searches</span>
        <strong>{rows.length} route{rows.length === 1 ? "" : "s"}</strong>
      </div>
      <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Related source candidates">
        {rows.map((row) => {
          const id = candidateId(row);
          const title = row.title || row.name || row.dataset_id || id;
          const inLab = Boolean(row.dataset_id && labIds?.has?.(row.dataset_id)) || row.kind === "lab";
          const ribbonSource = row.source || row.collect_via || row.source_route || row.publisher || row.backend;
          const meta = uniqueParts([
            inLab ? "In lab" : "External",
            formatMetaValue(row.grain),
            formatMetaValue(row.source || row.publisher || row.backend),
          ]).join(" · ");
          const selected = selectedId === id;
          return (
            <li key={String(id)} className={selected ? "rd-v2-row-on" : undefined}>
              <button
                type="button"
                className={`row rd-v2-discover-candidate rd-v2-discover-candidate--compact${selected ? " selected" : ""}`}
                data-kind={inLab ? "lab" : "external"}
                data-testid="discover-suggested-card"
                aria-pressed={selected}
                onClick={() => {
                  if (inLab && onSelectRow) onSelectRow(row);
                  else onSearchTitle?.(title);
                }}
              >
                <span className="rd-v2-discover-candidate-source">
                  <SourceRibbon source={ribbonSource} />
                </span>
                <span className="rd-v2-discover-candidate-main">
                  <span className="rd-v2-discover-candidate-top">
                    <strong>{title}</strong>
                  </span>
                  {meta ? <span className="rd-v2-discover-route">{meta}</span> : null}
                </span>
                <em>{inLab ? "View holding" : "Find sources"}</em>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const QUERY_STOPWORDS = new Set([
  "and",
  "for",
  "from",
  "raw",
  "the",
  "with",
  "data",
  "dataset",
  "datasets",
]);

function queryTokens(query) {
  return (
    String(query || "")
      .toLowerCase()
      .match(/[a-z0-9_]+/g)
      ?.filter((token) => token.length >= 3 && !QUERY_STOPWORDS.has(token))
      .slice(0, 8) || []
  );
}

function rowText(row, fields) {
  return fields.map((field) => String(row?.[field] || "").toLowerCase()).join(" ");
}

function discoverQueryScore(row, tokens, labIds) {
  if (!tokens.length) return Number(row?.score) || 0;
  const title = rowText(row, ["title", "name", "dataset_id", "doi"]);
  const body = rowText(row, [
    "description",
    "recommended_use",
    "limitations",
    "source",
    "publisher",
    "domain",
    "coverage",
    "grain",
    "collect_via",
  ]);
  let score = Math.min(Number(row?.score) || 0, 100) / 10;
  for (const token of tokens) {
    if (title.includes(token)) score += 16;
    if (body.includes(token)) score += 5;
  }
  if (discoverCandidateState(row, labIds).key === "in_lab") score -= 14;
  if (tokens.includes("mops")) {
    const financeContext = /taiwan|twse|filing|financial|issuer|governance|disclosure|sec/.test(
      `${title} ${body}`,
    );
    if (!financeContext) score -= 24;
  }
  if (row?.local_ready || row?.collect_via === "local_open") score += 2;
  return score;
}

function titleTokenMatches(row, tokens) {
  const title = rowText(row, ["title", "name", "dataset_id", "doi"]);
  return tokens.reduce((sum, token) => sum + (title.includes(token) ? 1 : 0), 0);
}

function localCatalogSearch(catalog, query, labIds, limit = 12) {
  const tokens = queryTokens(query);
  if (!tokens.length || !Array.isArray(catalog) || !catalog.length) return [];
  const threshold = Math.min(2, tokens.length);
  const matched = catalog.filter((row) => {
    const titleHits = titleTokenMatches(row, tokens);
    if (titleHits >= threshold) return true;
    const body = rowText(row, [
      "description",
      "recommended_use",
      "source",
      "publisher",
      "domain",
      "coverage",
      "grain",
      "lane",
      "partition",
      "tags",
    ]);
    return tokens.some((token) => body.includes(token));
  });
  return rankRowsForQuery(matched, query, labIds).slice(0, limit);
}

function hasUsefulLabMatch(rows, query, labIds) {
  const tokens = queryTokens(query);
  if (!tokens.length) return rows.some((row) => discoverCandidateState(row, labIds).key === "in_lab");
  const threshold = Math.min(2, tokens.length);
  return rows.some((row) => {
    const state = discoverCandidateState(row, labIds);
    return state.key === "in_lab" && titleTokenMatches(row, tokens) >= threshold;
  });
}

function rankRowsForQuery(rows, query, labIds) {
  const tokens = queryTokens(query);
  if (!tokens.length) return rows;
  return rows
    .map((row, index) => ({ row, index, score: discoverQueryScore(row, tokens, labIds) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((item) => item.row);
}

function pickDefaultRow(rows, query, labIds) {
  const ranked = rankRowsForQuery(rows, query, labIds);
  const acquirable = ranked.find((row) => {
    const state = discoverCandidateState(row, labIds);
    return state.key !== "in_lab" && Boolean(discoverCandidateUrl(row));
  });
  if (acquirable) return acquirable;
  const external = ranked.find((row) => discoverCandidateState(row, labIds).key !== "in_lab");
  return external || ranked[0] || null;
}

function stateLabel(state) {
  if (state.key === "probe_ready") return "Ready to check";
  if (state.key === "in_lab") return "In lab";
  if (state.key === "awaiting") return "Awaiting you";
  if (state.key === "queued") return state.label || "Running";
  return "External";
}

function DiscoverCandidateRow({ row, labIds, jobs, selectedId, onSelectRow }) {
  const state = row.discover_state || discoverCandidateState(row, labIds, jobs);
  const selected = selectedId === candidateId(row);
  const ribbonSource = row.source || row.collect_via || row.source_route || row.publisher || row.backend;
  const meta = candidateMetaLine(row);

  return (
    <li className={selected ? "rd-v2-row-on" : undefined}>
      <button
        type="button"
        className={`row rd-v2-discover-candidate rd-v2-discover-candidate--compact${selected ? " selected" : ""}`}
        data-kind="external"
        data-state={state.key}
        aria-pressed={selected}
        onClick={() => onSelectRow(row)}
      >
        <span className="rd-v2-discover-candidate-source">
          <SourceRibbon source={ribbonSource} />
        </span>
        <span className="rd-v2-discover-candidate-main">
          <span className="rd-v2-discover-candidate-top">
            <strong>{candidateTitle(row)}</strong>
          </span>
          {meta ? <span className="rd-v2-discover-route">{meta}</span> : null}
        </span>
        <span className={`rd-v2-pill ${state.className}`}>{stateLabel(state)}</span>
      </button>
    </li>
  );
}

function DiscoverCandidateList({ rows, labIds, jobs, selectedId, onSelectRow }) {
  return (
    <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Discover candidates">
      {rows.map((row) => (
        <DiscoverCandidateRow
          key={candidateId(row)}
          row={row}
          labIds={labIds}
          jobs={jobs}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
        />
      ))}
    </ul>
  );
}

function DiscoverSearchSummary({ rows, loading, sourceLabel, showExternal }) {
  const countLabel = rows.length
    ? `${rows.length} result${rows.length === 1 ? "" : "s"}`
    : loading
      ? "Searching…"
      : "No results";
  // Never claim "Checking…" once we already have rows — that stuck status was the audit failure.
  const status = loading && !rows.length
    ? "Searching…"
    : [sourceLabel || (loading ? "Searching…" : "Explore"), showExternal ? "includes open web" : null]
        .filter(Boolean)
        .join(" · ");

  return (
    <div className="rd-v2-discover-search-summary" aria-label="Search result summary">
      <div>
        <strong>{countLabel}</strong>
        <span>{status}</span>
      </div>
    </div>
  );
}

function dedupeRows(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const key = candidateId(row).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

function hasExternalRows(rows) {
  return rows.some((row) => {
    const kind = String(row?.kind || "").toLowerCase();
    const source = String(row?.source || "").toLowerCase();
    return (
      kind === "datacite" ||
      kind === "huggingface" ||
      kind === "web_scrape" ||
      source.includes("datacite") ||
      source.includes("huggingface") ||
      source.includes("scrape")
    );
  });
}

export function BrowsePage({
  labIds,
  selectedId,
  onSelectRow,
  searchQuery,
  onSearchChange,
  jobs = [],
  jobBindings = {},
  discoverFilter = "all",
  discoverMode = "explore",
  discoverFocusAwaiting = false,
  onOpenReviewQueue,
  discoverActivityFilter = "all",
  onDiscoverActivityFilterChange,
  onDiscoverModeChange,
  profile = null,
  catalog = [],
  contextDataset = null,
  onDiscoverFilterChange,
  usingSeed = false,
  onSuggestSearch,
  onSearchWeb,
  onResearchQuestion,
  onMergedRowsChange,
  onApproveSafeJobs,
  historyEvents = [],
  selectedHistoryId = "",
  onSelectHistoryEvent,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [demoFallback, setDemoFallback] = useState(false);
  const [facets, setFacets] = useState(() => ({ ...EMPTY_FACETS }));
  const [indexMiss, setIndexMiss] = useState(false);
  const [showExternal, setShowExternal] = useState(false);
  const [searchPhase, setSearchPhase] = useState("idle");
  const [draftQuery, setDraftQuery] = useState(searchQuery || "");
  const [semanticSearch, setSemanticSearch] = useState({ goal: "", loading: false, error: "", total: 0 });
  const labIdsRef = useRef(labIds);
  const searchInputRef = useRef(null);

  useEffect(() => {
    if (!semanticSearch.goal) setDraftQuery(searchQuery || "");
  }, [searchQuery, semanticSearch.goal]);

  useEffect(() => {
    labIdsRef.current = labIds;
  }, [labIds]);

  const pendingRows = useMemo(
    () => pendingApprovalJobs(jobs).map((job) => jobToCandidateRow(job)).filter(Boolean),
    [jobs],
  );

  useEffect(() => {
    if (discoverMode !== "explore" && discoverMode !== "search") return;
    if (discoverFilter && discoverFilter !== "awaiting" && discoverFilter !== facets.access) {
      setFacets((prev) => ({ ...prev, access: discoverFilter }));
    }
  }, [discoverFilter, discoverMode, facets.access]);

  useEffect(() => {
    if (discoverMode !== "explore" && discoverMode !== "search") return;
    if (!pendingRows.length) return;
    if (selectedId) return;
    if (!(discoverFocusAwaiting || discoverActivityFilter === "awaiting")) return;
    onSelectRow?.(pendingRows[0]);
  }, [
    discoverMode,
    pendingRows,
    selectedId,
    onSelectRow,
    discoverFocusAwaiting,
    discoverActivityFilter,
  ]);

  useEffect(() => {
    let cancelled = false;
    const q = (searchQuery || "").trim();
    if (semanticSearch.goal) {
      setLoading(false);
      setSearchPhase("idle");
      return () => {
        cancelled = true;
      };
    }
    if (discoverMode === "history") {
      setLoading(false);
      setSearchPhase("idle");
      setRows([]);
      setSource("");
      setDemoFallback(false);
      setIndexMiss(false);
      setShowExternal(false);
      return () => {
        cancelled = true;
      };
    }
    const email = loadUserEmail();
    const activeLabIds = labIdsRef.current;
    const immediateDemo = discoverDemoSearch(q);
    const immediateCatalog = localCatalogSearch(catalog, q, activeLabIds, 12);
    setLoading(true);
    setSearchPhase(q ? "catalog" : "idle");
    setError("");
    setSource("");
    setDemoFallback(false);
    onSelectRow?.(null);
    if (q) {
      setFacets({ ...EMPTY_FACETS });
      onDiscoverFilterChange?.("all");
      const immediateRows = immediateCatalog.length
        ? immediateCatalog
        : rankRowsForQuery(immediateDemo, q, activeLabIds);
      if (immediateRows.length) {
        setRows(immediateRows);
        setSource(immediateCatalog.length ? "catalog" : "demo");
        setDemoFallback(false);
        onSelectRow?.(pickDefaultRow(immediateRows, q, activeLabIds));
      } else {
        setRows([]);
      }
    } else {
      setRows([]);
    }
    setIndexMiss(false);
    setShowExternal(false);

    const flattenRows = (data) => {
      const fromApi = (data.sections || []).flatMap((s) => s.rows || []);
      return fromApi.length ? fromApi : data.results || data.hits || [];
    };

    const apply = (data, label) => {
      if (cancelled) return 0;
      const flat = rankRowsForQuery(flattenRows(data), q, activeLabIds);
      setRows(flat);
      setSource(label);
      if (label !== "demo") setDemoFallback(false);
      if (q && flat.length) {
        onSelectRow?.(pickDefaultRow(flat, q, activeLabIds));
      }
      return flat.length;
    };

    const run = async () => {
      try {
        if (!q) {
          setRows([]);
          setSource("");
          setDemoFallback(false);
          setSearchPhase("idle");
          return;
        }
        // Preferred Explore contract: /library/discover/sources
        let exploreRows = [];
        try {
          const sources = await discoverSources(q, { limit: 12 });
          if (cancelled) return;
          exploreRows = sourcesResponseToRows(sources);
          if (exploreRows.length) {
            apply({ sections: [{ id: "explore", rows: exploreRows }] }, "explore");
          }
        } catch {
          /* fall through to legacy discover cascade */
        }

        const discover = exploreRows.length
          ? { sections: [{ id: "explore", rows: exploreRows }], index_miss: false, weak_match: false }
          : await discoverSearch(q, 12, email);
        if (cancelled) return;
        const discoverRows = dedupeRows([
          ...immediateCatalog,
          ...(exploreRows.length ? exploreRows : flattenRows(discover)),
        ]);
        if (discoverRows.length && !exploreRows.length) {
          apply({ sections: [{ id: "discover", rows: discoverRows }] }, "discover");
        }
        const needsUnified =
          discoverRows.length === 0 || Boolean(discover.index_miss || discover.weak_match);
        let mergedRows = discoverRows;
        let label = discoverRows.length
          ? (exploreRows.length ? "explore" : immediateCatalog.length ? "catalog" : "discover")
          : "";
        let miss = Boolean(discover.index_miss) && discoverRows.length === 0;
        let external = Boolean(exploreRows.length);

        if (needsUnified) {
          setSearchPhase("search");
          const search = await unifiedSearch(q, 12, email, { skipDiscover: true });
          if (cancelled) return;
          const searchRows = flattenRows(search);
          if (searchRows.length) {
            mergedRows = dedupeRows([...discoverRows, ...searchRows]);
            label = discoverRows.length ? (immediateCatalog.length ? "catalog" : "discover") : "search";
            external = hasExternalRows(searchRows);
            apply({ sections: [{ id: label, rows: mergedRows }] }, label);
          }
          if (!discoverRows.length) {
            miss = Boolean(
              discover.index_miss || search.index_miss || search.discover_index_miss || !searchRows.length,
            );
          }
        }

        const hasAcquireCandidate = mergedRows.some((r) => {
          const st = discoverCandidateState(r, activeLabIds);
          return st.key !== "in_lab" && Boolean(discoverCandidateUrl(r));
        });

        if (mergedRows.length && !hasAcquireCandidate && q && !hasUsefulLabMatch(mergedRows, q, activeLabIds)) {
          setSearchPhase("web");
          const web = await webDiscover(q, 8);
          if (cancelled) return;
          const webRows = webHitsToRows(web);
          if (webRows.length) {
            mergedRows = dedupeRows([...mergedRows, ...webRows]);
            if (!label || discoverStageCounts(mergedRows, activeLabIds, jobs).inLab === mergedRows.length - webRows.length) {
              label = mergedRows.length === webRows.length ? "web" : label || "search";
            }
            external = true;
          }
        }

        if (mergedRows.length) {
          apply({ sections: [{ id: label, rows: mergedRows }] }, label);
          setIndexMiss(false);
          setShowExternal(external || label === "web");
          return;
        }

        if (immediateDemo.length) {
          apply({ sections: [{ id: "demo", rows: immediateDemo }] }, "demo");
          setDemoFallback(true);
          setIndexMiss(false);
          setShowExternal(false);
          return;
        }

        setSearchPhase("web");
        const web = await webDiscover(q, 8);
        if (cancelled) return;
        const webRows = webHitsToRows(web);
        if (webRows.length) {
          apply({ sections: [{ id: "web", rows: webRows }] }, "web");
          setIndexMiss(false);
          setShowExternal(true);
          return;
        }

        setIndexMiss(miss);
        setShowExternal(false);
        setRows([]);
      } catch (err) {
        if (cancelled) return;
        if (immediateDemo.length) {
          setRows(immediateDemo);
          setSource("demo");
          setDemoFallback(true);
          setError("");
        } else {
          setRows([]);
          setError("Catalog search unavailable. Check the query engine and retry.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setSearchPhase("idle");
        }
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [searchQuery, semanticSearch.goal, discoverMode, onSelectRow, onDiscoverFilterChange, catalog]);

  const merged = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const r of rows) {
      const key = r.dataset_id || r.doi || r.title || r.url;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(r);
    }
    return bindJobsToCandidates(out, jobs, jobBindings);
  }, [rows, jobs, jobBindings]);

  useEffect(() => {
    onMergedRowsChange?.(merged);
  }, [merged, onMergedRowsChange]);

  const filtered = useMemo(
    () => merged.filter((r) => rowMatchesFacets(r, facets, labIds, jobs)),
    [merged, facets, labIds, jobs],
  );
  const stageCounts = useMemo(() => discoverStageCounts(merged, labIds, jobs), [merged, labIds, jobs]);

  const sourceLabel =
    source === "discover"
      ? "Discover API"
      : source === "catalog"
        ? "Lab index"
      : source === "search"
        ? "Unified search"
        : source === "web"
          ? "Open web"
          : source === "semantic"
            ? "Semantic lab search"
            : source === "demo"
              ? loading
                ? "Local suggestions"
                : "Demo catalog"
              : null;

  const q = (semanticSearch.goal || searchQuery || "").trim();
  const isExplore = discoverMode === "explore" || discoverMode === "search";
  const showHistory = discoverMode === "history";
  const showQueueStrip = isExplore && pendingRows.length > 0;
  const showDefaultHome = isExplore && !q;
  const hasContextDataset = Boolean(contextDataset?.dataset_id);
  const showSearchResults = isExplore && Boolean(q);
  const allInLab =
    !loading && !semanticSearch.loading && showSearchResults && merged.length > 0 && stageCounts.inLab > 0 && stageCounts.inLab === merged.length;

  const suggestedRows = useMemo(
    () => (showDefaultHome ? discoverSuggestedRows({ catalog, labIds, limit: 4 }) : []),
    [showDefaultHome, catalog, labIds],
  );
  const suggestedBound = useMemo(
    () => bindJobsToCandidates(suggestedRows, jobs, jobBindings),
    [suggestedRows, jobs, jobBindings],
  );
  const suggestedFiltered = useMemo(
    () => suggestedBound.filter((r) => rowMatchesFacets(r, facets, labIds, jobs)),
    [suggestedBound, facets, labIds, jobs],
  );
  const facetOptions = useMemo(
    () => collectFacetOptions(showSearchResults ? merged : suggestedBound),
    [showSearchResults, merged, suggestedBound],
  );
  const onFacetsChange = (next) => {
    setFacets(next);
    onDiscoverFilterChange?.(next.access || "all");
  };
  const filterControl = isExplore ? (
    <DiscoverFilterControl
      facets={facets}
      onChange={onFacetsChange}
      options={facetOptions}
    />
  ) : null;

  const commitSearch = (raw, { switchToExplore = false } = {}) => {
    const next = String(raw ?? draftQuery ?? "").trim();
    setDraftQuery(next);
    setSemanticSearch({ goal: "", loading: false, error: "", total: 0 });
    if (switchToExplore || (discoverMode !== "explore" && discoverMode !== "search")) {
      onDiscoverModeChange?.("explore");
    }
    onSearchChange?.(next);
    onSuggestSearch?.(next);
  };

  const runSemanticSearch = async (raw) => {
    const goal = String(raw ?? draftQuery ?? "").trim();
    if (!goal) return;
    setDraftQuery(goal);
    setSemanticSearch({ goal, loading: true, error: "", total: 0 });
    setRows([]);
    setSource("");
    setError("");
    onSelectRow?.(null);
    if (discoverMode !== "explore" && discoverMode !== "search") onDiscoverModeChange?.("explore");
    try {
      const out = await semanticDiscover(goal, 12);
      const semanticRows = (out.sections || []).flatMap((section) => section.rows || []);
      const nextRows = semanticRows.length ? semanticRows : out.rows || [];
      setRows(nextRows);
      setSource("semantic");
      if (nextRows.length) onSelectRow?.(nextRows[0]);
      setSemanticSearch({ goal, loading: false, error: "", total: Number(out.total) || nextRows.length });
      onResearchQuestion?.({ question: goal, matches: nextRows });
    } catch (err) {
      const message = err?.message || "Semantic search is unavailable. Try catalog search or retry.";
      setError(message);
      setSemanticSearch({ goal, loading: false, error: message, total: 0 });
    }
  };

  const runSuggestedSearch = (suggestion) => {
    commitSearch(suggestion, { switchToExplore: true });
  };

  const clearSearch = () => {
    setDraftQuery("");
    setSemanticSearch({ goal: "", loading: false, error: "", total: 0 });
    onSearchChange?.("");
    onSuggestSearch?.("");
    searchInputRef.current?.focus();
  };

  const pageLead = showHistory
    ? "Trace research questions to reusable evidence"
    : hasContextDataset
      ? `Find sources related to ${displayName(contextDataset)}`
      : "Find sources outside the vault";

  const searchPlaceholder = showHistory
    ? "Search from this trail…"
    : hasContextDataset
      ? "Search sources for this dataset…"
      : "Search external datasets…";

  const toolbarTrailing = (
    <>
      {demoFallback || (usingSeed && source === "demo" && !loading && isExplore) ? (
        <Chip warn>Offline sample</Chip>
      ) : null}
      {pendingRows.length ? (
        <button
          type="button"
          className="rd-v2-discover-queue-btn"
          onClick={() => {
            if (onOpenReviewQueue) onOpenReviewQueue();
            else if (pendingRows[0]) onSelectRow?.(pendingRows[0]);
          }}
        >
          Review queue <strong>{pendingRows.length}</strong>
        </button>
      ) : null}
      {showHistory || showSearchResults || pendingRows.length ? (
        <span className="rd-v2-toolbar-count">
          {showHistory
            ? `${(historyEvents || []).length} recorded`
            : showSearchResults
              ? `${filtered.length} result${filtered.length === 1 ? "" : "s"}`
              : `${pendingRows.length} awaiting approval`}
        </span>
      ) : null}
    </>
  );

  return (
    <PageShell
      className={[
        "rd-v2-discover-page",
        showQueueStrip ? "rd-v2-discover-page--queue" : "",
        showHistory ? "rd-v2-discover-page--history" : "",
        hasContextDataset && showDefaultHome ? "rd-v2-discover-page--context" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      title="Discover"
      lead={pageLead}
      headExtra={
        <DiscoverModeTabs
          mode={discoverMode}
          pendingCount={pendingRows.length}
          onChange={onDiscoverModeChange}
        />
      }
      toolbar={
        <DiscoverToolbar
          draftQuery={draftQuery}
          setDraftQuery={setDraftQuery}
          searchInputRef={searchInputRef}
          placeholder={searchPlaceholder}
          onCommit={(value) => commitSearch(value, { switchToExplore: true })}
          onSemanticSearch={runSemanticSearch}
          onClear={clearSearch}
          filterControl={filterControl}
          trailing={toolbarTrailing}
        />
      }
    >
      {showQueueStrip ? (
        <DiscoverQueueStrip
          rows={pendingRows}
          selectedId={selectedId}
          onSelectJob={(row) => onSelectRow?.(row)}
        />
      ) : null}
      {showHistory ? (
        <DiscoverHistoryPanel
          events={historyEvents}
          selectedId={selectedHistoryId}
          onSelectEvent={onSelectHistoryEvent}
        />
      ) : showDefaultHome ? (
        hasContextDataset ? (
          <div className="rd-v2-discover-empty rd-v2-discover-empty--context" data-testid="discover-empty">
            <DiscoverContextPanel
              dataset={contextDataset}
              labIds={labIds}
              pendingCount={pendingRows.length}
              onSearch={runSuggestedSearch}
            />
            <DiscoverContextSourceList
              rows={suggestedFiltered}
              labIds={labIds}
              selectedId={selectedId}
              onSelectRow={onSelectRow}
              onSearchTitle={(title) => {
                setDraftQuery(title);
                commitSearch(title);
              }}
            />
          </div>
        ) : (
          <DiscoverEmptyState
            profile={profile}
            onSuggest={runSuggestedSearch}
          >
            <DiscoverSuggestedCards
              rows={suggestedFiltered}
              labIds={labIds}
              onSearchTitle={(title) => {
                setDraftQuery(title);
                commitSearch(title);
              }}
            />
          </DiscoverEmptyState>
        )
      ) : (
        <>
          <DiscoverSearchSummary
            rows={filtered}
            loading={loading || semanticSearch.loading}
            sourceLabel={sourceLabel}
            showExternal={showExternal}
          />
          {!loading && !semanticSearch.loading && allInLab ? (
            <div className="rd-v2-discover-miss" data-testid="discover-all-in-lab">
              <p className="rd-v2-empty-inline">
                All {merged.length} matches are already in the lab vault.
                {onSearchWeb ? " " : ""}
                {onSearchWeb ? (
                  <button type="button" className="rd-v2-linkish" onClick={() => onSearchWeb(q)}>
                    Search the open web via Ask →
                  </button>
                ) : null}
              </p>
            </div>
          ) : null}
          {!loading && !semanticSearch.loading && error ? (
            <div className="rd-v2-discover-error">
              <p>{error}</p>
            </div>
          ) : null}
          {!loading && !semanticSearch.loading && !error && filtered.length === 0 ? (
            <div className="rd-v2-discover-miss">
              <p className="rd-v2-empty-inline">
                No matches for “{q}”
                {activeFacetEntries(facets).length ? " with current filters" : ""}
                {indexMiss ? " in the local lab index." : "."}
              </p>
              {onSearchWeb ? (
                <button type="button" className="rd-v2-linkish" onClick={() => onSearchWeb(q)}>
                  Ask the desk →
                </button>
              ) : null}
            </div>
          ) : null}
          <div className="rd-v2-discover-list-panel">
            <DiscoverCandidateList
              rows={filtered}
              labIds={labIds}
              jobs={jobs}
              selectedId={selectedId}
              onSelectRow={onSelectRow}
            />
          </div>
        </>
      )}
    </PageShell>
  );
}
