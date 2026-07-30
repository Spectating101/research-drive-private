/**
 * Discover result taxonomy (D1 / D1.1).
 *
 * Machine keys → human labels:
 *   local-query-ready      → In Library · Query ready
 *   local-connected        → In Library · Connected
 *   local-metadata         → In Library · Metadata only
 *   external-discoverable  → External · Available to inspect
 *   external-probed        → External · Probed
 *   external-acquirable    → External · Acquisition available
 *   external-unavailable   → External · Acquisition unavailable
 *   licensed-manual        → Licensed / manual access
 *
 * Precedence (first match wins):
 * 1. local-query-ready — lab holding + explicit query readiness
 * 2. local-connected — lab holding + storage/path connection, not query-ready
 * 3. local-metadata — lab/registry membership without connection or query path
 * 4. licensed-manual — explicit entitlement/manual/licensed signal
 * 5. external-unavailable — explicit inaccessible/unsupported acquisition
 * 6. external-acquirable — explicit collect route / collection capability
 *    (generic connector_id alone is not enough)
 * 7. external-probed — probe evidence whose candidate_key matches this row
 * 8. external-discoverable — default external inspectable candidate
 *
 * Unknown/missing fields never invent readiness, probe, or acquisition.
 * Group order for lists: 1 → 2 → 3 → 4 (see TAXONOMY.group); API order preserved within group.
 */

import { candidateKey } from "./candidateKey.js";

export const TAXONOMY = {
  "local-query-ready": {
    label: "In Library · Query ready",
    possession: "In Library",
    readiness: "Query ready",
    className: "lab",
    group: 1,
    filter: ["in_lab", "query_ready"],
  },
  "local-connected": {
    label: "In Library · Connected",
    possession: "In Library",
    readiness: "Connected",
    className: "lab",
    group: 2,
    filter: ["in_lab"],
  },
  "local-metadata": {
    label: "In Library · Metadata only",
    possession: "In Library",
    readiness: "Metadata only",
    className: "lab",
    group: 2,
    filter: ["in_lab"],
  },
  "external-discoverable": {
    label: "External · Available to inspect",
    possession: "External",
    readiness: "Available to inspect",
    className: "ext",
    group: 3,
    filter: ["external"],
  },
  "external-probed": {
    label: "External · Probed",
    possession: "External",
    readiness: "Probed",
    className: "ext",
    group: 3,
    filter: ["external"],
  },
  "external-acquirable": {
    label: "External · Acquisition available",
    possession: "External",
    readiness: "Acquisition available",
    className: "ext",
    group: 3,
    filter: ["external"],
  },
  "external-unavailable": {
    label: "External · Acquisition unavailable",
    possession: "External",
    readiness: "Acquisition unavailable",
    className: "warn",
    group: 4,
    filter: ["external", "needs_access"],
  },
  "licensed-manual": {
    label: "Licensed / manual access",
    possession: "Licensed",
    readiness: "Manual access",
    className: "warn",
    group: 4,
    filter: ["needs_access"],
  },
};

function lower(value) {
  return String(value || "").toLowerCase();
}

function trim(value) {
  return String(value ?? "").trim();
}

const CATALOG_ONLY_ACCESS = new Set([
  "catalog_reference",
  "procurement_catalog",
  "live_connector",
]);

/** Lab-owned / registry-local possession. */
export function isLocalHolding(row, labIds) {
  if (!row || typeof row !== "object") return false;
  const id = row.dataset_id || row.id;
  if (id && labIds?.has?.(id)) return true;
  if (row.local_ready || row.in_vault) return true;
  const kind = lower(row.kind);
  if (kind === "local_registry" || kind === "lab") return true;
  if (row.local === true || row.in_lab === true) return true;
  if (row.registry_id || row.registration_id || row.registered === true) return true;
  if (row.materialization?.query_ready === true) return true;
  if (row.materialization?.resolved_path) return true;

  // A registry row is not automatically a Library holding. The registry also
  // contains catalogue references, procurement candidates, and live connectors
  // whose local_path points to their metadata card rather than acquired evidence.
  const access = lower(row.source_access_mode || row.access_shape || "");
  if (CATALOG_ONLY_ACCESS.has(access)) return false;
  const hasLocalPath = Boolean(row.local_root || row.local_path);
  if (!hasLocalPath) return false;
  if (["derived_internal", "materialized_bulk", "materialized_instant"].includes(access)) {
    return true;
  }
  const readiness = lower(row.analysis_readiness || row.readiness);
  if (readiness === "instant" || readiness === "query_ready" || readiness === "registered") {
    return true;
  }
  // Collected outputs sometimes predate source_access_mode. A concrete local
  // backend + path is possession evidence; a generic registry card is not.
  return !access && lower(row.backend).startsWith("local_");
}

