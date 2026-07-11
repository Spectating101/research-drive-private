import { useEffect, useMemo, useState } from "react";
import { discoverSearch, unifiedSearch, webDiscover } from "@/v2/api";
import {
  classifyDiscoverResult,
  coverageLine,
  descriptiveLine,
  discoverCandidateState,
  exceptionalRowPill,
  orderDiscoverResults,
  taxonomyMatchesFilter,
  taxonomyStageCounts,
} from "@/v2/browseMeta";
import { discoverCandidateUrl, webHitsToRows } from "@/v2/discoverActions";
import { candidateKey, isCandidateQueued, withCandidateKey } from "@/v2/candidateKey";
import { buildDiscoverLifecycle, projectDiscoverCandidateLifecycle } from "@/v2/discoverLifecycle";
import { DiscoverEvaluationSurface } from "@/v2/DiscoverEvaluationSurface";
import { groupDiscoverBrowseRows } from "@/v2/discoverComposition";
import { assessLocalSufficiency } from "@/v2/discoverSufficiency";
import { loadUserEmail } from "@/v2/deskSession";
import { discoverDemoSearch } from "@/v2/deskSeed";
import { DiscoverEmptyState } from "@/v2/DiscoverEmptyState";
import { DiscoverPipeline } from "@/v2/DiscoverPipeline";
import { Chip, PageShell, SourceRibbon } from "@/v2/ui";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "in_lab", label: "In lab" },
  { id: "query_ready", label: "Query ready" },
  { id: "external", label: "External" },
  { id: "needs_access", label: "Needs access" },
];

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

