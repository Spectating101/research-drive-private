/**
 * Shared evidence placement vocabulary (Discover / Library / Synthesis).
 *
 * Backend is the authority when `placement` / `why` are present. FE only
 * derives placement from factual possession signals — never invents
 * "weak match" or "no Library alternative" judgment.
 */

export const PLACEMENT = Object.freeze({
  HELD: "held",
  ROUTE: "route",
  CONTEXT: "context",
  MISSING: "missing",
});

const CANNED_WHY = new Set([
  "matched on meaning, not wording",
  "matched on meaning not wording",
]);

export function cleanWhy(value) {
  const text = String(value || "")
    .trim()
    .replace(/\s+/g, " ");
  if (!text) return "";
  if (CANNED_WHY.has(text.toLowerCase().replace(/\.$/, ""))) return "";
  return text.slice(0, 240);
}

export function evidenceWhy(row) {
  return cleanWhy(row?.why || row?.selection_reason);
}

/**
 * @param {object} row
 * @param {Set<string>} [labIds]
 * @returns {"held"|"route"|"context"|"missing"}
 */
export function evidencePlacement(row, labIds) {
  const explicit = String(row?.placement || "")
    .trim()
    .toLowerCase();
  if (Object.values(PLACEMENT).includes(explicit)) return explicit;

  const status = String(row?.status || "")
    .trim()
    .toLowerCase();
  if (["held", "queryable", "query_ready"].includes(status)) return PLACEMENT.HELD;
  if (status === "missing") return PLACEMENT.MISSING;
  if (["needs_access", "sourceable"].includes(status)) return PLACEMENT.ROUTE;

  const id = String(row?.dataset_id || row?.id || "").trim();
  if (id && labIds?.has?.(id)) return PLACEMENT.HELD;
  if (row?.local_ready || row?.in_vault || row?.in_lab === true) return PLACEMENT.HELD;

  const kind = String(row?.kind || row?.type || "")
    .trim()
    .toLowerCase();
  if (["local_registry", "lab", "registry_dataset", "dataset"].includes(kind) && id) {
    return PLACEMENT.HELD;
  }
  if (/paper|article|literature|publication|web|page|context/.test(kind)) {
    return PLACEMENT.CONTEXT;
  }
  if (row?.collect_via || row?.collectable || row?.url || row?.doi || row?.connector_id || row?.source_id) {
    return PLACEMENT.ROUTE;
  }
  return PLACEMENT.CONTEXT;
}

export function placementLabel(placement) {
  switch (placement) {
    case PLACEMENT.HELD:
      return "In Library";
    case PLACEMENT.ROUTE:
      return "Collection route";
    case PLACEMENT.MISSING:
      return "Missing";
    case PLACEMENT.CONTEXT:
      return "Context";
    default:
      return "";
  }
}

/** Material Library relationships worth a dedicated line — not "no alternative". */
export function isMaterialLibraryRelation(state) {
  return ["exact-local", "partial-local", "related-local"].includes(String(state || ""));
}
