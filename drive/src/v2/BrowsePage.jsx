import { useEffect, useMemo, useState } from "react";
import { discoverCollectRoutes, discoverSearch, discoverSources, libraryPartitions, webDiscover } from "@/v2/api";
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
import {
  candidateSpecificityText,
  hasSpecificDiscoverRoute,
} from "@/v2/discoverQuerySpecificity";
import { Chip, PageShell, SourceRibbon } from "@/v2/ui";
import { groupCatalogueVariants } from "@/v2/catalogueVariants";

const FILTERS = [
  { id: "all", label: "All results" },
  { id: "in_lab", label: "In your Library" },
  { id: "query_ready", label: "Query ready" },
  { id: "external", label: "Beyond your Library" },
  { id: "needs_access", label: "Needs access" },
];

function plural(value, singular, pluralValue = `${singular}s`) {
  return `${value} ${value === 1 ? singular : pluralValue}`;
}

/** VC-5: first-use examples for the single adaptive composer. */
const DISCOVER_KEYWORD_EXAMPLE = "stablecoin";
const DISCOVER_QUESTION_EXAMPLE = "What data can I use to study de-pegs?";

function resultScopeSummary(counts) {
  const wider = Math.max(0, Number(counts?.external || 0) - Number(counts?.needsAccess || 0));
  return [
    counts?.inLab ? `${plural(counts.inLab, "result")} in your Library` : null,
    wider ? `${plural(wider, "source")} beyond your Library` : null,
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
  if (taxonomy?.key?.startsWith("local-")) return "Library dataset";
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
      return "In your Library · Query-ready declared";
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

function libraryFacingSufficiency(value) {
  return String(value || "")
    .replaceAll("Exact local match", "Exact Library match")
    .replaceAll("Partial local coverage", "Partial Library coverage")
    .replaceAll("Related lab asset", "Related Library asset")
    .replaceAll("No local alternative found", "No Library alternative found")
    .replaceAll("Local comparison unavailable", "Library comparison unavailable")
    .replaceAll("In lab", "In Library");
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
  return candidateSpecificityText(row);
}

function hasSpecificSourceRoute(rows, query) {
  return hasSpecificDiscoverRoute(rows || [], interpretEvidenceNeed(query).tokens);
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

function DiscoverCandidateRow({
  row,
  labIds,
  selectedId,
  onSelectRow,
  onAdd,
  externalCatalogue = false,
}) {
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
  const canAdd = !taxonomy.key.startsWith("local-")
    && !["Reference only", "Web context"].includes(offeringType(row, taxonomy))
    && typeof onAdd === "function";

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
          {/* Why this row answers the question that was asked -- the one thing
              the single-column CLI rendering had that this page did not. It is
              the reader's own sentence, so it argues relevance ("On-chain USDT
              transfer flows during peg stress events") where every other line
              on the row only describes the dataset. Placed above the
              description because it is the reason to keep reading. */}
          {row?.selection_reason ? (
            <span className="rd-v2-discover-why" data-testid="discover-why">
              <b>why</b> {row.selection_reason}
            </span>
          ) : null}
          {evidenceLine ? <span className="rd-v2-discover-evidence">{evidenceLine}</span> : null}
          {/* "Dataset · catalog_harvest" is the desk's own vocabulary and says
              nothing a researcher can act on. Keep the offering type only when
              it changes what you can do with the row (a reference or a
              connector is not a downloadable dataset), and lead with coverage,
              which is what the field shows. */}
          <span className="rd-v2-discover-offering-facts">
            {[
              ["Reference only", "Web context", "Connector"].includes(offeringType(row, taxonomy))
                ? offeringType(row, taxonomy)
                : null,
              showCoverage ? coverage : null,
              row?.refresh_frequency || row?.refresh || row?.update_frequency,
            ].filter(Boolean).join(" · ")}
          </span>
          {showSufficiency ? (
            <span
              className={`rd-v2-discover-sufficiency rd-v2-discover-sufficiency-${row.discover_sufficiency.state}`}
              data-testid="discover-sufficiency-line"
            >
              {libraryFacingSufficiency(row.discover_sufficiency.browseLine)}
            </span>
          ) : null}
        </span>
      </button>
      {canAdd ? (
        <button
          type="button"
          className="rd-v2-discover-row-add"
          onClick={(event) => {
            event.stopPropagation();
            onAdd(row);
          }}
        >
          Add to collection
        </button>
      ) : null}
    </li>
  );
}

export function isDiscoverResearchQuestion(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  if (text.includes("?")) return true;
  if (/^(what|which|where|when|why|how|can|could|should|would|do|does|is|are|i need|we need|help me|find me)\b/i.test(text)) {
    return true;
  }
  return text.split(/\s+/).length >= 8;
}

function DiscoverQueryComposer({
  value,
  onValueChange,
  onSearch,
  onAsk,
  onAssess,
  idle = false,
}) {
  const submit = (event) => {
    event.preventDefault();
    const next = String(value || "").trim();
    if (!next) return;
    onSearch?.(next);
    if (isDiscoverResearchQuestion(next)) {
      // Assessment is deliberately started before Ask so the visible rail lands
      // on the continuing conversation while the hidden Detail lens evaluates.
      onAssess?.(next);
      onAsk?.(next);
    }
  };
  return (
    <form
      className={`rd-v2-discover-composer${idle ? " is-idle" : ""}`}
      data-testid="discover-query-composer"
      onSubmit={submit}
    >
      <textarea
        value={value}
        onChange={(event) => onValueChange?.(event.target.value)}
        onKeyDown={handleEnterToRequestSubmit}
        rows={1}
        placeholder="Search datasets, or describe what data you need…"
        aria-label="Search or describe a research need"
      />
      <button type="submit" className="rd-v2-btn sm primary">
        Explore
      </button>
      {/* Teaching copy earns its space before the first search and not after.
          Once results are on screen it competes with them, and the researcher
          has already demonstrated they know how to run a query. */}
      <p hidden={!idle}>
        Keywords return fast results. A research question also starts a contextual Ask investigation automatically.
      </p>
      {/* VC-5: two compact examples teach the one-composer behaviour by
          demonstration. They are examples, not modes or tabs. */}
      {idle ? (
        <div className="rd-v2-discover-composer-examples" data-testid="discover-composer-examples">
          <button type="button" onClick={() => onValueChange?.(DISCOVER_KEYWORD_EXAMPLE)}>
            <span>Try a keyword</span>
            <em>{DISCOVER_KEYWORD_EXAMPLE}</em>
          </button>
          <button type="button" onClick={() => onValueChange?.(DISCOVER_QUESTION_EXAMPLE)}>
            <span>Ask a research need</span>
            <em>{DISCOVER_QUESTION_EXAMPLE}</em>
          </button>
        </div>
      ) : null}
    </form>
  );
}

function DiscoverRouteComparison({
  query,
  requirement,
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
  const readRequirement = (key, fallback = "Not yet specified") => {
    const item = requirement?.[key];
    const value = item?.value;
    if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
    return String(value || "").trim() || fallback;
  };
  const outputTitle = readRequirement("output_title", "Proposed research evidence dataset");
  const proposedUnit = readRequirement("unit");
  const proposedUniverse = readRequirement("universe/geography");
  const proposedPeriod = readRequirement("time_range");
  const proposedFields = readRequirement("fields");
  const recordedGap = String(
    gap?.blocks || gap?.statement || "the required evidence is not yet established",
  ).replace(/[.!?]+$/, "");
  const answerLine = [
    `Organizes ${proposedFields} at ${proposedUnit}`,
    proposedUniverse !== "Not yet specified" ? `for ${proposedUniverse}` : "",
    `to address the recorded gap: ${recordedGap}.`,
  ].filter(Boolean).join(" ");
  const nextAction = publicRoute
    ? {
        text: `Review the declared route for ${candidateTitle(publicRoute)} and verify coverage before approval.`,
        label: "Review acquisition route",
        run: () => onReviewAcquisition?.(publicRoute),
      }
    : accessRoute
      ? {
          text: `Review entitlement and permitted coverage for ${candidateTitle(accessRoute)} before choosing a route.`,
          label: "Review access route",
          run: () => onReviewAcquisition?.(accessRoute),
        }
      : {
          text: "Clarify the missing source and coverage constraints in Ask before recording implementation work.",
          label: "Refine in Ask",
          run: () => onAsk?.(
            `Refine a custom dataset strategy for: ${query}. The current gap is: ${gap?.statement || "not fully specified"}. Ask for the missing source and coverage constraints. Do not submit procurement.`,
          ),
        };
  const inputCards = [
    held ? {
      label: "Library evidence",
      title: candidateTitle(held),
      state: "Observed in Library",
      action: () => onSelectRow?.(held),
    } : {
      label: "Library evidence",
      title: "No Library input established",
      state: "Unknown",
    },
    publicRoute ? {
      label: "Source route",
      title: candidateTitle(publicRoute),
      state: publicRoute?.probe_snapshot?.observed_at ? "Probe observed" : "Route declared · verify",
      action: () => onReviewAcquisition?.(publicRoute),
    } : accessRoute ? {
      label: "Access route",
      title: candidateTitle(accessRoute),
      state: "Entitlement must be verified",
      action: () => onReviewAcquisition?.(accessRoute),
    } : {
      label: "Source route",
      title: "No supported route established",
      state: "Needs investigation",
    },
    {
      label: "Identity + coverage",
      title: proposedUniverse === "Not yet specified"
        ? "Identity and coverage contract"
        : `Coverage map · ${proposedUniverse}`,
      state: "Proposed · must verify",
    },
  ];

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
            <span className="rd-v2-eyebrow">Custom dataset strategy · proposed</span>
            <h3>{outputTitle}</h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Close acquisition strategy">Close</button>
        </header>
        <p className="rd-v2-discover-route-intro">
          {gap?.statement || "The standard sourcing path does not yet establish every part of this evidence need."}
        </p>
        <section className="rd-v2-discover-strategy-answer">
          <span>How it answers the question</span>
          <p>{answerLine}</p>
        </section>
        <div className="rd-v2-discover-strategy-flow" aria-label="Proposed dataset strategy">
          <div className="rd-v2-discover-strategy-inputs">
            {inputCards.map((input) => (
              <button
                key={input.label}
                type="button"
                disabled={!input.action}
                onClick={input.action}
              >
                <span>{input.label}</span>
                <strong>{input.title}</strong>
                <em>{input.state}</em>
              </button>
            ))}
          </div>
          <div className="rd-v2-discover-strategy-arrow" aria-hidden="true">→</div>
          <div className="rd-v2-discover-strategy-process">
            <span>Proposed transform</span>
            <strong>Collect · normalize · reconcile</strong>
            <em>Implementation and source terms remain unverified</em>
          </div>
          <div className="rd-v2-discover-strategy-arrow" aria-hidden="true">→</div>
          <div className="rd-v2-discover-strategy-output">
            <span>Planned output</span>
            <strong>{outputTitle}</strong>
            <dl>
              <div><dt>Unit</dt><dd>{proposedUnit}</dd></div>
              <div><dt>Universe</dt><dd>{proposedUniverse}</dd></div>
              <div><dt>Period</dt><dd>{proposedPeriod}</dd></div>
              <div><dt>Fields</dt><dd>{proposedFields}</dd></div>
            </dl>
            <em>Register only after archive and query-readiness verification</em>
          </div>
        </div>
        <div className="rd-v2-discover-strategy-truth">
          <span><b>Observed</b> only states shown on source records</span>
          <span><b>Proposed</b> output contract and transformation</span>
          <span><b>Unknown</b> cost, completion time, full coverage, and feasibility</span>
        </div>
        <section className="rd-v2-discover-strategy-next">
          <div>
            <span>Next valid action</span>
            <p>{nextAction.text}</p>
          </div>
          <button type="button" onClick={nextAction.run}>{nextAction.label} →</button>
        </section>
        <footer>
          <p>This preview cannot submit procurement or promise delivery.</p>
          <button type="button" onClick={() => onAsk?.(
            `Refine a custom dataset strategy for: ${query}. The current gap is: ${gap?.statement || "not fully specified"}. Ask for the missing context and keep observed facts, proposals, and unknowns separate. Do not submit procurement.`,
          )}>
            Refine in Ask →
          </button>
          {!publicRoute && !accessRoute && onSearchWider ? (
            <button type="button" onClick={onSearchWider}>Search wider →</button>
          ) : null}
        </footer>
      </section>
    </div>
  );
}

const LIBRARY_PAGE = 7;

/**
 * Held datasets as a dense, scannable list — the approved layout's hero.
 *
 * These rows were previously buried in a collapsed "Library evidence" dropdown
 * capped at four entries, so a query matching thirty held datasets showed four
 * of them behind a disclosure triangle while external routes took the page.
 * That inverted the thing a research desk is for: what you already hold is the
 * first answer, and external collection is the fallback.
 *
 * One line per dataset, columns aligned, because at twenty to a hundred results
 * a card is the wrong primitive — six cards fill the fold and nothing can be
 * compared across rows.
 */
function LibraryResultList({ rows, labIds, selectedId, onSelectRow }) {
  const [expanded, setExpanded] = useState(false);
  const [openKey, setOpenKey] = useState("");
  const shown = expanded ? rows : rows.slice(0, LIBRARY_PAGE);
  const rest = rows.length - shown.length;
  return (
    <>
      <ul className="rd-v2-library-rows" aria-label="Datasets in your Library">
        {shown.map((row) => {
          const key = candidateKey(row);
          const ready = Boolean(row.local_ready);
          const geo = Number(row.geography_count || 0);
          const open = openKey === key;
            return (
            <li key={key} className={selectedId === key ? "rd-v2-row-on" : undefined}>
              <button
                type="button"
                className="rd-v2-library-row"
                aria-expanded={open}
                onClick={() => {
                  setOpenKey(open ? "" : key);
                  onSelectRow?.(row);
                }}
              >
                {/* Title first, metadata as a byline beneath -- the row shape
                    every dataset search converges on, because a reader scans
                    names and only then checks whether the grain and period fit.
                    A fixed column grid forced empty cells: time_range and
                    geography are undeclared on most rows, so two of five
                    columns rendered "—" on every line. A byline simply omits
                    what is not known. */}
                <span className={`rd-v2-library-mark${ready ? " on" : ""}`} aria-hidden="true">
                  {ready ? "✓" : "○"}
                </span>
                <span className="rd-v2-library-main">
                  <span className="rd-v2-library-title">
                    {row.display_name || row.title || row.dataset_id}
                  </span>
                  {row.one_line ? (
                    <span className="rd-v2-library-snippet">{row.one_line}</span>
                  ) : null}
                  <span className="rd-v2-library-byline">
                    {[
                      ready ? "query-ready" : "not query-ready",
                      row.time_range,
                      geo ? `${geo} countries` : null,
                      row._variants?.length > 1 ? `${row._variants.length} scales` : null,
                      (row.tags || []).slice(0, 3).join(" · ") || null,
                      row.probed_at ? `checked ${String(row.probed_at).slice(0, 10)}` : null,
                    ].filter(Boolean).join("  ·  ")}
                  </span>
                </span>
                <span className="rd-v2-library-chev" aria-hidden="true">▸</span>
              </button>
              {open ? (
                <span className="rd-v2-library-detail">
                  {row.selection_reason ? (
                    <span className="rd-v2-discover-why">
                      <b>why</b> {row.selection_reason}
                    </span>
                  ) : null}
                  {/* The id belongs here, not in the headline: it is what you
                      copy into a query, needed once you have chosen the row. */}
                  <code className="rd-v2-library-idcode">{row.dataset_id}</code>
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {rest > 0 ? (
        <button type="button" className="rd-v2-btn sm rd-v2-library-more" onClick={() => setExpanded(true)}>
          … {rest} more — Show all
        </button>
      ) : null}
    </>
  );
}

function DiscoverCandidateList({
  rows,
  labIds,
  selectedId,
  onSelectRow,
  onAdd,
  externalCatalogue = false,
}) {
  return (
    <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Discover candidates">
      {rows.map((row) => (
        <DiscoverCandidateRow
          key={candidateKey(row) || candidateTitle(row)}
          row={row}
          labIds={labIds}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
          onAdd={onAdd}
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
  const [loadedQuery, setLoadedQuery] = useState("");
  const [enrichedQuestion, setEnrichedQuestion] = useState("");

  const pendingRows = useMemo(
    () => pendingApprovalJobs(jobs).map((job) => jobToCandidateRow(job)).filter(Boolean),
    [jobs],
  );
  const isExplore = discoverMode === "explore" || discoverMode === "search";
  const showHistory = discoverMode === "history";

  useEffect(() => {
    setQueryDraft(searchQuery || "");
    setRouteComparisonOpen(false);
    setEnrichedQuestion("");
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
    setLoadedQuery("");

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
          try {
            const knownSources = await discoverSources("", {
              limit: 8,
              semantic: false,
              live: false,
            });
            apply({ results: sourcesResponseToRows(knownSources) }, "known_sources");
          } catch {
            setRows([]);
            setSource("");
            setDemoFallback(false);
          }
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
        // Two tempos, deliberately separated. A plain keyword lookup consults the
        // local holding index and the known-source route index in parallel. Neither
        // call fans out to remote providers. Semantic hybrid search and live
        // external adapters remain an explicit "Search wider" escalation.
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
        const [discoverResult, knownSourcesResult] = await Promise.allSettled([
          discoverSearch(q, 12, email),
          discoverSources(q, { limit: 8, semantic: false, live: false }),
        ]);
        if (discoverResult.status === "rejected" && knownSourcesResult.status === "rejected") {
          throw discoverResult.reason;
        }
        const discover = discoverResult.status === "fulfilled" ? discoverResult.value : {};
        const discoverRows = flattenRows(discover);
        const knownSourceRows =
          knownSourcesResult.status === "fulfilled"
            ? sourcesResponseToRows(knownSourcesResult.value)
            : [];
        let mergedRows = dedupeRows([...knownSourceRows, ...discoverRows]);
        let label = mergedRows.length ? "index" : "";
        let miss = Boolean(discover.index_miss || discover.weak_match) && discoverRows.length === 0;

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

        // No demo fallback here. This branch means the desk answered and
        // answered "nothing" -- which is a true, useful answer for a
        // procurement tool, and the one the gap-to-route flow is built on.
        //
        // Filling it with demo fixtures fabricated results: "US polling data"
        // returned "Global ocean temperature anomaly" because discoverDemoSearch
        // matches any token over two characters, and every sample's text
        // contains "data". It was then labelled "Partial Library coverage" and
        // setIndexMiss(false) suppressed the honest miss that would have
        // triggered the route offer. The catch branch below still seeds demo
        // rows when the API is genuinely unreachable, and flags them as such.
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
        setLoadedQuery(q);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [searchQuery, discoverMode, labIds, preferLiveSources, onLiveSourcesConsumed, externalSearchQuery]);

  useEffect(() => {
    const q = String(searchQuery || "").trim();
    if (
      !isExplore
      || !q
      || loadedQuery !== q
      || preferLiveSources
      || externalSearchQuery === q
      || !isDiscoverResearchQuestion(q)
      || enrichedQuestion === q
    ) return undefined;

    let cancelled = false;
    setEnrichedQuestion(q);
    const enrich = async () => {
      let extra = [];
      try {
        const sources = await discoverSources(q, { limit: 12, semantic: true, live: true });
        extra = sourcesResponseToRows(sources);
      } catch {
        // The first result paint remains valid when optional enrichment is unavailable.
      }
      if (!extra.length || !hasSpecificSourceRoute(extra, q)) {
        try {
          const web = await webDiscover(q, 8);
          extra = dedupeRows([...extra, ...rankExternalCatalogueRows(webHitsToRows(web), q)]);
        } catch {
          // Web context is optional and must never erase already-rendered evidence.
        }
      }
      if (cancelled || !extra.length) return;
      setRows((current) => dedupeRows([...current, ...extra]));
      setSource((current) => current ? `${current}+progressive` : "progressive");
      setIndexMiss(false);
    };
    enrich();
    return () => {
      cancelled = true;
    };
  }, [
    searchQuery,
    isExplore,
    loadedQuery,
    preferLiveSources,
    externalSearchQuery,
    enrichedQuestion,
  ]);

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
      duplicates: 0,
    };
    for (const row of filtered) {
      // An external row whose sufficiency is "exact local match" is a second
      // listing of a dataset already shown under IN YOUR LIBRARY. Seven
      // "external" results for a stablecoin query contained four such
      // duplicates, so the section that is supposed to show what the desk does
      // NOT hold was mostly re-showing what it does. Counted, not silently
      // dropped, so the total still reconciles.
      if (row.discover_sufficiency?.state === "exact-local") {
        groups.duplicates += 1;
        continue;
      }
      const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
      const type = offeringType(row, taxonomy);
      if (taxonomy.key.startsWith("local-")) groups.held.push(row);
      else if (type === "Reference only" || type === "Web context") groups.context.push(row);
      else if (["external-acquirable", "external-probed"].includes(taxonomy.key)) groups.available.push(row);
      else groups.external.push(row);
    }
    return groups;
  }, [filtered, labIds]);
  const readyCount = useMemo(
    () => resultGroups.held.filter((r) => r.local_ready).length,
    [resultGroups.held],
  );
  const resultBreakdown = useMemo(
    () => [
      resultGroups.available.length
        ? `${plural(resultGroups.available.length, "offering")} available to add`
        : null,
      resultGroups.external.length
        ? `${plural(resultGroups.external.length, "route")} to verify`
        : null,
      resultGroups.context.length
        ? plural(resultGroups.context.length, "reference")
        : null,
      resultGroups.held.length
        ? `${plural(resultGroups.held.length, "result")} in your Library`
        : null,
    ].filter(Boolean).join(" · "),
    [resultGroups],
  );

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
  const strategyNeedsContext = ["insufficient_metadata", "insufficient_requirement", "cannot_assess"].includes(
    assessmentStatus,
  );
  const assessmentPending = Boolean(assessmentActive && !assessmentResult);
  const idleHoldings = useMemo(
    () => catalog.filter((row) => labIds.has(row.dataset_id || row.id)).slice(0, 4).map((row) => ({
      ...row,
      discover_taxonomy: classifyDiscoverResult(row, labIds),
    })),
    [catalog, labIds],
  );
  const idleRecommendations = useMemo(
    () => merged
      .filter((row) => !(row.discover_taxonomy || classifyDiscoverResult(row, labIds)).key.startsWith("local-"))
      .filter((row) => String(row.result_type || row.kind || "").toLowerCase() !== "connector")
      .slice(0, 4),
    [merged, labIds],
  );

  // The desk's declared collection routes, loaded independently of the query.
  //
  // idleRecommendations derives from `merged`, the search result set, so it is
  // empty exactly when a search misses -- which is the moment the routes are
  // worth showing. Fetching the unfiltered source list separately means a miss
  // can still answer "we don't hold this, here is what we can collect from".
  //
  // Listing the desk's standing routes here was wrong: asked for US opinion
  // polling, it offered CRSP MOVEit, a daily market-price archive. Calling it
  // "not matched to your query" made that honest without making it useful.
  // This asks which sources could actually supply the request and shows
  // nothing when none can, because "this desk cannot get that" is the answer
  // a procurement tool owes.
  // Openable content on the landing, the way Kaggle and HuggingFace show
  // trending datasets. An empty search box with no starting point forces the
  // researcher to already know what the desk holds, which is exactly what they
  // came here to find out.
  const [shelves, setShelves] = useState([]);
  useEffect(() => {
    let cancelled = false;
    libraryPartitions()
      .then((res) => {
        if (cancelled) return;
        const rows = (res?.shelves || [])
          .filter((sh) => (sh.dataset_count || 0) > 0)
          .sort((a, b) => (b.query_ready_count || 0) - (a.query_ready_count || 0));
        setShelves(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const [missRouteState, setMissRouteState] = useState({ query: "", routes: [], reason: "" });
  useEffect(() => {
    const wanted = String(q || "").trim();
    if (!wanted || loading || error || filtered.length > 0) return undefined;
    let cancelled = false;
    setMissRouteState({ query: wanted, routes: [], reason: "loading" });
    discoverCollectRoutes(wanted)
      .then((res) => {
        if (!cancelled) {
          setMissRouteState({
            query: wanted,
            routes: Array.isArray(res?.routes) ? res.routes : [],
            reason: String(res?.reason || ""),
          });
        }
      })
      .catch(() => {
        if (!cancelled) setMissRouteState({ query: wanted, routes: [], reason: "unavailable" });
      });
    return () => {
      cancelled = true;
    };
  }, [q, loading, error, filtered.length]);

  const missRoutes = missRouteState.query === String(q || "").trim() ? missRouteState.routes : [];
  const missRouteReason = missRouteState.query === String(q || "").trim() ? missRouteState.reason : "";

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

  const libraryEvidenceMenu = resultGroups.held.length ? (
    <details className="rd-v2-discover-library-evidence" data-testid="discover-library-evidence">
      <summary>Library evidence · {resultGroups.held.length}</summary>
      <div className="rd-v2-discover-library-popover">
        <span className="rd-v2-eyebrow">Relevant Library evidence</span>
        <DiscoverCandidateList
          rows={resultGroups.held.slice(0, 4)}
          labIds={labIds}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
        />
      </div>
    </details>
  ) : null;

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
      lead="Search your Library first, then evaluate sources beyond it"
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
              onAssess={onOpenAssessment}
              idle
            />
            {shelves.length ? (
              <div className="rd-v2-discover-shelves" aria-label="Browse the Library">
                <div className="rd-v2-discover-shelves-head">
                  <span className="rd-v2-eyebrow">Browse what the desk holds</span>
                </div>
                <ul>
                  {shelves.map((sh) => (
                    <li key={sh.id}>
                      <a className="rd-v2-shelf-chip" href={`?tab=library&folder=${encodeURIComponent(sh.id)}`}>
                        <span className="rd-v2-shelf-label">{sh.label}</span>
                        <span className="rd-v2-shelf-count">
                          {sh.dataset_count}
                          {sh.query_ready_count ? ` · ${sh.query_ready_count} ready` : ""}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="rd-v2-discover-idle-held">
              {/* VC-5: with no known routes this collapses to one quiet line
                  instead of an oversized empty section. */}
              {/* These are sources, not results, and they sat above the fold as
                  four full cards before the researcher had asked for anything.
                  "OpenAlex — Add to collection" is not an action anyone can
                  take: add what from OpenAlex? They also wore dataset labels
                  ("Access not verified", "Related Library asset") that mean
                  nothing about a connector.

                  A search landing shows the box and, at most, openable content
                  — which is what Kaggle and HuggingFace put here. Until this
                  can show real holdings, the honest version is one quiet line
                  naming what the desk can reach, opened on demand. */}
              {idleRecommendations.length ? (
                <details className="rd-v2-discover-routes-disclosure">
                  <summary>
                    <span className="muted">
                      {plural(merged.length, "source")} this desk can collect from
                    </span>
                  </summary>
                  <DiscoverCandidateList
                    rows={idleRecommendations}
                    labIds={labIds}
                    selectedId={selectedId}
                    onSelectRow={onSelectRow}
                    onAdd={onReviewAcquisition}
                  />
                </details>
              ) : null}
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
                  onAssess={onOpenAssessment}
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
              {/* On a miss this row said "0 results · index lookup" and offered
                  "Search wider" -- both of which the miss block below states
                  more clearly, next to the routes that actually help. Three
                  restatements of "nothing found" (here, the miss line, and the
                  rail's "No candidate selected") made the page feel like it was
                  apologising rather than answering. Keep the count where it is
                  informative: when there are results to count. */}
              {/* Conditional render, not the hidden attribute: this element is
                  display:flex, which beats the UA stylesheet's [hidden] rule,
                  so the row stayed on screen while claiming to be hidden. */}
              {/* The verdict line above the Library list already states held,
                  external and query-ready counts. Keeping this row as well
                  stated the same totals twice before the first result. It
                  survives only when there is no Library section to carry
                  them. */}
              {loading || error || (filtered.length > 0 && !resultGroups.held.length) ? (
              <div
                className="rd-v2-discover-result-actions"
                aria-label="Discover next actions"
              >
                <div>
                  <strong>{plural(filtered.length, "result")}</strong>
                  <span>
                    {resultBreakdown || (preferLiveSources || source === "sources" || externalCatalogueActive
                      ? "wider discovery"
                      : "index lookup")}
                  </span>
                </div>
                <div>
                  {onSearchWeb ? (
                    <button type="button" onClick={() => onSearchWeb(q)}>
                      Search wider
                    </button>
                  ) : null}
                  {assessmentPending ? (
                    <button type="button" className="rd-v2-discover-strategy-trigger is-pending" disabled>
                      Assessing strategy…
                    </button>
                  ) : strategyNeedsContext ? (
                    <button
                      type="button"
                      className="rd-v2-discover-strategy-trigger"
                      onClick={() => onAskQuery?.(
                        q,
                        {
                          kind: "strategy_context",
                          rows: merged,
                          prompt: `Clarify the evidence requirement for: ${q}. Ask only for the missing context needed to judge coverage and prepare a custom dataset strategy. Do not submit procurement.`,
                        },
                      )}
                    >
                      Strategy needs context
                    </button>
                  ) : hasEvidenceGap ? (
                    <button
                      type="button"
                      className="rd-v2-discover-strategy-trigger is-ready"
                      onClick={() => setRouteComparisonOpen(true)}
                    >
                      Custom strategy ready
                    </button>
                  ) : null}
                </div>
              </div>
              ) : null}
            </section>

            {resultGroups.held.length ? (
              <section className="rd-v2-discover-library" aria-label="In your Library">
                {/* Collapsed by default: the held list is reference material the
                    researcher opens when they want it, and leaving it expanded
                    pushed everything else below the fold. */}
                {/* Verdict first: one line stating where the answer stands,
                    before any list. The page used to open with a filter bar and
                    a count, so the researcher had to assemble the verdict from
                    fragments scattered across three regions. */}
                <details className="rd-v2-library-disclosure">
                <summary className="rd-v2-discover-verdict">
                  <span className="rd-v2-eyebrow">In your Library</span>
                  <strong>
                    {plural(resultGroups.held.length, "dataset")} held
                  </strong>
                  {resultGroups.available.length || resultGroups.external.length
                    ? ` · ${resultGroups.available.length + resultGroups.external.length} external`
                    : ""}
                  {readyCount ? ` · ${readyCount} query-ready now` : ""}
                </summary>
                <LibraryResultList
                  rows={groupCatalogueVariants(resultGroups.held)}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                />
                </details>
              </section>
            ) : null}

            {/* Every external candidate had a Library equivalent, so the
                external sections rendered nothing and the page simply stopped
                after the held list -- indistinguishable from a broken search.
                Removing a duplicate is the right call; going quiet about it is
                not, because "you already hold all of these" is the answer. */}
            {!resultGroups.available.length && !resultGroups.external.length && resultGroups.duplicates ? (
              <p className="muted rd-v2-discover-all-held">
                {plural(resultGroups.duplicates, "external match")} found — all already in your Library.
              </p>
            ) : null}

            {resultGroups.available.length ? (
              <section className="rd-v2-discover-best-fit" aria-label="Available to add" data-testid="discover-best-fit">
                {/* VC-5: the result header already states the offering count;
                    repeating it beside an identical heading is noise. */}
                <div className="rd-v2-home-section-head">
                  <div>
                    <span className="rd-v2-eyebrow">Beyond your Library</span>
                    <h3>Available to add</h3>
                  </div>
                </div>
                <DiscoverCandidateList
                  rows={groupCatalogueVariants(resultGroups.available)}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  onAdd={onReviewAcquisition}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
            ) : null}

            {hasEvidenceGap && routeComparisonOpen ? (
              <DiscoverRouteComparison
                query={q}
                requirement={assessmentResult.requirement}
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
              <p className="rd-v2-browse-loading">Searching your Library and wider sources…</p>
            ) : null}

            {!loading && allInLab ? (
              <div className="rd-v2-discover-expand-search">
                <div>
                  <strong>Every current match is already in your Library.</strong>
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
                  <strong>No current source route specifically matches “{q}”.</strong>
                  <p>The routes below are known to the desk, but they are not evidence results for this question.</p>
                </div>
                <button type="button" className="rd-v2-btn sm" onClick={() => setExternalSearchQuery(q)}>
                  Search external catalogues
                </button>
              </section>
            ) : null}

            {!loading && !error && filtered.length === 0 ? (
              <div className="rd-v2-discover-miss">
                <p className="rd-v2-empty-inline">
                  The desk holds no {stateFilter === "all" ? "" : `${activeFilter.label.toLowerCase()} `}match for “{q}”
                  {indexMiss ? " in the current research index." : "."}
                </p>
                {indexMiss && onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search wider sources →
                  </button>
                ) : null}
                {/* "Nothing found" is where a procurement desk earns its keep:
                    not holding the data is the normal case, and the useful
                    answer is which routes could get it. These are the same
                    declared source routes the idle screen offers, so the miss
                    stops being a dead end without inventing a new surface. */}
                {missRoutes.length ? (
                  <div className="rd-v2-discover-miss-routes">
                    <div className="rd-v2-home-section-head">
                      <div>
                        <span className="rd-v2-eyebrow">Not held — routes to get it</span>
                        <h3>Sources that could supply this</h3>
                      </div>
                      <span className="muted">{plural(missRoutes.length, "route")}</span>
                    </div>
                    <ul className="rd-v2-catalog rd-v2-miss-route-list">
                      {missRoutes.map((route) => (
                        <li key={route.source_id}>
                          <div className="rd-v2-miss-route">
                            <div>
                              <strong>{route.label || route.source_id}</strong>
                              {route.provider ? <span className="muted"> · {route.provider}</span> : null}
                              <span className="rd-v2-discover-why">
                                <b>why</b> {route.reason}
                              </span>
                            </div>
                            <button
                              type="button"
                              className="rd-v2-btn sm"
                              onClick={() => onAskQuery?.(
                                `Collect ${route.label || route.source_id} for: ${q}`,
                                { kind: "investigation" },
                              )}
                            >
                              {route.action === "collect" ? "Start collection" : "Request access"}
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : missRouteReason === "loading" ? (
                  <p className="muted rd-v2-discover-no-route">Checking which sources could supply this…</p>
                ) : missRouteReason === "no_route_found" ? (
                  /* Saying so is the answer. Four irrelevant offers -- the desk
                     proposing a market-price archive for opinion polling -- is
                     worse than admitting the desk has no route, because the
                     researcher has to work that out for themselves. */
                  <p className="muted rd-v2-discover-no-route">
                    No source on this desk carries this kind of data. Paste a URL or DOI below to
                    have it assessed for collection.
                  </p>
                ) : missRouteReason === "unavailable" || String(missRouteReason).startsWith("backend_unavailable") ? (
                  <p className="muted rd-v2-discover-no-route">
                    Could not check collection routes right now. Try again, or paste a URL or DOI below.
                  </p>
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
                  rows={groupCatalogueVariants(resultGroups.external)}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  onAdd={onReviewAcquisition}
                  externalCatalogue={externalCatalogueActive}
                />
              </section>
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
                <span className="muted">
                  {externalCatalogueActive
                    ? "Ordered by title and description match to this question"
                    : `Ranked using active research + interpreted evidence need${stateFilter !== "all" ? ` · ${activeFilter.label}` : ""}`}
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
      {intentRecord ? (
        <div
          className="rd-v2-discover-intent-scrim"
          role="dialog"
          aria-modal="true"
          aria-label="Review acquisition"
          onMouseDown={(event) => event.target === event.currentTarget && onCloseIntent?.()}
        >
          <div className="rd-v2-discover-intent-modal">
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
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}