function DiscoverCandidateRow({ row, labIds, selectedId, onSelectRow }) {
  const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
  const state = row.discover_state || discoverCandidateState(row, labIds);
  const selected = selectedId === candidateKey(row);
  const ribbonSource =
    row.source || row.collect_via || row.source_route || row.publisher || row.backend || hostLabel(row.url);
  const taxonomyLine = taxonomy.label;
  const exceptionPill = exceptionalRowPill(row, taxonomy, state);
  const showSufficiency = Number(taxonomy.group) >= 3 && row.discover_sufficiency?.browseLine;

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
          <strong className="rd-v2-discover-candidate-title">
            {selected ? <span className="rd-v2-discover-selected-mark" aria-hidden="true" /> : null}
            {candidateTitle(row)}
          </strong>
          <em className="rd-v2-discover-possession">{taxonomyLine}</em>
          <span className="rd-v2-discover-evidence">{descriptiveLine(row)}</span>
          <span className="rd-v2-discover-coverage">
            <b>Coverage</b>
            <em>{coverageLine(row)}</em>
          </span>
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

function DiscoverCandidateList({ rows, labIds, selectedId, onSelectRow }) {
  return (
    <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Discover candidates">
      {rows.map((row) => (
        <DiscoverCandidateRow
          key={candidateKey(row) || candidateTitle(row)}
          row={row}
          labIds={labIds}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
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
  catalog = [],
  selectedId,
  focusTarget = null,
  onSelectRow,
  onBackToResults,
  onOpenAsk,
  searchQuery,
  jobs = [],
  usingSeed = false,
  probeSnapshots = {},
  onSuggestSearch,
  onSearchWeb,
  // Focused evaluation wiring
  probeState,
  browseLifecycle,
  onAskAbout,
  onAddToLab,
  onPreviewExternal,
  onProbeSource,
  onOpenInLibrary,
  onTrackResources,
  onReviewApproval,
  onRetryLifecycleRefresh,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [demoFallback, setDemoFallback] = useState(false);
  const [stateFilter, setStateFilter] = useState("all");
  const [indexMiss, setIndexMiss] = useState(false);
  const [showExternal, setShowExternal] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const q = (searchQuery || "").trim();
    const email = loadUserEmail();
    const immediateDemo = discoverDemoSearch(q);
    setLoading(true);
    setError("");
    setSource("");
    setDemoFallback(false);
    setRows([]);
    setStateFilter("all");
    setIndexMiss(false);
    setShowExternal(false);

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
        if (!q) {
          setRows([]);
          setSource("");
          setDemoFallback(false);
          return;
        }
        const discover = await discoverSearch(q, 12, email);
        const discoverRows = flattenRows(discover);
        const needsUnified =
          discoverRows.length === 0 || Boolean(discover.index_miss || discover.weak_match);
        let mergedRows = discoverRows;
        let label = discoverRows.length ? "discover" : "";
        let miss = Boolean(discover.index_miss) && discoverRows.length === 0;
        let external = false;

        if (needsUnified) {
          const search = await unifiedSearch(q, 12, email);
          const searchRows = flattenRows(search);
          if (searchRows.length) {
            mergedRows = dedupeRows([...discoverRows, ...searchRows]);
            label = discoverRows.length ? "discover" : "search";
            external = hasExternalRows(searchRows);
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
          setIndexMiss(false);
          setShowExternal(false);
          return;
        }

        const web = await webDiscover(q, 8);
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
        setLoading(false);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [searchQuery, labIds]);

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

  const browseGroups = useMemo(() => groupDiscoverBrowseRows(filtered), [filtered]);

  const stageCounts = useMemo(() => {
    const tax = taxonomyStageCounts(merged, labIds);
    return {
      ...tax,
      queued: merged.filter((r) => r.queued).length,
      acquirable: tax.acquirable,
    };
  }, [merged, labIds]);

  const sourceLabel =
    source === "discover"
      ? "Discover API"
      : source === "search"
        ? "Unified search"
        : source === "web"
          ? "Open web"
          : source === "demo"
            ? "Demo catalog"
            : null;

  const q = (searchQuery || "").trim();
  const allInLab =
    !loading && merged.length > 0 && stageCounts.inLab > 0 && stageCounts.inLab === merged.length;

  // Focused Evaluation mode — evaluation owns the main canvas.
  if (focusTarget) {
    return (
      <div className="rd-v2-discover-focus" data-testid="discover-focus-workspace" data-mode="focus">
        <header className="rd-v2-discover-focus-bar">
          <button type="button" className="rd-v2-btn ghost sm" onClick={() => onBackToResults?.()}>
            ← Back to results
          </button>
          <span className="rd-v2-discover-focus-spacer" />
          <button
            type="button"
            className="rd-v2-btn sm"
            onClick={() => onOpenAsk?.(focusTarget)}
          >
            Ask
          </button>
        </header>
        <DiscoverEvaluationSurface
          variant="workspace"
          target={focusTarget}
          labIds={labIds}
          catalog={catalog}
          onAskAbout={onAskAbout}
          onAddToLab={onAddToLab}
          onPreviewExternal={onPreviewExternal}
          onProbeSource={onProbeSource}
          probeState={probeState}
          onOpenInLibrary={onOpenInLibrary}
          lifecycle={browseLifecycle}
          onTrackResources={onTrackResources}
          onReviewApproval={onReviewApproval}
          onRetryLifecycleRefresh={onRetryLifecycleRefresh}
        />
      </div>
    );
  }

  return (
    <PageShell
      title="Discover"
      lead="Find holdings and public sources, then see what you can actually use"
      toolbar={
        <>
          <Chip active={!!q}>{q ? `“${q}”` : "Awaiting search"}</Chip>
          {sourceLabel ? <Chip>{sourceLabel}</Chip> : null}
          {showExternal ? <Chip>External catalogs</Chip> : null}
          {demoFallback || (usingSeed && source === "demo") ? (
            <Chip warn>Offline sample</Chip>
          ) : null}
          <span className="rd-v2-toolbar-spacer" />
          <span className="rd-v2-toolbar-count">
            {filtered.length} result{filtered.length === 1 ? "" : "s"}
          </span>
        </>
      }
    >
      <div className="rd-v2-discover-browse" data-testid="discover-browse-mode" data-mode="browse">
        <DiscoverPipeline counts={stageCounts} />
        {!q ? (
          <DiscoverEmptyState onSuggest={onSuggestSearch} />
        ) : (
          <>
            <p className="rd-v2-discover-browse-prompt">What data do you need?</p>
            <div className="rd-v2-toolbar inline">
              {FILTERS.map((f) => (
                <Chip
                  key={f.id}
                  active={stateFilter === f.id}
                  onClick={() => setStateFilter(f.id)}
                >
                  {f.label}
                </Chip>
              ))}
            </div>
            {loading && filtered.length ? (
              <p className="rd-v2-browse-loading">Showing offline matches while live catalogs refresh…</p>
            ) : null}
            {loading && !filtered.length ? <p className="rd-v2-browse-loading">Searching catalogs…</p> : null}
            {!loading && allInLab ? (
              <div className="rd-v2-discover-miss">
                <p className="rd-v2-empty-inline warn">
                  All {merged.length} matches are already in your lab vault. Search the open web for new sources.
                </p>
                {onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search the open web via Ask →
                  </button>
                ) : null}
              </div>
            ) : null}
            {!loading && error ? (
              <div className="rd-v2-discover-error">
                <p>{error}</p>
              </div>
            ) : null}
            {!loading && !error && filtered.length === 0 ? (
              <div className="rd-v2-discover-miss">
                <p className="rd-v2-empty-inline">
                  No matches for “{q}”
                  {stateFilter !== "all" ? ` with filter ${stateFilter.replace("_", " ")}` : ""}
                  {indexMiss ? " in the local lab index." : "."}
                </p>
                {indexMiss && onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search the open web via Ask →
                  </button>
                ) : null}
              </div>
            ) : null}
            <div className="rd-v2-discover-list-panel rd-v2-discover-browse-groups">
              {browseGroups.map((group) => (
                <section
                  key={group.id}
                  className="rd-v2-discover-group"
                  data-group={group.id}
                  aria-label={group.title}
                >
                  <h3 className="rd-v2-discover-group-title">{group.title}</h3>
                  <DiscoverCandidateList
                    rows={group.rows}
                    labIds={labIds}
                    selectedId={selectedId}
                    onSelectRow={onSelectRow}
                  />
                </section>
              ))}
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}
