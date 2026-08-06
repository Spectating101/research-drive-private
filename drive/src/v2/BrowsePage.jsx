import { useEffect, useMemo, useState } from "react";
import { discoverCollectRoutes, discoverSearch, discoverSources, libraryPartitions, webDiscover } from "@/v2/api";
import { sourcesResponseToRows } from "@/v2/discoverAdapters";
import { DiscoverHistoryPanel } from "@/v2/DiscoverHistoryPanel";
import { jobToCandidateRow, pendingApprovalJobs } from "@/v2/procurementJobs";
import {
  classifyDiscoverResult,
  coverageLine,
  routeDisplayName,
  descriptiveLine,
  discoverCandidateState,
  exceptionalRowPill,
  humanizeDiscoverDescription,
  orderDiscoverResults,
  taxonomyMatchesFilter,
  taxonomyStageCounts,
} from "@/v2/browseMeta";
import { isHeldRow, readinessMark } from "@/v2/readinessMark";
import { discoverCandidateUrl, webHitsToRows } from "@/v2/discoverActions";
import { candidateKey, isCandidateQueued, withCandidateKey } from "@/v2/candidateKey";
import { buildDiscoverLifecycle, projectDiscoverCandidateLifecycle } from "@/v2/discoverLifecycle";
import {
  interpretEvidenceNeed,
} from "@/v2/discoverComposition";
import {
  evidencePlacement,
  evidenceWhy,
  isMaterialLibraryRelation,
  PLACEMENT,
  placementLabel,
} from "@/v2/evidencePlacement";
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

/** The declared collection route, named.
 *
 * Every acquirable offering said "Collection route declared", so the phrase
 * repeated down the whole list and distinguished nothing -- the generic
 * per-source string the adaptive freeze §13 tells us not to reintroduce.
 * `collect_via` already records which route, so name it. Only the rendering
 * changes; the claim ("a route is declared") is the same one. */
function routeLabel(row) {
  const raw = Array.isArray(row?.collect_via) ? row.collect_via[0] : row?.collect_via;
  const named = routeDisplayName(raw);
  return named ? `Collect via ${named}` : "Collection route declared";
}

/** Bytes on disk, in the units a reader thinks in.
 *
 * Measured by dataset_scale_probe, never estimated. A row with no measurement
 * renders no scale cell at all rather than a zero or a guess -- an unreachable
 * or shared path is an absence of knowledge, not a size of nothing. */
function formatSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = n / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function accessLabel(taxonomy, row, labIds) {
  const placement = evidencePlacement(row, labIds);
  if (placement === PLACEMENT.HELD) {
    if (taxonomy?.key === "local-query-ready") return "In Library · Query-ready";
    return placementLabel(PLACEMENT.HELD);
  }
  switch (taxonomy?.key) {
    case "external-discoverable":
      return "Access not verified";
    case "external-probed":
      return "Probe observed";
    case "external-acquirable":
      return routeLabel(row);
    case "external-unavailable":
      return "No supported route";
    case "licensed-manual":
      return "Access review required";
    default:
      return placementLabel(placement) || taxonomy?.label || "";
  }
}

