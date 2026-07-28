import { useEffect, useMemo, useState } from "react";
import { discoverSearch, discoverSources, unifiedSearch, webDiscover } from "@/v2/api";
import { sourcesResponseToRows } from "@/v2/discoverAdapters";
import { DiscoverHistoryPanel } from "@/v2/DiscoverHistoryPanel";
import { jobToCandidateRow, pendingApprovalJobs } from "@/v2/procurementJobs";
import {
  classifyDiscoverResult,
  coverageLine,
  descriptiveLine,
  discoverCandidateState,
  exceptionalRowPill,
  humanizeDiscoverDescription,
  orderDiscoverResults,
  taxonomyMatchesFilter,
  taxonomyStageCounts,
} from "@/v2/browseMeta";
import { discoverCandidateUrl, webHitsToRows } from "@/v2/discoverActions";
import { candidateKey, isCandidateQueued, withCandidateKey } from "@/v2/candidateKey";
import { buildDiscoverLifecycle, projectDiscoverCandidateLifecycle } from "@/v2/discoverLifecycle";
import {
  interpretEvidenceNeed,
} from "@/v2/discoverComposition";
import { assessLocalSufficiency } from "@/v2/discoverSufficiency";
import { loadUserEmail } from "@/v2/deskSession";
import { discoverDemoSearch } from "@/v2/deskSeed";
import { DiscoverIntentWorkspace } from "@/v2/DiscoverIntentWorkspace";
import { handleEnterToRequestSubmit } from "@/v2/enterToSubmit";
import { Chip, PageShell, SourceRibbon } from "@/v2/ui";

const FILTERS = [
  { id: "all", label: "All results" },
  { id: "in_lab", label: "In lab" },
  { id: "query_ready", label: "Query ready" },
  { id: "external", label: "Beyond your lab" },
  { id: "needs_access", label: "Needs access" },
];

function plural(value, singular, pluralValue = `${singular}s`) {
  return `${value} ${value === 1 ? singular : pluralValue}`;
}

