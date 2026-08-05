/**
 * Discover presentation helpers (D1).
 * Taxonomy lives in discoverTaxonomy.js — this file adapts pills/actions without fit heuristics.
 */

import {
  classifyDiscoverResult,
  isLocalHolding,
  taxonomyStageCounts,
} from "./discoverTaxonomy.js";

export {
  classifyDiscoverResult,
  exceptionalRowPill,
  orderDiscoverResults,
  taxonomyMatchesFilter,
  taxonomyStageCounts,
} from "./discoverTaxonomy.js";

/**
 * Presentation state for pills and rail actions.
 * Removes Faculty finance/crypto fit heuristics.
 */
export function discoverCandidateState(row, labIds) {
  const taxonomy = row?.discover_taxonomy || classifyDiscoverResult(row, labIds);
  const queued = Boolean(row?.queued);

  if (queued && !taxonomy.key.startsWith("local-")) {
    return {
      key: "queued",
      label: "Queued",
      className: "queue",
      taxonomy,
      possession: taxonomy.possession,
      readiness: "Queued for collection",
      nextAction: "Review queued job",
    };
  }

  const actionKey = taxonomy.key.startsWith("local-") ? "in_lab" : taxonomy.key;

  return {
    key: actionKey,
    label: taxonomy.label,
    className: taxonomy.className,
    taxonomy,
    possession: taxonomy.possession,
    readiness: taxonomy.readiness,
    nextAction: taxonomy.key.startsWith("local-")
      ? "Open in Library"
      : taxonomy.key === "external-acquirable"
        ? "Review acquisition route"
        : taxonomy.key === "external-probed"
          ? "Review probe, then decide"
          : taxonomy.key === "licensed-manual"
            ? "Manual / licensed path"
            : "Inspect source",
  };
}

export function browseRowState(row, labIds) {
  const state = discoverCandidateState(row, labIds);
  return { label: state.label, className: state.className };
}

export function decorateDiscoverCandidate(row, labIds) {
  const taxonomy = classifyDiscoverResult(row, labIds);
  return {
    ...row,
    discover_taxonomy: taxonomy,
    discover_state: discoverCandidateState({ ...row, discover_taxonomy: taxonomy }, labIds),
  };
}

/** @deprecated Prefer taxonomyStageCounts — kept for pipeline overview counts. */
export function discoverStageCounts(rows, labIds) {
  const tax = taxonomyStageCounts(rows, labIds);
  return {
    total: tax.total,
    probeReady: tax.external - tax.needsAccess,
    queued: rows.filter((r) => r.queued).length,
    inLab: tax.inLab,
    external: tax.external,
    queryReady: tax.queryReady,
    needsAccess: tax.needsAccess,
  };
}

/** Desk identifiers read as jargon on a faculty-facing row.
 *
 * Values like `scrape_snapshot` and `catalog_harvest` reach the coverage slot
 * straight from pipeline configuration and were rendering verbatim. Spacing
 * and sentence-casing them keeps the recorded value truthful -- nothing is
 * substituted or inferred -- while making it legible to a reader who does not
 * work on this desk. */
function humanizeDeskToken(value) {
  const text = String(value || "").trim();
  if (!/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(text)) return text;
  const spaced = text.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function coverageLine(row) {
  const parts = [
    row?.coverage,
    row?.date_range,
    row?.temporal_coverage,
    row?.geographic_coverage,
    row?.grain,
  ]
    .map((p) => humanizeDeskToken(p))
    .filter(Boolean);
  const seen = new Set();
  const unique = [];
  for (const p of parts) {
    const k = p.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    unique.push(p);
  }
  if (!unique.length) return "Coverage not described";
  return unique.join(" · ");
}

export function descriptiveLine(row) {
  // `one_line` is what the registry actually calls its plain-language
  // description, and it was missing from this list -- so registry-backed
  // offerings rendered "Description not recorded" while the very same dataset
  // showed a full description in Library evidence one section above.
  const text = String(
    row?.description || row?.one_line || row?.recommended_use || row?.subtitle || row?.grain || "",
  )
    .replace(/\s+/g, " ")
    .trim();
  if (!text) {
    const source = row?.source || row?.publisher || row?.collect_via;
    return source ? `${source} source` : "No description provided";
  }
  if (text.length <= 160) return text;
  return `${text.slice(0, 159).trim()}…`;
}

const DISCOVER_TERM_LABELS = Object.freeze({
  materialized_instant: "Direct collection",
  materialized_bulk: "Bulk archive route",
  procurement_catalog: "Procurement route",
  live_connector: "Connected route",
  governance_regulatory: "governance and regulatory records",
  daily_prices: "daily market prices",
  index_pit_survivorship: "point-in-time index membership",
  estimates_revisions: "estimates and revisions",
  onchain_crypto: "on-chain market data",
  scholarly_works: "scholarly works",
  social_sentiment: "social sentiment",
});

/** Convert connector metadata into readable research language without changing its meaning. */
export function humanizeDiscoverDescription(value) {
  return String(value || "")
    .split(" · ")
    .map((part) => {
      const normalized = part.trim().toLowerCase();
      if (DISCOVER_TERM_LABELS[normalized]) return DISCOVER_TERM_LABELS[normalized];
      return part.replace(/_/g, " ");
    })
    .join(" · ");
}

export function isLabOwned(row, labIds) {
  return isLocalHolding(row, labIds);
}

/** Human names for declared collection routes.
 *
 * Shared so the row ("Collect via BigQuery") and the rail's route tally use
 * one vocabulary. They previously disagreed: the rail listed the raw config
 * tokens `bigquery` / `datacite` / `http_manifest` beside rows that had
 * already named them properly. */
const ROUTE_NAMES = {
  bigquery: "BigQuery",
  datacite: "DataCite",
  huggingface: "Hugging Face",
  local_open: "the Library copy",
  http_manifest: "a file manifest",
  scrape_snapshot: "a page snapshot",
  catalog_harvest: "a catalog harvest",
  browser_extract: "browser extraction",
  api_query: "an API query",
};

const ROUTE_ACRONYMS = new Set([
  "api", "edp", "sec", "doi", "ftp", "sftp", "rpc", "csv", "lseg", "twse", "mops",
]);

export function routeDisplayName(value) {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "";
  if (ROUTE_NAMES[key]) return ROUTE_NAMES[key];
  return key
    .split("_")
    .filter(Boolean)
    .map((word) => (ROUTE_ACRONYMS.has(word) ? word.toUpperCase() : word))
    .join(" ");
}