/**
 * Explicit query readiness — not inferred from a URL, title, or bare “panel”.
 * Missing readiness → not query-ready.
 */
export function isQueryReady(row) {
  if (!row || typeof row !== "object") return false;
  if (row.materialization?.query_ready === true) return true;
  if (row.materialization?.query_ready === false) return false;
  if (row.query_ready === true || row.queryable === true) return true;
  const readiness = lower(row.analysis_readiness || row.readiness);
  // `instant` is the registry's declared query posture. The UI labels this
  // "Query-ready declared"; an explicit failed materialization above wins.
  if (readiness === "instant" || readiness === "query_ready" || readiness === "queryable") return true;
  return false;
}

/** Conservative possession set for Discover. Catalogue membership alone is excluded. */
export function holdingIdsFromCatalog(rows = []) {
  return new Set(
    rows
      .filter((row) => isLocalHolding(row))
      .map((row) => row?.dataset_id || row?.id)
      .filter(Boolean),
  );
}

/** Known storage/source connection without proven query path. */
export function isLocalConnected(row) {
  if (!row || typeof row !== "object") return false;
  if (row.local_ready || row.local_root || row.local_path || row.in_vault) return true;
  const access = lower(row.access_shape || row.source_access_mode || "");
  if (access.includes("materialized") || access.includes("local_file") || access.includes("connected")) {
    return true;
  }
  return false;
}

/**
 * Licensed / manual / entitlement — requires an explicit signal.
 * Do not infer from a generic license string alone unless it clearly marks restricted access.
 */
export function isLicensedManual(row) {
  if (!row || typeof row !== "object") return false;
  if (row.manual_access === true || row.requires_manual === true) return true;
  const mode = lower(row.access_mode || row.acquisition_mode || row.entitlement);
  if (/licensed|manual|entitlement|restricted|paywall|login_required|credential/.test(mode)) return true;
  const procure = lower(row.procureability || row.procureability_label);
  if (/manual|licensed|entitlement|restricted|unavailable_without/.test(procure)) return true;
  const license = lower(row.license);
  if (/all rights reserved|proprietary|commercial license|requires approval/.test(license)) return true;
  return false;
}

/** Explicit inaccessible / unsupported acquisition — never from a missing optional field. */
export function isAcquisitionUnavailable(row) {
  if (!row || typeof row !== "object") return false;
  if (row.acquisition_available === false || row.collectable === false) return true;
  const mode = lower(row.access_mode || row.acquisition_mode);
  if (/inaccessible|unsupported|blocked|forbidden|unavailable/.test(mode)) return true;
  const procure = lower(row.procureability || row.procureability_label);
  if (/^unavailable$|not collectable|cannot collect|blocked/.test(procure)) return true;
  return false;
}

/** Connector object explicitly advertises collection/download/harvest capability. */
function connectorSupportsCollection(connector) {
  if (!connector || typeof connector !== "object") return false;
  const bags = [
    connector.capabilities,
    connector.capability,
    connector.spec?.capabilities,
    connector.spec?.capability,
    connector.actions,
  ];
  for (const bag of bags) {
    const list = Array.isArray(bag) ? bag : bag ? [bag] : [];
    for (const item of list) {
      const s = lower(typeof item === "string" ? item : item?.id || item?.name || item?.action);
      if (/collect|download|harvest|materializ|acquire|ingest|fetch_files/.test(s)) return true;
    }
  }
  const mode = lower(connector.access_mode || connector.spec?.access_mode || "");
  if (/collect|download|harvest|materializ/.test(mode)) return true;
  return false;
}

/**
 * Explicit collection route — not a bare URL, not a generic connector id.
 * Gap: if a connector can collect but only exposes an id with no capability list,
 * we classify conservatively (not acquirable) until the contract carries capabilities.
 */