function libraryFacingSufficiency(value) {
  // Never surface "no alternative" / comparison-unknown scaffolding — those
  // were FE-invented judgments without a backend contract.
  const raw = String(value || "");
  if (/no local alternative|no library alternative|comparison unavailable/i.test(raw)) {
    return "";
  }
  return raw
    .replaceAll("Exact local match", "Exact Library match")
    .replaceAll("Partial local coverage", "Partial Library coverage")
    .replaceAll("Related lab asset", "Related Library asset")
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
  const taxonomyLine = accessLabel(taxonomy, row, labIds);
  const exceptionPill = exceptionalRowPill(row, taxonomy, state);
  const whyLine = evidenceWhy(row);
  const materialSufficiencyLine = libraryFacingSufficiency(row.discover_sufficiency?.browseLine);
  const showSufficiency =
    !externalCatalogue
    && Number(taxonomy.group) >= 3
    && isMaterialLibraryRelation(row.discover_sufficiency?.state)
    && Boolean(materialSufficiencyLine);
  // States that mean the lab already holds something relevant, so collecting
  // may be unnecessary. These get a highlighted line; the rest stay inline.
  const readinessBadge = readinessMark(row);
  const recommendedUse = String(row?.recommended_use || "").trim().slice(0, 150);

  const hasExplicitDescription = Boolean(
    String(row?.description || row?.one_line || row?.recommended_use || row?.subtitle || "").trim(),
  );
  const evidenceLine = hasExplicitDescription ? humanizeDiscoverDescription(descriptiveLine(row)) : "";
  const coverage = coverageLine(row);
  const showCoverage = coverage && coverage !== "Coverage not described";
  const canAdd = evidencePlacement(row, labIds) !== PLACEMENT.HELD
    && !taxonomy.key.startsWith("local-")
    && !["Reference only", "Web context"].includes(offeringType(row, taxonomy))
    && typeof onAdd === "function";

  return (
    <li className={selected ? "rd-v2-row-on" : undefined}>
      <button
        type="button"
        className={`row rd-v2-discover-candidate${selected ? " selected" : ""}${exceptionPill ? " has-exception" : ""}`}
        data-kind={taxonomy.key}
        data-placement={evidencePlacement(row, labIds)}
        data-state={state.key}
        data-sufficiency={showSufficiency ? row.discover_sufficiency.state : undefined}
        aria-pressed={selected}
        onClick={() => onSelectRow(row)}
      >
        <span className="rd-v2-discover-candidate-main">
          <span className="rd-v2-discover-candidate-heading">
            <SourceRibbon source={ribbonSource} />
            <strong className="rd-v2-discover-candidate-title">
              {selected || isHeldRow(row, labIds) ? (
                <span
                  className={`rd-v2-discover-selected-mark${
                    isHeldRow(row, labIds) ? " is-held" : ""
                  }`}
                  aria-hidden="true"
                >
                  ▌
                </span>
              ) : null}
              {candidateTitle(row)}
            </strong>
            {exceptionPill ? (
              <span className={`rd-v2-pill ${exceptionPill.className}`}>{exceptionPill.label}</span>
            ) : null}
            {readinessBadge ? (
              <em className={`rd-v2-discover-readiness is-${readinessBadge.tone}`}>
                {readinessBadge.label}
              </em>
            ) : null}
          </span>
          {/* Backend why only — catalog reader / author sentence. Never canned
              semantic wallpaper ("matched on meaning, not wording"). */}
          {whyLine ? (
            <span className="rd-v2-discover-why" data-testid="discover-why">
              <b>why</b> {whyLine}
            </span>
          ) : null}
          {/* Every offering states what it contains (adaptive freeze §3, §12).
              When the source map records no capability we say so rather than
              rendering a blank line -- UI_PRODUCT_AUTHORITY §15 gives
              "Description not recorded" as the authority-backed fallback. */}
          <span className={`rd-v2-discover-evidence${evidenceLine ? "" : " is-missing"}`}>
            {evidenceLine || "Description not recorded"}
          </span>
          {/* "Dataset · catalog_harvest" is the desk's own vocabulary and says
              nothing a researcher can act on. Keep the offering type only when
              it changes what you can do with the row (a reference or a
              connector is not a downloadable dataset), and lead with coverage,
              which is what the field shows. */}
          {/* Adaptive freeze §3 row grammar: one facts line carrying
              type · coverage · access/route state · local relationship.
              The route state used to float right in green on every row
              ("Collection route declared" three times over), and the local
              relationship occupied a third line behind a "LIBRARY COMPARISON"
              label. Neither is a heading; both are facts about this offering. */}
          <span className="rd-v2-discover-offering-facts">
            {[
              ["Reference only", "Web context", "Connector"].includes(offeringType(row, taxonomy))
                ? offeringType(row, taxonomy)
                : null,
              showCoverage ? coverage : null,
              row?.refresh_frequency || row?.refresh || row?.update_frequency,
              taxonomyLine,
            ].filter(Boolean).join(" · ")}
          </span>
          {/* Only material Library relationships (exact/partial/related). Never
              invent "No Library alternative" — that was FE scaffolding. */}
          {showSufficiency ? (
            <span
              className={`rd-v2-discover-sufficiency rd-v2-discover-sufficiency-${row.discover_sufficiency.state}`}
              data-testid="discover-sufficiency-line"
            >
              {materialSufficiencyLine}
            </span>
          ) : null}
        </span>
        {/* Scale column. How much of it there is -- the thing every comparable
            product shows and this list did not, so a 412-byte probe snapshot
            and a 181MB panel looked identical. Rendered only when measured. */}
        <span className="rd-v2-discover-candidate-scale">
          {formatSize(row?.size_bytes) ? (
            <>
              <b>{formatSize(row.size_bytes)}</b>
              {row?.file_count > 1 ? <i>{row.file_count} files</i> : null}
              {row?.size_partial ? <i>partial scan</i> : null}
            </>
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
 * Dense held-dataset list for the Library evidence chrome popover.
 *
 * Adaptive freeze (2026-07-28): held evidence is compact chrome, not the
 * permanent centre canvas. External Available offerings stay primary; this
 * list is the bounded popover preview behind `Library evidence · N`.
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
                  {evidenceWhy(row) ? (
                    <span className="rd-v2-discover-why">
                      <b>why</b> {evidenceWhy(row)}
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

/**
 * The initial result budget.
 *
 * Rendering 20 ranked offerings as one unbroken column gave the researcher no
 * sense of how much was below the fold and no way to act on it -- the same
 * failure UI_IMPLEMENTATION_PROGRAM forbids for History: "Initial lifecycle
 * viewport budget is 8-12 rows with explicit `Load more`; do not recreate an
 * endless activity feed through infinite scrolling." The results list gets the
 * same discipline, so the count is stated and expanding is a deliberate act.
 */
const RESULT_BUDGET = 8;

function DiscoverCandidateList({
  rows,
  labIds,
  selectedId,
  onSelectRow,
  onAdd,
  externalCatalogue = false,
}) {
  const [showAll, setShowAll] = useState(false);
  // A selection below the fold must not be hidden by the budget.
  const selectedBeyondBudget = rows
    .slice(RESULT_BUDGET)
    .some((row) => candidateKey(row) === selectedId);
  const expanded = showAll || selectedBeyondBudget;
  const visible = expanded ? rows : rows.slice(0, RESULT_BUDGET);
  const hidden = rows.length - visible.length;

  return (
    <>
      <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Discover candidates">
        {visible.map((row) => (
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
      {hidden > 0 ? (
        <button
          type="button"
          className="rd-v2-discover-show-all"
          data-testid="discover-show-all"
          onClick={() => setShowAll(true)}
        >
          Show all {rows.length} — {hidden} more below
        </button>
      ) : null}
      {expanded && rows.length > RESULT_BUDGET ? (
        <button
          type="button"
          className="rd-v2-discover-show-all"
          data-testid="discover-show-fewer"
          onClick={() => setShowAll(false)}
          disabled={selectedBeyondBudget}
        >
          {selectedBeyondBudget
            ? `Showing all ${rows.length} — a selected offering is below the first ${RESULT_BUDGET}`
            : `Show first ${RESULT_BUDGET}`}
        </button>
      ) : null}
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
  onSearchSummary,
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
  const [agentMeta, setAgentMeta] = useState({
    summary: "",
    nextAction: "",
    engine: "",
    routeReason: "",
    layers: null,
    cacheHit: false,
  });
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
    setAgentMeta({
      summary: "",
      nextAction: "",
      engine: "",
      routeReason: "",
      layers: null,
      cacheHit: false,
    });
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
        // Best-practice stack: L0 hands (held/routes) → L1 desk-grounded Composer+MCP.
        const discover = await discoverSearch(q, 12, email, { mode: "auto" });
        const discoverRows = flattenRows(discover);
        const engine = String(discover.engine || discover.mode || "composer");
        const meta = {
          summary: discover.summary || "",
          nextAction: discover.next_action || "",
          engine,
          routeReason: discover.route_reason || "",
          layers: discover.layers || null,
          cacheHit: Boolean(discover.cache_hit),
        };
        if (discoverRows.length) {
          apply(discover, engine);
          setIndexMiss(Boolean(discover.index_miss) && !discoverRows.some((r) => r.placement === "held" || r.local_ready));
          setAgentMeta(meta);
          return;
        }

        setAgentMeta({ ...meta, nextAction: discover.next_action || "paste_url" });
        setIndexMiss(Boolean(discover.index_miss ?? true));
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
    // Optional live enrichment is retired — Composer turn continues past miss via MCP.
    // Keep preferLiveSources / Search wider as an explicit user escalation only.
    return undefined;
  }, [searchQuery, isExplore, loadedQuery, preferLiveSources, externalSearchQuery, enrichedQuestion]);

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
      const placement = evidencePlacement(projected, labIds);
      const taxonomy = projected.discover_taxonomy || classifyDiscoverResult(projected, labIds);
      // FE sufficiency taxonomy is not authority — placement/why from Composer/backend only.
      stampedRows.push({
        ...projected,
        placement,
        why: evidenceWhy(projected) || undefined,
        discover_taxonomy: taxonomy,
        discover_sufficiency: null,
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
      // listing of a dataset already shown under Library evidence.
      if (row.discover_sufficiency?.state === "exact-local") {
        groups.duplicates += 1;
        continue;
      }
      const placement = evidencePlacement(row, labIds);
      const taxonomy = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
      if (placement === PLACEMENT.HELD || taxonomy.key.startsWith("local-")) {
        groups.held.push(row);
      } else if (placement === PLACEMENT.CONTEXT || offeringType(row, taxonomy) === "Reference only" || offeringType(row, taxonomy) === "Web context") {
        groups.context.push(row);
      } else if (placement === PLACEMENT.ROUTE || ["external-acquirable", "external-probed"].includes(taxonomy.key)) {
        groups.available.push(row);
      } else {
        groups.external.push(row);
      }
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
        ? `${plural(resultGroups.available.length, "route")} available`
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

  /**
   * What this search found, for the rail.
   *
   * With no candidate selected the rail was 9% ink in a 374x836 column -- a
   * quarter of the viewport holding a folder icon and two lines. The authority
   * allows a quiet rail but forbids a "permanent empty inspector" (§3), and
   * during an active search there is a meaningful object: the search itself.
   *
   * Every number here is counted off rows already rendered in the centre.
   * Nothing is inferred, so the panel cannot claim coverage the results do not
   * show.
   */
  const searchSummary = useMemo(() => {
    if (!q) return null;
    const sufficiency = { exact: resultGroups.duplicates, partial: 0, related: 0, none: 0, unknown: 0 };
    const routes = new Map();
    for (const row of [...resultGroups.available, ...resultGroups.external]) {
      const state = String(row?.discover_sufficiency?.state || "");
      if (state === "partial-local") sufficiency.partial += 1;
      else if (state === "related-local") sufficiency.related += 1;
      else if (state === "no-local-alternative") sufficiency.none += 1;
      else sufficiency.unknown += 1;

      const via = Array.isArray(row?.collect_via) ? row.collect_via[0] : row?.collect_via;
      const label = String(via || "").trim();
      if (label) routes.set(label, (routes.get(label) || 0) + 1);
    }
    return {
      query: q,
      offerings: resultGroups.available.length + resultGroups.external.length,
      held: resultGroups.held.length,
      webContext: resultGroups.context.length,
      queryReady: resultGroups.held.filter((r) => r.local_ready).length,
      sufficiency,
      routes: [...routes.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4),
      engine: agentMeta.engine || undefined,
      next_action: agentMeta.nextAction || undefined,
      summary: agentMeta.summary || undefined,
      cache_hit: Boolean(agentMeta.cacheHit),
      held_titles: resultGroups.held.slice(0, 5).map((r) => ({
        title: r.title || r.label || r.dataset_id || "",
        dataset_id: r.dataset_id || undefined,
      })).filter((r) => r.title),
      route_titles: resultGroups.available
        .filter((r) => r.kind === "declared_route" || r.placement === "route" || r.source_id)
        .slice(0, 5)
        .map((r) => ({
          title: r.title || r.label || r.source_id || "",
          source_id: r.source_id || undefined,
        }))
        .filter((r) => r.title),
    };
  }, [q, resultGroups, agentMeta]);

  // Keyed on content, not identity. `searchSummary` is a fresh object on every
  // render, so depending on it directly pushed new state into App, which
  // re-rendered BrowsePage, which built another object -- an infinite loop that
  // stalled the whole shell rather than failing loudly.
  const searchSummaryKey = searchSummary ? JSON.stringify(searchSummary) : "";
  useEffect(() => {
    onSearchSummary?.(searchSummaryKey ? JSON.parse(searchSummaryKey) : null);
     
  }, [searchSummaryKey]);
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

  // Adaptive freeze (2026-07-28): held evidence is chrome, not a permanent
  // centre section. Opus inverted that into "IN YOUR LIBRARY" as the primary
  // canvas; restore the freeze chrome so Available offerings stay primary.
  const offeringsCount = resultGroups.available.length + resultGroups.external.length;
  const showLibraryChromeOpen = false;
  const libraryEvidenceMenu = resultGroups.held.length ? (
    <details
      className="rd-v2-discover-library-evidence"
      data-testid="discover-library-evidence"
      open={showLibraryChromeOpen || undefined}
    >
      <summary>Library evidence · {resultGroups.held.length}</summary>
      <div className="rd-v2-discover-library-popover">
        <span className="rd-v2-eyebrow">Relevant Library evidence</span>
        <LibraryResultList
          rows={groupCatalogueVariants(resultGroups.held).slice(0, 6)}
          labIds={labIds}
          selectedId={selectedId}
          onSelectRow={onSelectRow}
        />
        {resultGroups.held.length > 6 ? (
          <p className="muted">Showing 6 of {resultGroups.held.length}.</p>
        ) : null}
        <div className="rd-v2-discover-library-popover-actions">
          <button
            type="button"
            className="rd-v2-btn sm"
            onClick={() => onAskQuery?.(
              q,
              {
                kind: "results",
                rows: resultGroups.held,
                prompt: `Compare coverage of the held Library evidence for: ${q}. Say what is covered, what remains unknown, and whether a wider source is still needed.`,
              },
            )}
          >
            Compare coverage
          </button>
          <a className="rd-v2-btn sm ghost" href={`?tab=library&q=${encodeURIComponent(q)}`}>
            Open Library results
          </a>
        </div>
      </div>
    </details>
  ) : null;

  const stackEngineLabel =
    agentMeta.engine === "composer_mcp_grounded" || agentMeta.engine === "hybrid_hands_composer"
      ? "Desk + Composer"
      : agentMeta.engine === "lexical_fast" || agentMeta.engine === "lexical"
        ? "Library index"
        : agentMeta.engine === "hands_routes"
          ? "Declared routes"
          : agentMeta.engine || "";

  const exploreChrome = !loading && !error && q ? (
    <div className="rd-v2-discover-explore-chrome" data-testid="discover-explore-chrome" role="toolbar" aria-label="Discover result scope">
      <span className={offeringsCount ? "on" : ""}>
        Available · {offeringsCount}
      </span>
      {libraryEvidenceMenu || <span className="muted">Library evidence · 0</span>}
      {resultGroups.context.length ? (
        <span>Web context · {resultGroups.context.length}</span>
      ) : (
        <span className="muted">Web context · 0</span>
      )}
      {stackEngineLabel ? (
        <span className="muted" data-testid="discover-stack-meta">
          {stackEngineLabel}
          {agentMeta.cacheHit ? " · cached" : ""}
          {agentMeta.layers?.total_ms != null
            ? ` · ${Math.round(Number(agentMeta.layers.total_ms))}ms`
            : ""}
        </span>
      ) : null}
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
      lead="Find held evidence and sources beyond it"
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
              {exploreChrome}
              {/* Result counts and strategy chrome live in exploreChrome
                  (Available / Library evidence / Web context). Keeping a second
                  totals row restated the same numbers before the first offering. */}
            </section>

            {/* Adaptive freeze: Available / external offerings are the primary
                canvas. Held evidence is chrome above, not a permanent section. */}
            {resultGroups.available.length ? (
              <section className="rd-v2-discover-best-fit" aria-label="Available" data-testid="discover-best-fit">
                {/* §16: the header states one set and its partition, once.
                    The chrome above already carries Available / Library
                    evidence / Web context, so repeating "3 offerings" here and
                    the scope summary again below stated the same totals three
                    times before the first row. */}
                <div className="rd-v2-home-section-head">
                  <h3>
                    Available
                    <span className="rd-v2-section-count">{resultGroups.available.length}</span>
                  </h3>
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

            {!resultGroups.available.length && !resultGroups.external.length && resultGroups.duplicates ? (
              <p className="muted rd-v2-discover-all-held" data-testid="discover-all-held">
                {resultGroups.duplicates} external{" "}
                {resultGroups.duplicates === 1 ? "match" : "matches"} already held in Library evidence above.
                Open that chrome to review them, or search wider for alternatives.
              </p>
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

            {!loading && allInLab && offeringsCount ? (
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
                  {agentMeta.summary
                    || `The desk holds no ${stateFilter === "all" ? "" : `${activeFilter.label.toLowerCase()} `}match for “${q}”${indexMiss ? " in the current research index." : "."}`}
                </p>
                {stackEngineLabel ? (
                  <p className="muted rd-v2-discover-agent-meta" data-testid="discover-agent-meta">
                    {stackEngineLabel}
                    {agentMeta.nextAction ? ` · next: ${agentMeta.nextAction.replace(/_/g, " ")}` : ""}
                    {agentMeta.cacheHit ? " · cached" : ""}
                    {agentMeta.layers?.total_ms != null
                      ? ` · ${Math.round(Number(agentMeta.layers.total_ms))}ms`
                      : ""}
                  </p>
                ) : null}
                {(indexMiss || agentMeta.nextAction === "search_wider" || agentMeta.nextAction === "paste_url") && onSearchWeb ? (
                  <button type="button" className="rd-v2-btn sm" onClick={() => onSearchWeb(q)}>
                    Search wider sources →
                  </button>
                ) : null}
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
                ) : missRouteReason === "loading" && !agentMeta.summary ? (
                  <p className="muted rd-v2-discover-no-route">Checking which sources could supply this…</p>
                ) : (missRouteReason === "no_route_found" || agentMeta.routeReason === "no_route_found" || agentMeta.nextAction === "paste_url") ? (
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
                {/* "Other external matches" named the group by what it was not
                    and gave no reason for the split. These rows are separated
                    because the comparator found nothing equivalent in the
                    Library -- say that, in the possession vocabulary the
                    adaptive freeze §16 settled on. */}
                <div className="rd-v2-home-section-head">
                  <h3>
                    {externalCatalogueActive ? "External catalogue matches" : "Beyond your Library"}
                    <span className="rd-v2-section-count">{resultGroups.external.length}</span>
                  </h3>
                  <span className="muted">
                    {externalCatalogueActive
                      ? plural(resultGroups.external.length, "external catalogue record")
                      : "no equivalent found in your Library"}
                  </span>
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

            {resultGroups.held.length ? (
              <section className="rd-v2-discover-other-matches" aria-label="In your Library" data-testid="discover-held-section">
                <div className="rd-v2-home-section-head">
                  <h3>
                    In your Library
                    <span className="rd-v2-section-count">{resultGroups.held.length}</span>
                  </h3>
                  <span className="muted">
                    {readyCount ? `${readyCount} query-ready` : "already collected"}
                  </span>
                </div>
                <DiscoverCandidateList
                  rows={groupCatalogueVariants(resultGroups.held)}
                  labIds={labIds}
                  selectedId={selectedId}
                  onSelectRow={onSelectRow}
                  onAdd={onReviewAcquisition}
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
