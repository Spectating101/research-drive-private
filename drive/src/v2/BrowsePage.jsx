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
  splitBestFitAndOthers,
} from "@/v2/discoverComposition";
import { assessLocalSufficiency } from "@/v2/discoverSufficiency";
import { loadUserEmail } from "@/v2/deskSession";
import { discoverDemoSearch } from "@/v2/deskSeed";
import { DiscoverEmptyState } from "@/v2/DiscoverEmptyState";
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
  const taxonomyLine = taxonomy.label;
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
  discoverMode = "explore",
  onDiscoverModeChange,
  discoverFocusAwaiting = false,
  historyEvents = [],
  selectedHistoryId = "",
  onSelectHistoryEvent,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [demoFallback, setDemoFallback] = useState(false);
  const [stateFilter, setStateFilter] = useState("all");
  const [indexMiss, setIndexMiss] = useState(false);
  const [externalSearchQuery, setExternalSearchQuery] = useState("");

  const pendingRows = useMemo(
    () => pendingApprovalJobs(jobs).map((job) => jobToCandidateRow(job)).filter(Boolean),
    [jobs],
  );
  const isExplore = discoverMode === "explore" || discoverMode === "search";
  const showHistory = discoverMode === "history";

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
        // Prefer Explore sources contract (semantic hybrid), escalate to live adapters
        // when the local catalogue is thin or Search-wider requested. Fall back to legacy path.
        try {
          const wantLive = Boolean(preferLiveSources);
          let sources = await discoverSources(q, {
            limit: 12,
            semantic: true,
            live: wantLive,
          });
          let sourceRows = sourcesResponseToRows(sources);
          if (!wantLive && sourceRows.length && sourceRows.length < 3) {
            try {
              const liveSources = await discoverSources(q, {
                limit: 12,
                semantic: true,
                live: true,
              });
              const liveRows = sourcesResponseToRows(liveSources);
              if (liveRows.length > sourceRows.length) {
                sources = liveSources;
                sourceRows = liveRows;
              }
            } catch {
              /* live adapters optional — keep local/semantic hits */
            }
          }
          if (!sourceRows.length && !wantLive) {
            try {
              sources = await discoverSources(q, { limit: 12, semantic: true, live: true });
              sourceRows = sourcesResponseToRows(sources);
            } catch {
              /* continue to legacy path */
            }
          }
          if (wantLive) onLiveSourcesConsumed?.(false);
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
          if (preferLiveSources) onLiveSourcesConsumed?.(false);
          /* sources endpoint optional — continue */
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

        if (mergedRows.length && !hasAcquireCandidate && q) {
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

        const web = await webDiscover(q, 8);
        const webRows = webHitsToRows(web);
        if (webRows.length) {
          apply({ sections: [{ id: "web", rows: webRows }] }, "web");
          setIndexMiss(false);
          return;
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

  const ranked = useMemo(() => splitBestFitAndOthers(filtered), [filtered]);
  const interpretation = useMemo(() => interpretEvidenceNeed(searchQuery), [searchQuery]);

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
          <DiscoverEmptyState onSuggest={onSuggestSearch} onCraftUrl={onCraftUrl} />
        ) : (
          <>
            <section
              className="rd-v2-discover-explore-workspace"
              aria-label="Discover explore"
              data-testid="discover-result-summary"
            >
              <header className="rd-v2-discover-explore-need">
                <h2>What evidence are you looking for?</h2>
                <form
                  className="rd-v2-discover-need-form"
                  data-testid="discover-need-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const next = String(event.currentTarget.elements.need?.value || "").trim();
                    if (next) onSuggestSearch?.(next);
                  }}
                >
                  <textarea
                    name="need"
                    className="rd-v2-discover-need-input"
                    data-testid="discover-need-query"
                    defaultValue={q}
                    key={q}
                    rows={1}
                    placeholder="Describe the evidence need — keyword, gap, or research question…"
                    aria-label="Evidence need"
                    onKeyDown={handleEnterToRequestSubmit}
                  />
                  <button type="submit" className="rd-v2-btn sm primary" aria-label="Search evidence need">
                    Search
                  </button>
                </form>
                <p className="rd-v2-ask-send-hint rd-v2-discover-enter-hint">Enter to search · ⇧↵ newline</p>
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
            </section>

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
                  <span>Continue beyond the lab to look for alternatives or broader coverage.</span>
                </div>
                {onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search wider sources →
                  </button>
                ) : null}
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
                    Ask Research Drive to search wider →
                  </button>
                ) : null}
              </div>
            ) : null}

            {ranked.bestFit ? (
              <section className="rd-v2-discover-best-fit" aria-label="Best fit" data-testid="discover-best-fit">
                <div className="rd-v2-home-section-head">
                  <h3>{externalCatalogueActive ? "External catalogue matches" : sourceRouteGap ? "Available lab routes" : "Best fit"}</h3>
                  {externalCatalogueActive ? (
                    <span className="muted">{plural(ranked.total, "external catalogue record")}</span>
                  ) : scopeSummary ? (
                    <span className="muted">{scopeSummary}</span>
                  ) : null}
                </div>
                <DiscoverCandidateList
                  rows={[ranked.bestFit]}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {ranked.others.length ? (
              <section className="rd-v2-discover-other-matches" aria-label="Other matches" data-testid="discover-other-matches">
                <div className="rd-v2-home-section-head">
                  <h3>{externalCatalogueActive ? "Other catalogue records" : "Other matches"}</h3>
                </div>
                <DiscoverCandidateList
                  rows={ranked.others}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {ranked.total ? (
              <footer className="rd-v2-discover-rank-foot" data-testid="discover-rank-foot">
                <span>
                  {plural(ranked.total, "candidate")}
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
                Discover checks lab holdings first, evaluates wider source candidates when the lab is insufficient,
                and returns successful acquisitions to Library for reuse.
              </p>
            </details>
          </>
        )}
      </div>
    </PageShell>
  );
}