export function hasAcquisitionRoute(row) {
  if (!row || typeof row !== "object") return false;
  if (row.acquisition_available === true || row.collectable === true) return true;
  if (trim(row.collect_via) || trim(row.source_route)) return true;
  if (connectorSupportsCollection(row.connector)) return true;
  if (connectorSupportsCollection(row.probe_snapshot?.connector)) return true;
  if (connectorSupportsCollection(row.probe_result?.connector)) return true;
  const procure = lower(row.procureability || row.procureability_label);
  if (/collect|download|harvest|manifest|queue|acquir/.test(procure) && !/unavail|manual|licens|probe.?only/.test(procure)) {
    return true;
  }
  return false;
}

function evidenceCandidateKey(evidence) {
  if (!evidence || typeof evidence !== "object") return "";
  return trim(evidence.candidate_key || evidence.candidateKey || "");
}

/**
 * Candidate-bound probe evidence only (D0 identity contract).
 * Unqualified probed:true / unbound probe_result / probe_state alone are insufficient.
 */
export function hasBoundProbe(row) {
  if (!row || typeof row !== "object") return false;
  const rowKey = trim(row.candidate_key) || candidateKey(row);
  if (!rowKey) return false;

  for (const evidence of [row.probe_snapshot, row.probe_result]) {
    const evidenceKey = evidenceCandidateKey(evidence);
    if (evidenceKey && evidenceKey === rowKey) return true;
  }
  return false;
}

/**
 * @returns {{ key: string, label: string, possession: string, readiness: string, className: string, group: number }}
 */
export function classifyDiscoverResult(row, labIds) {
  const meta = (key) => {
    const t = TAXONOMY[key];
    return {
      key,
      label: t.label,
      possession: t.possession,
      readiness: t.readiness,
      className: t.className,
      group: t.group,
    };
  };

  if (isLocalHolding(row, labIds)) {
    if (isQueryReady(row)) return meta("local-query-ready");
    if (isLocalConnected(row)) return meta("local-connected");
    return meta("local-metadata");
  }

  if (isLicensedManual(row)) return meta("licensed-manual");
  if (isAcquisitionUnavailable(row)) return meta("external-unavailable");
  if (hasAcquisitionRoute(row)) return meta("external-acquirable");
  if (hasBoundProbe(row)) return meta("external-probed");
  return meta("external-discoverable");
}

/**
 * Exceptional / transient row pill — only when it adds information beyond the taxonomy line.
 * Normal readiness is stated once in the taxonomy line; no duplicate pill.
 */
export function exceptionalRowPill(row, taxonomy, state) {
  if (state?.key === "queued" || row?.queued) {
    return { label: "Queued", className: "queue" };
  }
  const key = taxonomy?.key || "";
  if (key === "licensed-manual") {
    return { label: "Manual access", className: taxonomy.className || "warn" };
  }
  if (key === "external-unavailable") {
    return { label: "Unavailable", className: taxonomy.className || "warn" };
  }
  return null;
}

export function taxonomyMatchesFilter(classification, filterId) {
  if (!filterId || filterId === "all") return true;
  const t = TAXONOMY[classification.key];
  return Boolean(t?.filter?.includes(filterId));
}

/**
 * Group by taxonomy, preserve relative API order within each group.
 * @param {object[]} rows
 * @param {Set} labIds
 */
export function orderDiscoverResults(rows, labIds) {
  if (!Array.isArray(rows) || !rows.length) return [];
  const decorated = rows.map((row, index) => ({
    row,
    index,
    classification:
      row?.discover_taxonomy?.lifecycle_projected
        ? row.discover_taxonomy
        : classifyDiscoverResult(row, labIds),
  }));
  decorated.sort((a, b) => {
    if (a.classification.group !== b.classification.group) {
      return a.classification.group - b.classification.group;
    }
    return a.index - b.index;
  });
  return decorated.map((d) => ({
    ...d.row,
    discover_taxonomy: d.classification,
  }));
}

export function taxonomyStageCounts(rows, labIds) {
  const counts = {
    total: rows.length,
    inLab: 0,
    queryReady: 0,
    external: 0,
    needsAccess: 0,
    probed: 0,
    acquirable: 0,
  };
  for (const row of rows) {
    const c = row.discover_taxonomy || classifyDiscoverResult(row, labIds);
    if (c.key.startsWith("local-")) counts.inLab += 1;
    if (c.key === "local-query-ready") counts.queryReady += 1;
    if (c.key.startsWith("external-") || c.key === "licensed-manual") counts.external += 1;
    if (c.key === "licensed-manual" || c.key === "external-unavailable") counts.needsAccess += 1;
    if (c.key === "external-probed") counts.probed += 1;
    if (c.key === "external-acquirable") counts.acquirable += 1;
  }
  return counts;
}
