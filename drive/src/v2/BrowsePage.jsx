import { useEffect, useMemo, useState } from "react";
import { discoverSearch, unifiedSearch, webDiscover } from "@/v2/api";
import {
  discoverCandidateState,
  discoverStageCounts,
} from "@/v2/browseMeta";
import { webHitsToRows, discoverCandidateUrl } from "@/v2/discoverActions";
import { candidateKey, isCandidateQueued, withCandidateKey } from "@/v2/candidateKey";
import { loadUserEmail } from "@/v2/deskSession";
import { discoverDemoSearch } from "@/v2/deskSeed";
import { DiscoverEmptyState } from "@/v2/DiscoverEmptyState";
import { DiscoverPipeline } from "@/v2/DiscoverPipeline";
import { Chip, PageShell, SourceRibbon } from "@/v2/ui";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "probe_ready", label: "Ready to check" },
  { id: "queued", label: "Queued" },
  { id: "in_lab", label: "In lab" },
];

function rowFilterState(row, labIds) {
  return discoverCandidateState(row, labIds).key;
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
    if (!text || seen.has(key)) continue;
    seen.add(key);
    out.push(text);
  }
  return out;
}

function shortText(value, max = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trim()}…`;
}

function candidateRoute(row) {
  const host = hostLabel(row?.url);
  const source = row?.publisher || row?.source || row?.domain || host || row?.backend;
  const route = row?.collect_via || row?.source_route || row?.access_mode;
  return uniqueParts([source, route]).join(" · ") || "Public source";
}

function candidateEvidence(row, state) {
  const sourceText = row?.description || row?.recommended_use || row?.limitations;
  const metadata = uniqueParts([
    row?.coverage || row?.date_range || row?.temporal_coverage,
    row?.grain,
    row?.license || row?.access,
  ]).join(" · ");
  const fallback = uniqueParts([state.fit, state.access, state.probe]).join(" · ");
  return shortText(uniqueParts([sourceText, metadata]).join(" · ") || fallback, 210);
}

function candidateSubline(row) {
  return uniqueParts([
    row?.dataset_id,
    row?.doi,
    hostLabel(row?.url),
  ]).join(" · ");
}

function stateLabel(state) {
  if (state.key === "probe_ready") return "Ready to check";
  if (state.key === "in_lab") return "In lab";
  if (state.key === "queued") return "Queued";
  return "External";
}

function DiscoverFact({ label, value }) {
  return (
    <span className="rd-v2-discover-fact">
      <b>{label}</b>
      <em>{value}</em>
    </span>
  );
}

function DiscoverCandidateRow({ row, labIds, selectedId, onSelectRow }) {
  const state = row.discover_state || discoverCandidateState(row, labIds);
  const selected = selectedId === candidateKey(row);
  const ribbonSource = row.source || row.collect_via || row.source_route || row.publisher || row.backend;
  const route = candidateRoute(row);
  const subline = candidateSubline(row);

  return (
    <li className={selected ? "rd-v2-row-on" : undefined}>
      <button
        type="button"
        className={`row rd-v2-discover-candidate${selected ? " selected" : ""}`}
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
          <span className="rd-v2-discover-route">{route}</span>
          <span className="rd-v2-discover-evidence">{candidateEvidence(row, state)}</span>
          {subline ? <span className="rd-v2-discover-subline">{subline}</span> : null}
        </span>
        <span className="rd-v2-discover-facts" aria-label="Candidate details">
          <DiscoverFact label="Fit" value={state.fit} />
          <DiscoverFact label="Access" value={state.access} />
          <DiscoverFact label="Probe" value={state.probe} />
          <DiscoverFact label="Destination" value={state.destination} />
        </span>
        <span className={`rd-v2-pill ${state.className}`}>{stateLabel(state)}</span>
      </button>
    </li>
  );
}

function DiscoverCandidateList({ rows, labIds, selectedId, onSelectRow }) {
  return (
    <>
      <div className="rd-v2-discover-list-hd" aria-hidden="true">
        <span>Source</span>
        <span>Candidate</span>
        <span>Fit · access · probe · destination</span>
        <span>Action</span>
      </div>
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
    </>
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
  selectedId,
  onSelectRow,
  searchQuery,
  jobs = [],
  usingSeed = false,
  onSuggestSearch,
  onSearchWeb,
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
          const st = discoverCandidateState(r, labIds);
          return st.key !== "in_lab" && Boolean(discoverCandidateUrl(r));
        });

        if (mergedRows.length && !hasAcquireCandidate && q) {
          const web = await webDiscover(q, 8);
          const webRows = webHitsToRows(web);
          if (webRows.length) {
            mergedRows = dedupeRows([...mergedRows, ...webRows]);
            if (!label || discoverStageCounts(mergedRows, labIds).inLab === mergedRows.length - webRows.length) {
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
    const out = [];
    for (const r of rows) {
      const stamped = withCandidateKey(r);
      const key = candidateKey(stamped);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const queued = isCandidateQueued(stamped, jobs);
      out.push(queued ? { ...stamped, queued: true } : stamped);
    }
    return out;
  }, [rows, jobs]);

  const filtered = useMemo(() => {
    if (stateFilter === "all") return merged;
    return merged.filter((r) => rowFilterState(r, labIds) === stateFilter);
  }, [merged, stateFilter, labIds]);
  const stageCounts = useMemo(() => discoverStageCounts(merged, labIds), [merged, labIds]);

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

  return (
    <PageShell
      title="Discover"
      lead="Find external datasets, check source fit, then add them to the lab"
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
      <DiscoverPipeline counts={stageCounts} searching={!!q && loading} />
      {!q ? (
        <DiscoverEmptyState onSuggest={onSuggestSearch} />
      ) : (
        <>
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
          <div className="rd-v2-discover-list-panel">
            <DiscoverCandidateList
              rows={filtered}
              labIds={labIds}
              selectedId={selectedId}
              onSelectRow={onSelectRow}
            />
          </div>
        </>
      )}
    </PageShell>
  );
}