function resultScopeSummary(counts) {
  const wider = Math.max(0, Number(counts?.external || 0) - Number(counts?.needsAccess || 0));
  return [
    counts?.inLab ? `${plural(counts.inLab, "result")} already in your lab` : null,
    wider ? `${plural(wider, "source")} beyond your lab` : null,
    counts?.needsAccess
      ? counts.needsAccess === 1
        ? "1 source needs access review"
        : `${counts.needsAccess} sources need access review`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}


function candidateTitle(row) {
  return row?.title || row?.name || row?.dataset_id || row?.doi || row?.url || "External dataset";
}

function offeringType(row, taxonomy) {
  const kind = String(row?.kind || row?.type || row?.artifact_type || "").toLowerCase();
  const url = String(row?.url || row?.source_url || row?.resolved_url || "").toLowerCase();
  if (taxonomy?.key?.startsWith("local-")) return "Held dataset";
  if (/paper|article|literature|publication|openalex/.test(kind)) return "Reference only";
  if (/web|page|context/.test(kind)) return "Web context";
  if (/connector|api|bigquery|warehouse/.test(kind) || row?.connector) return "Connector";
  if (/artifact|file|download|csv|parquet|json/.test(kind) || /\.(csv|json|parquet|zip)(?:[?#]|$)/.test(url)) {
    return "Downloadable artifact";
  }
  return "Dataset";
}

function accessLabel(taxonomy) {
  switch (taxonomy?.key) {
    case "local-query-ready":
      return "In lab · Query-ready declared";
    case "external-discoverable":
      return "Access not verified";
    case "external-probed":
      return "Probe observed";
    case "external-acquirable":
      return "Collection route declared";
    case "external-unavailable":
      return "No supported route";
    case "licensed-manual":
      return "Access review required";
    default:
      return taxonomy?.label || "State not recorded";
  }
}

function hostLabel(value) {
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function meaningfulQueryTerms(query) {
  return interpretEvidenceNeed(query).tokens
    .map((token) => String(token || "").toLowerCase())
    .filter((token) => token.length >= 3);
}

function candidateSearchText(row) {
  return [
    row?.title,
    row?.name,
    row?.source,
    row?.publisher,
    row?.description,
    row?.recommended_use,
    ...(Array.isArray(row?.capabilities) ? row.capabilities : []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function hasSpecificSourceRoute(rows, query) {
  const terms = meaningfulQueryTerms(query);
  if (!terms.length) return true;
  return (rows || []).some((row) => {
    const text = candidateSearchText(row);
    return terms.some((term) => text.includes(term));
  });
}

function rankExternalCatalogueRows(rows, query) {
  const terms = meaningfulQueryTerms(query);
  return [...(rows || [])].sort((left, right) => {
    const score = (row) => {
      const title = String(row?.title || "").toLowerCase();
      const text = candidateSearchText(row);
      return terms.reduce(
        (total, term) => total + (title.includes(term) ? 8 : 0) + (text.includes(term) ? 2 : 0),
        0,
      );
    };
    return score(right) - score(left);
  });
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

function DiscoverCandidateRow({ row, labIds, selectedId, onSelectRow, externalCatalogue = false }) {
  const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
  const state = row.discover_state || discoverCandidateState(row, labIds);
  const selected = selectedId === candidateKey(row);
  const ribbonSource =
    row.source || row.collect_via || row.source_route || row.publisher || row.backend || hostLabel(row.url);
  const taxonomyLine = accessLabel(taxonomy);
  const exceptionPill = exceptionalRowPill(row, taxonomy, state);
  const showSufficiency =
    !externalCatalogue && Number(taxonomy.group) >= 3 && row.discover_sufficiency?.browseLine;
  const hasExplicitDescription = Boolean(
    String(row?.description || row?.recommended_use || row?.subtitle || "").trim(),
  );
  const evidenceLine = hasExplicitDescription ? humanizeDiscoverDescription(descriptiveLine(row)) : "";
  const coverage = coverageLine(row);
  const showCoverage = coverage && coverage !== "Coverage not described";

  return (
    <li className={selected ? "rd-v2-row-on" : undefined}>
      <button
        type="button"
        className={`row rd-v2-discover-candidate${selected ? " selected" : ""}${exceptionPill ? " has-exception" : ""}`}
        data-kind={taxonomy.key}
        data-state={state.key}
        data-sufficiency={showSufficiency ? row.discover_sufficiency.state : undefined}
        aria-pressed={selected}
        onClick={() => onSelectRow(row)}
      >
        <span className="rd-v2-discover-candidate-source">
          <SourceRibbon source={ribbonSource} />
          {exceptionPill ? (
            <span className={`rd-v2-pill ${exceptionPill.className}`}>{exceptionPill.label}</span>
          ) : null}
        </span>
        <span className="rd-v2-discover-candidate-main">
          <span className="rd-v2-discover-candidate-heading">
            <strong className="rd-v2-discover-candidate-title">
              {selected ? (
                <span className="rd-v2-discover-selected-mark" aria-hidden="true">
                  ▌
                </span>
              ) : null}
              {candidateTitle(row)}
            </strong>
            <em className="rd-v2-discover-possession">{taxonomyLine}</em>
          </span>
          {evidenceLine ? <span className="rd-v2-discover-evidence">{evidenceLine}</span> : null}
          <span className="rd-v2-discover-offering-facts">
            {[
              offeringType(row, taxonomy),
              row?.refresh_frequency || row?.refresh || row?.update_frequency,
              row?.probe_snapshot?.observed_at ? "Observed probe" : null,
            ].filter(Boolean).join(" · ")}
          </span>
          {showCoverage ? <span className="rd-v2-discover-coverage">{coverage}</span> : null}
          {showSufficiency ? (
            <span
              className={`rd-v2-discover-sufficiency rd-v2-discover-sufficiency-${row.discover_sufficiency.state}`}
              data-testid="discover-sufficiency-line"
            >
              {row.discover_sufficiency.browseLine}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

function DiscoverQueryComposer({
  value,
  onValueChange,
  onSearch,
  onAsk,
  mode = "search",
  onModeChange,
  idle = false,
}) {
  const submit = (event) => {
    event.preventDefault();
    const next = String(value || "").trim();
    if (!next) return;
    if (mode === "ask") onAsk?.(next);
    else onSearch?.(next);
  };
  return (
    <form
      className={`rd-v2-discover-composer${idle ? " is-idle" : ""}`}
      data-testid="discover-query-composer"
      onSubmit={submit}
    >
      <div className="rd-v2-discover-composer-modes" role="group" aria-label="Discover input mode">
        <button
          type="button"
          className={mode === "search" ? "on" : ""}
          aria-pressed={mode === "search"}
          aria-label="Search mode"
          onClick={() => onModeChange?.("search")}
        >
          Search
        </button>
        <button
          type="button"
          className={mode === "ask" ? "on" : ""}
          aria-pressed={mode === "ask"}
          aria-label="Ask mode"
          onClick={() => onModeChange?.("ask")}
        >
          Ask
        </button>
      </div>
      <textarea
        value={value}
        onChange={(event) => onValueChange?.(event.target.value)}
        onKeyDown={handleEnterToRequestSubmit}
        rows={1}
        placeholder={
          mode === "ask"
            ? "Ask about an evidence need, source, or acquisition strategy…"
            : "Search datasets, identifiers, or topics…"
        }
        aria-label={mode === "ask" ? "Ask Discover" : "Search Discover"}
      />
      <button type="submit" className="rd-v2-btn sm primary">
        {mode === "ask" ? "Ask" : "Search"}
      </button>
      <p>
        {mode === "ask"
          ? "Opens the existing Ask rail with this query and the visible Discover evidence in context."
          : "Fast index lookup. Search wider only when you explicitly need live and semantic discovery."}
      </p>
    </form>
  );
}

function routeUnknown(row) {
  if (!row) return "No candidate evidence has been selected.";
  const coverage = coverageLine(row);
  if (coverage && coverage !== "Coverage not described") return `Fit to the full gap beyond ${coverage}.`;
  return "Coverage for the stated gap is not recorded.";
}

function DiscoverRouteComparison({
  gap,
  rows,
  labIds,
  onSelectRow,
  onReviewAcquisition,
  onAsk,
  onSearchWider,
  onClose,
}) {
  const classified = rows.map((row) => ({
    row,
    taxonomy: row.discover_taxonomy || classifyDiscoverResult(row, labIds),
  }));
  const held = classified.find(({ taxonomy }) => taxonomy.key.startsWith("local-"))?.row;
  const publicRoute = classified.find(({ taxonomy }) =>
    ["external-acquirable", "external-probed", "external-discoverable"].includes(taxonomy.key),
  )?.row;
  const accessRoute = classified.find(({ taxonomy }) =>
    ["licensed-manual", "external-unavailable"].includes(taxonomy.key),
  )?.row;
  const routes = [
    held ? {
      id: "reuse",
      label: "Reuse with a limitation",
      adds: candidateTitle(held),
      requires: "Record the limitation before carrying the evidence into Synthesis.",
      unknown: routeUnknown(held),
      action: "Inspect held evidence",
      run: () => onSelectRow?.(held),
    } : null,
    publicRoute ? {
      id: "public",
      label: "Inspect a public collection route",
      adds: candidateTitle(publicRoute),
      requires: "Verify the probe and collection plan; approval remains required before a write.",
      unknown: routeUnknown(publicRoute),
      action: "Review acquisition",
      run: () => onReviewAcquisition?.(publicRoute),
    } : null,
    accessRoute ? {
      id: "access",
      label: "Request access review",
      adds: candidateTitle(accessRoute),
      requires: "Confirm entitlement, permitted fields, and usable historical coverage.",
      unknown: routeUnknown(accessRoute),
      action: "Review access route",
      run: () => onReviewAcquisition?.(accessRoute),
    } : null,
    {
      id: "implementation",
      label: "Record implementation needed",
      adds: "A durable specification for the unresolved evidence requirement.",
      requires: "Engineering ownership and a supported source route.",
      unknown: "Delivery timing and implementation feasibility are not established.",
      action: "Discuss implementation",
      run: () => onAsk?.(
        `Record an implementation need for this Discover gap: ${gap?.statement || "unresolved evidence gap"}. Identify the evidence contract, unknowns, and the safest next valid action. Do not submit procurement or invent delivery timing.`,
      ),
    },
  ].filter(Boolean);

  useEffect(() => {
    const handleKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="rd-v2-discover-route-scrim"
      onMouseDown={(event) => event.target === event.currentTarget && onClose?.()}
    >
      <section
        className="rd-v2-discover-route-compare"
        data-testid="discover-route-comparison"
        role="dialog"
        aria-modal="true"
        aria-label="Ways to get this evidence"
      >
        <header>
          <div>
            <span className="rd-v2-eyebrow">Custom acquisition strategy</span>
            <h3>{gap?.statement || "Unresolved evidence requirement"}</h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Close acquisition strategy">Close</button>
        </header>
        <p className="rd-v2-discover-route-intro">
          Compare only routes supported by the evidence currently visible. Nothing is submitted from this preview.
        </p>
        <div className="rd-v2-discover-route-grid">
          {routes.map((route) => (
            <article key={route.id}>
              <h4>{route.label}</h4>
              <dl>
                <div><dt>Adds</dt><dd>{route.adds}</dd></div>
                <div><dt>Requires</dt><dd>{route.requires}</dd></div>
                <div><dt>Unknown</dt><dd>{route.unknown}</dd></div>
              </dl>
              <button type="button" onClick={route.run}>{route.action} →</button>
            </article>
          ))}
        </div>
        <footer>
          <p>A chosen acquisition route opens the existing review and approval flow.</p>
          {!publicRoute && !accessRoute && onSearchWider ? (
            <button type="button" onClick={onSearchWider}>Search wider for external offerings →</button>
          ) : null}
        </footer>
      </section>
    </div>
  );
}

function DiscoverCandidateList({ rows, labIds, selectedId, onSelectRow, externalCatalogue = false }) {
  return (
    <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Discover candidates">
      {rows.map((row) => (
        <DiscoverCandidateRow
          key={candidateKey(row) || candidateTitle(row)}
          row={row}
          labIds={labIds}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
          externalCatalogue={externalCatalogue}
        />
      ))}
    </ul>
  );
}

function dedupeRows(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const stamped = withCandidateKey(row);
    const key = candidateKey(stamped);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(stamped);
  }
  return out;
}


export function BrowsePage({
  labIds,
  catalog = [],
  selectedId,
  onSelectRow,
  searchQuery,
  preferLiveSources = false,
  onLiveSourcesConsumed,
  jobs = [],
  usingSeed = false,
  probeSnapshots = {},
  onSuggestSearch,
  onCraftUrl,
  onSearchWeb,
  onAskQuery,
  onReviewAcquisition,
  discoverMode = "explore",
  onDiscoverModeChange,
  discoverFocusAwaiting = false,
  historyEvents = [],
  selectedHistoryId = "",
  onSelectHistoryEvent,
  intentRecord = null,
  onIntentChange,
  onCloseIntent,
  onIntentSubmitted,
  onOpenIntentHistory,
  assessmentActive = false,
  assessmentResult = null,
  onOpenAssessment,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [demoFallback, setDemoFallback] = useState(false);
  const [stateFilter, setStateFilter] = useState("all");
  const [indexMiss, setIndexMiss] = useState(false);
  const [externalSearchQuery, setExternalSearchQuery] = useState("");
  const [routeComparisonOpen, setRouteComparisonOpen] = useState(false);
  const [queryDraft, setQueryDraft] = useState(searchQuery || "");
  const [composerMode, setComposerMode] = useState("search");

  const pendingRows = useMemo(
    () => pendingApprovalJobs(jobs).map((job) => jobToCandidateRow(job)).filter(Boolean),
    [jobs],
  );
  const isExplore = discoverMode === "explore" || discoverMode === "search";
  const showHistory = discoverMode === "history";

  useEffect(() => {
    setQueryDraft(searchQuery || "");
    setRouteComparisonOpen(false);
  }, [searchQuery]);

  useEffect(() => {
    if (!isExplore) return;
    if (!pendingRows.length) return;
    if (selectedId) return;
    if (!discoverFocusAwaiting) return;
    onSelectRow?.(pendingRows[0]);
  }, [isExplore, pendingRows, selectedId, onSelectRow, discoverFocusAwaiting]);

  useEffect(() => {
    let cancelled = false;
    const q = (searchQuery || "").trim();
    const externalSearchActive = Boolean(q && externalSearchQuery === q);
    const email = loadUserEmail();
    const immediateDemo = discoverDemoSearch(q);
    setLoading(true);
    setError("");
    setSource("");
    setDemoFallback(false);
    setRows([]);
    setStateFilter("all");
    setIndexMiss(false);

    const flattenRows = (data) => {
      const fromApi = (data.sections || []).flatMap((s) => s.rows || []);
      return fromApi.length ? fromApi : data.results || data.hits || [];
    };

    const apply = (data, label) => {
      if (cancelled) return 0;
      const flat = flattenRows(data);
      setRows(flat);
      setSource(label);
      if (label !== "demo") setDemoFallback(false);
      return flat.length;
    };

    const run = async () => {
      try {
        if (discoverMode === "history") {
          setRows([]);
          setSource("");
          setDemoFallback(false);
          setLoading(false);
          return;
        }
        if (!q) {
          setRows([]);
          setSource("");
          setDemoFallback(false);
          return;
        }
        if (externalSearchActive) {
          const web = await webDiscover(q, 8);
          const webRows = rankExternalCatalogueRows(webHitsToRows(web), q);
          if (webRows.length) {
            apply({ sections: [{ id: "external_catalogues", rows: webRows }] }, "external_catalogues");
            setIndexMiss(Boolean(web.index_miss));
            return;
          }
          setIndexMiss(true);
          setRows([]);
          return;
        }
        // Two tempos, deliberately separated. A plain keyword lookup must stay fast,
        // so it uses the index-only path below (discoverSearch/unifiedSearch).
        // Semantic hybrid search and live external adapters are an explicit
        // escalation via "Search wider" (preferLiveSources): that cascade costs
        // several sequential round trips, and paying it on every ordinary query is
        // what made a simple lookup take ~10s against the live desk.
        if (preferLiveSources) {
        try {
          let sources = await discoverSources(q, {
            limit: 12,
            semantic: true,
            live: true,
          });
          let sourceRows = sourcesResponseToRows(sources);
          onLiveSourcesConsumed?.(false);
          if (sourceRows.length) {
            // A capability route is not an evidence match. When the source
            // catalogue cannot name a route that actually matches the need,
            // consult the external catalogue before showing generic providers.
            if (!hasSpecificSourceRoute(sourceRows, q)) {
              try {
                const web = await webDiscover(q, 8);
                const webRows = rankExternalCatalogueRows(webHitsToRows(web), q);
                if (webRows.length) {
                  apply({ sections: [{ id: "external_catalogues", rows: webRows }] }, "external_catalogues");
                  setIndexMiss(Boolean(web.index_miss));
                  return;
                }
              } catch {
                // Catalogue availability is optional; retain known routes as a truthful fallback.
              }
            }
            apply({ results: sourceRows }, sources.demo ? "demo" : "sources");
            if (sources.demo) setDemoFallback(true);
            setIndexMiss(false);
            return;
          }
        } catch {
          onLiveSourcesConsumed?.(false);
          /* sources endpoint optional — fall through to the index path */
        }
        }
        const discover = await discoverSearch(q, 12, email);
        const discoverRows = flattenRows(discover);
        const needsUnified =
          discoverRows.length === 0 || Boolean(discover.index_miss || discover.weak_match);
        let mergedRows = discoverRows;
        let label = discoverRows.length ? "discover" : "";
        let miss = Boolean(discover.index_miss) && discoverRows.length === 0;

        if (needsUnified) {
          const search = await unifiedSearch(q, 12, email);
          const searchRows = flattenRows(search);
          if (searchRows.length) {
            mergedRows = dedupeRows([...discoverRows, ...searchRows]);
            label = discoverRows.length ? "discover" : "search";
          }
          if (!discoverRows.length) {
            miss = Boolean(
              discover.index_miss || search.index_miss || search.discover_index_miss || !searchRows.length,
            );
          }
        }

        const hasAcquireCandidate = mergedRows.some((r) => {
          const tax = classifyDiscoverResult(r, labIds);
          return !tax.key.startsWith("local-") && Boolean(discoverCandidateUrl(r));
        });

        // Open-web enrichment is another network hop. Keep it on the explicit
        // "Search wider" escalation; an index hit that lacks an acquire route is
        // still a truthful instant result, and the user can widen from there.
        if (preferLiveSources && mergedRows.length && !hasAcquireCandidate && q) {
          const web = await webDiscover(q, 8);
          const webRows = webHitsToRows(web);
          if (webRows.length) {
            mergedRows = dedupeRows([...mergedRows, ...webRows]);
            if (!label) label = "web";
          }
        }

        if (mergedRows.length) {
          apply({ sections: [{ id: label, rows: mergedRows }] }, label);
          setIndexMiss(false);
          return;
        }

        if (immediateDemo.length) {
          apply({ sections: [{ id: "demo", rows: immediateDemo }] }, "demo");
          setIndexMiss(false);
          return;
        }

        if (preferLiveSources) {
          const web = await webDiscover(q, 8);
          const webRows = webHitsToRows(web);
          if (webRows.length) {
            apply({ sections: [{ id: "web", rows: webRows }] }, "web");
            setIndexMiss(false);
            return;
          }
        }

        setIndexMiss(miss);
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
        setLoading(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [searchQuery, discoverMode, labIds, preferLiveSources, onLiveSourcesConsumed, externalSearchQuery]);

  const merged = useMemo(() => {
    const seen = new Set();
    const stampedRows = [];
    for (const r of rows) {
      const stamped = withCandidateKey(r);
      const key = candidateKey(stamped);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const queued = isCandidateQueued(stamped, jobs);
      const withProbe =
        probeSnapshots[key] && !stamped.probe_snapshot
          ? {
              ...stamped,
              probe_snapshot: {
                ...probeSnapshots[key],
                candidate_key: probeSnapshots[key].candidate_key || key,
              },
            }
          : stamped;
      const base = queued ? { ...withProbe, queued: true } : withProbe;
      const life = buildDiscoverLifecycle({
        row: base,
        jobs,
        catalog,
        labIds,
      });
      const projected = projectDiscoverCandidateLifecycle(base, life);
      const taxonomy = projected.discover_taxonomy || classifyDiscoverResult(projected, labIds);
      const sufficiency =
        Number(taxonomy.group) >= 3 ? assessLocalSufficiency(projected, catalog) : null;
      stampedRows.push({
        ...projected,
        discover_taxonomy: taxonomy,
        discover_sufficiency: sufficiency,
      });
    }
    return orderDiscoverResults(stampedRows, labIds);
  }, [rows, jobs, labIds, catalog, probeSnapshots]);

  const filtered = useMemo(() => {
    if (stateFilter === "all") return merged;
    return merged.filter((r) => {
      const tax = r.discover_taxonomy || classifyDiscoverResult(r, labIds);
      return taxonomyMatchesFilter(tax, stateFilter);
    });
  }, [merged, stateFilter, labIds]);

  const interpretation = useMemo(() => interpretEvidenceNeed(searchQuery), [searchQuery]);

  const resultGroups = useMemo(() => {
    const groups = {
      available: [],
      external: [],
      held: [],
      context: [],
    };
    for (const row of filtered) {
      const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
      const type = offeringType(row, taxonomy);
      if (taxonomy.key.startsWith("local-")) groups.held.push(row);
      else if (type === "Reference only" || type === "Web context") groups.context.push(row);
      else if (["external-acquirable", "external-probed"].includes(taxonomy.key)) groups.available.push(row);
      else groups.external.push(row);
    }
    return groups;
  }, [filtered, labIds]);

  const filterCounts = useMemo(
    () =>
      Object.fromEntries(
        FILTERS.map((item) => [
          item.id,
          item.id === "all"
            ? merged.length
            : merged.filter((row) => {
                const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
                return taxonomyMatchesFilter(taxonomy, item.id);
              }).length,
        ]),
      ),
    [merged, labIds],
  );

  const stageCounts = useMemo(() => {
    const tax = taxonomyStageCounts(merged, labIds);
    return {
      ...tax,
      queued: merged.filter((r) => r.queued).length,
      acquirable: tax.acquirable,
    };
  }, [merged, labIds]);

  const q = (searchQuery || "").trim();
  const allInLab =
    !loading && merged.length > 0 && stageCounts.inLab > 0 && stageCounts.inLab === merged.length;
  const demoMode = demoFallback || (usingSeed && source === "demo");
  const scopeSummary = resultScopeSummary(stageCounts);
  const activeFilter = FILTERS.find((item) => item.id === stateFilter) || FILTERS[0];
  const externalSearchActive = Boolean(q && externalSearchQuery === q);
  const externalCatalogueActive = externalSearchActive || source === "external_catalogues";
  const sourceRouteGap =
    !loading &&
    !externalSearchActive &&
    source === "sources" &&
    merged.length > 0 &&
    !hasSpecificSourceRoute(merged, q);
  const assessmentStatus = String(assessmentResult?.assessment_status || "").toLowerCase();
  const assessmentVerdict = String(assessmentResult?.verdict || "").toLowerCase();
  const hasEvidenceGap =
    assessmentStatus === "assessed"
    && ["partially_covered", "partial", "not_covered", "uncovered"].includes(assessmentVerdict)
    && assessmentResult?.gap;
  const hasMetadataGap = assessmentStatus === "insufficient_metadata";
  const idleHoldings = useMemo(
    () => catalog.slice(0, 4).map((row) => ({
      ...row,
      discover_taxonomy: classifyDiscoverResult(row, labIds),
    })),
    [catalog, labIds],
  );

  const modeTabs = (
    <DiscoverModeTabs
      mode={showHistory ? "history" : "explore"}
      pendingCount={pendingRows.length}
      onChange={onDiscoverModeChange}
    />
  );

  const filterMenu = (
    <details className="rd-v2-discover-filter-menu" data-testid="discover-filter-menu">
      <summary>
        <span>Filters</span>
        {stateFilter !== "all" ? <strong>{activeFilter.label}</strong> : null}
      </summary>
      <div className="rd-v2-discover-filter-popover" role="group" aria-label="Filter Discover results">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={stateFilter === item.id ? "on" : ""}
            aria-pressed={stateFilter === item.id}
            onClick={(event) => {
              setStateFilter(item.id);
              event.currentTarget.closest("details")?.removeAttribute("open");
            }}
          >
            <span>{item.label}</span>
            <b>{filterCounts[item.id] || 0}</b>
          </button>
        ))}
      </div>
    </details>
  );

  if (showHistory) {
    return (
      <PageShell
        className="rd-v2-discover-page rd-v2-discover-page--history"
        title="Discover"
        lead="Trace research questions to reusable evidence"
        headExtra={modeTabs}
      >
        <DiscoverHistoryPanel
          events={historyEvents}
          selectedId={selectedHistoryId}
          onSelectEvent={onSelectHistoryEvent}
        />
      </PageShell>
    );
  }

  if (intentRecord) {
    return (
      <PageShell
        className="rd-v2-discover-page rd-v2-discover-page--intent"
        title="Discover"
        lead="Review one durable acquisition intent before collection"
        headExtra={modeTabs}
      >
        <DiscoverIntentWorkspace
          record={intentRecord}
          onChange={onIntentChange}
          onBack={onCloseIntent}
          onAsk={(record) => onAskQuery?.(
            record?.researchNeed || searchQuery,
            {
              kind: "implementation",
              prompt: `Investigate acquisition routes for ${record?.candidate?.title || "this offering"}. Intent ${record?.intent?.id || "is recorded"}. Explain only supported routes, required evidence, and unknowns. Do not submit procurement.`,
            },
          )}
          onSubmitted={onIntentSubmitted}
          onOpenHistory={onOpenIntentHistory}
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      className="rd-v2-discover-page"
      title="Discover"
      lead="Search the lab first, then evaluate sources beyond it"
      headExtra={modeTabs}
      toolbar={demoMode ? <Chip warn>Demo preview · static sample</Chip> : null}
    >
      <div className="rd-v2-discover-browse" data-testid="discover-browse-mode" data-mode="browse">
        {!q ? (
          <section className="rd-v2-discover-idle" data-testid="discover-empty">
            <DiscoverQueryComposer
              value={queryDraft}
              onValueChange={setQueryDraft}
              onSearch={onSuggestSearch}
              onAsk={(question) => onAskQuery?.(question, { kind: "investigation" })}
              mode={composerMode}
              onModeChange={setComposerMode}
              idle
            />
            <div className="rd-v2-discover-idle-held">
              <div className="rd-v2-home-section-head">
                <div>
                  <span className="rd-v2-eyebrow">Held locally</span>
                  <h3>Start with evidence already in the lab</h3>
                </div>
                <span className="muted">{plural(catalog.length, "catalog record")}</span>
              </div>
              {idleHoldings.length ? (
                <DiscoverCandidateList
                  rows={idleHoldings}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                />
              ) : <p className="muted">No local catalog metadata is available yet.</p>}
            </div>
            {onCraftUrl ? (
              <form
                className="rd-v2-discover-idle-intake"
                data-testid="discover-craft-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const target = String(event.currentTarget.elements.sourceTarget?.value || "").trim();
                  if (target) onCraftUrl(target);
                }}
              >
                <label htmlFor="discover-idle-source-target">Have a URL or DOI?</label>
                <input id="discover-idle-source-target" name="sourceTarget" type="text" inputMode="url" placeholder="Paste a public URL or DOI" aria-label="Public URL or DOI" />
                <button type="submit">Inspect →</button>
              </form>
            ) : null}
          </section>
        ) : null}
        {q ? (
          <>
            <section
              className="rd-v2-discover-explore-workspace"
              aria-label="Discover explore"
              data-testid="discover-result-summary"
            >
              <header className="rd-v2-discover-explore-need">
                <DiscoverQueryComposer
                  value={queryDraft}
                  onValueChange={setQueryDraft}
                  onSearch={onSuggestSearch}
                  onAsk={(question) => onAskQuery?.(question, { kind: "results", rows: merged })}
                  mode={composerMode}
                  onModeChange={setComposerMode}
                />
              </header>

              <div className="rd-v2-discover-query-tools">
                {interpretation.chips.length ? (
                  <div className="rd-v2-discover-interpreting" data-testid="discover-interpreting">
                    <span className="rd-v2-eyebrow">Research brief</span>
                  <div className="rd-v2-discover-interpreting-chips" role="list" aria-label="Interpreted evidence need">
                    {interpretation.chips.map((chip) => (
                      <span key={chip} role="listitem" className="rd-v2-discover-chip">
                        {chip}
                      </span>
                    ))}
                    {interpretation.overflow > 0 ? (
                      <span role="listitem" className="rd-v2-discover-chip muted">
                        +{interpretation.overflow}
                      </span>
                    ) : null}
                  </div>
                  <details className="rd-v2-discover-refine">
                    <summary>Refine evidence need</summary>
                    <div className="rd-v2-discover-refine-body">
                      <p>
                        <b>Research object</b> {interpretation.chips[0] || "—"}
                      </p>
                      <p>
                        <b>Evidence need</b> {q}
                      </p>
                      <p>
                        <b>Signals</b> {interpretation.tokens?.join(" · ") || interpretation.chips.join(" · ")}
                      </p>
                    </div>
                  </details>
                  </div>
                ) : null}
                {filterMenu}
              </div>
              <div className="rd-v2-discover-result-actions" aria-label="Discover next actions">
                <div>
                  <strong>{plural(filtered.length, "result")}</strong>
                  <span>{preferLiveSources || source === "sources" || externalCatalogueActive ? "wider discovery" : "index lookup"}</span>
                </div>
                <div>
                  {onSearchWeb ? (
                    <button type="button" onClick={() => onSearchWeb(q)}>
                      Search wider
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className={assessmentActive ? "on" : ""}
                    onClick={() => {
                      onOpenAssessment?.(q);
                      setRouteComparisonOpen(false);
                    }}
                  >
                    Assess coverage
                  </button>
                </div>
              </div>
            </section>

            {hasMetadataGap && onAskQuery ? (
              <div className="rd-v2-discover-metadata-action">
                <div>
                  <strong>Coverage is not yet recorded.</strong>
                  <span>The assessment remains available in Detail; Ask can prepare a metadata review without starting procurement.</span>
                </div>
                <button type="button" onClick={() => onAskQuery(
                  q,
                  {
                    kind: "metadata_review",
                    prompt: `Review the catalog metadata gap for: ${q}. Identify which held records need coverage verification and what evidence would establish their unit, geography, period, frequency, fields, or event type. Do not start procurement.`,
                  },
                )}>
                  Ask for catalog review →
                </button>
              </div>
            ) : null}

            {resultGroups.available.length ? (
              <section className="rd-v2-discover-best-fit" aria-label="Available to add" data-testid="discover-best-fit">
                <div className="rd-v2-home-section-head">
                  <div>
                    <span className="rd-v2-eyebrow">Beyond your library</span>
                    <h3>Available to add</h3>
                  </div>
                  <span className="muted">{plural(resultGroups.available.length, "supported offering")}</span>
                </div>
                <DiscoverCandidateList
                  rows={resultGroups.available}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {hasEvidenceGap && !routeComparisonOpen ? (
              <div className="rd-v2-discover-gap-action">
                <div>
                  <span className="rd-v2-eyebrow">Custom strategy available</span>
                  <strong>{assessmentResult?.gap?.statement || "A recorded evidence gap needs a supported acquisition route."}</strong>
                  <span>Review how the desk can obtain the missing evidence without leaving these results.</span>
                </div>
                <button type="button" onClick={() => setRouteComparisonOpen(true)}>
                  Review strategy →
                </button>
              </div>
            ) : null}

            {hasEvidenceGap && routeComparisonOpen ? (
              <DiscoverRouteComparison
                gap={assessmentResult.gap}
                rows={merged}
                labIds={labIds}
                onSelectRow={onSelectRow}
                onReviewAcquisition={onReviewAcquisition}
                onAsk={(prompt) => onAskQuery?.(q, { kind: "implementation", prompt })}
                onSearchWider={() => onSearchWeb?.(q)}
                onClose={() => setRouteComparisonOpen(false)}
              />
            ) : null}

            {loading && filtered.length ? (
              <p className="rd-v2-browse-loading">Showing current matches while wider sources refresh…</p>
            ) : null}
            {loading && !filtered.length ? (
              <p className="rd-v2-browse-loading">Searching the lab and wider sources…</p>
            ) : null}

            {!loading && allInLab ? (
              <div className="rd-v2-discover-expand-search">
                <div>
                  <strong>You already hold every current match.</strong>
                  <span>Search wider only when you need alternatives or broader coverage.</span>
                </div>
              </div>
            ) : null}

            {!loading && error ? (
              <div className="rd-v2-discover-error">
                <p>{error}</p>
              </div>
            ) : null}

            {sourceRouteGap ? (
              <section className="rd-v2-discover-route-gap" aria-label="No specific source route match">
                <div>
                  <span className="rd-v2-eyebrow">No direct route match</span>
                  <strong>No current lab source route specifically matches “{q}”.</strong>
                  <p>The routes below are available to the lab, but they are not evidence results for this question.</p>
                </div>
                <button type="button" className="rd-v2-btn sm" onClick={() => setExternalSearchQuery(q)}>
                  Search external catalogues
                </button>
              </section>
            ) : null}

            {!loading && !error && filtered.length === 0 ? (
              <div className="rd-v2-discover-miss">
                <p className="rd-v2-empty-inline">
                  No {stateFilter === "all" ? "" : `${activeFilter.label.toLowerCase()} `}matches for “{q}”
                  {indexMiss ? " in the current research index." : "."}
                </p>
                {indexMiss && onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search wider sources →
                  </button>
                ) : null}
              </div>
            ) : null}

            {resultGroups.external.length ? (
              <section
                className={resultGroups.available.length ? "rd-v2-discover-other-matches" : "rd-v2-discover-best-fit"}
                aria-label="Other external matches"
                data-testid={resultGroups.available.length ? "discover-other-matches" : "discover-best-fit"}
              >
                <div className="rd-v2-home-section-head">
                  <h3>{externalCatalogueActive ? "External catalogue matches" : "Other external matches"}</h3>
                  {externalCatalogueActive ? (
                    <span className="muted">{plural(resultGroups.external.length, "external catalogue record")}</span>
                  ) : scopeSummary ? (
                    <span className="muted">{scopeSummary}</span>
                  ) : null}
                </div>
                <DiscoverCandidateList
                  rows={resultGroups.external}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {resultGroups.held.length ? (
              <details className="rd-v2-discover-held-results" open={!resultGroups.available.length && !resultGroups.external.length}>
                <summary>
                  <span>Already in your Library</span>
                  <b>{resultGroups.held.length}</b>
                </summary>
                <DiscoverCandidateList
                  rows={resultGroups.held}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                />
              </details>
            ) : null}

            {resultGroups.context.length ? (
              <section className="rd-v2-discover-other-matches" aria-label="References and web context">
                <div className="rd-v2-home-section-head">
                  <h3>References and web context</h3>
                </div>
                <DiscoverCandidateList
                  rows={resultGroups.context}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {filtered.length ? (
              <footer className="rd-v2-discover-rank-foot" data-testid="discover-rank-foot">
                <span>
                  {plural(filtered.length, "candidate")}
                  {stateFilter !== "all" ? ` · ${activeFilter.label}` : ""}
                </span>
                <span className="muted">
                  {externalCatalogueActive
                    ? "Ordered by title and description match to this question"
                    : "Ranked using active research + interpreted evidence need"}
                </span>
              </footer>
            ) : null}

            <details className="rd-v2-discover-process-disclosure">
              <summary>How Discover handles a missing dataset</summary>
              <p>
                Discover checks the index first. Wider discovery is explicit; coverage assessment names one evidence
                gap; route comparison preserves unknowns; and any collection remains approval-gated before its
                verified output is registered in Library and recorded in History.
              </p>
            </details>
          </>
        ) : null}
      </div>
    </PageShell>
  );
}
