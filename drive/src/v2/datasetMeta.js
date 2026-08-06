/** Map registry rows → frozen UI labels (Detail + StatusPill). */

/** Exact readiness tokens that mean smoke-proven / instant local query — never fuzzy `/query|ready/`. */
export function isQueryReadyReadiness(value) {
  const readiness = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return (
    readiness === "query_ready" ||
    readiness === "instant" ||
    readiness === "instant_or_minutes" ||
    readiness === "queryable"
  );
}

/**
 * Receipt-recovery catalog rows — registered in a receipt only, not a reusable query holding.
 * Terra donor (6769b75 / datasetMeta honesty).
 */
export function isReceiptOnlyAsset(dataset) {
  const state = String(dataset?.catalog_reconciliation?.state || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return state === "receipt_only";
}

export function statusPillKind(dataset) {
  if (dataset?.live_identity_badge?.kind && dataset?.live_identity_badge?.label) {
    return dataset.live_identity_badge;
  }
  if (isReceiptOnlyAsset(dataset)) {
    return { kind: "registered", label: "Registered · reconciliation pending" };
  }
  const readiness = String(dataset?.analysis_readiness || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (dataset?.external || dataset?.collect_via) {
    return { kind: "external", label: "External" };
  }
  if (isQueryReadyReadiness(readiness)) {
    return { kind: "query-ready", label: "Query ready" };
  }
  if (readiness === "registered") {
    return { kind: "registered", label: "Registered" };
  }
  if (readiness === "dry_run_before_execution" || /bigquery/i.test(dataset?.backend || "")) {
    return { kind: "connected", label: "Connected" };
  }
  if (readiness === "connected") return { kind: "connected", label: "Connected" };
  if (readiness === "metadata_search" || readiness === "metadata_only") {
    return { kind: "remote", label: "Metadata only" };
  }
  if (readiness === "procurement_planning") return { kind: "queued", label: "Queued" };
  if (readiness === "sample_now_full_later") return { kind: "warn", label: "Review" };
  if (readiness === "failed") return { kind: "failed", label: "Failed" };
  return { kind: "unknown", label: "Readiness unknown" };
}

export function statusPill(dataset) {
  return statusPillKind(dataset).label;
}

/** Faculty-facing "Can I use this?" copy — keeps Registered distinct from Query ready. */
export function canIUseDecision(dataset) {
  const state = statusPillKind(dataset);
  if (state.kind === "query-ready") {
    return {
      headline: "Query ready",
      body: "You can preview and query this dataset now.",
    };
  }
  if (state.kind === "connected") {
    return {
      headline: "Connected",
      body: "A live source connection exists. Instant local query access is not confirmed.",
    };
  }
  if (state.kind === "remote") {
    return {
      headline: "Metadata only",
      body: "This record supports discovery and acquisition. A queryable local asset is not confirmed.",
    };
  }
  if (state.kind === "queued") {
    return {
      headline: "Queued",
      body: "Acquisition or registration work is still pending.",
    };
  }
  if (state.kind === "warn") {
    return {
      headline: "Review required",
      body: "The current asset needs review before analysis.",
    };
  }
  if (state.kind === "failed") {
    return {
      headline: "Failed",
      body: "The current asset path failed and needs attention before use.",
    };
  }
  if (state.kind === "external") {
    return {
      headline: "External source",
      body: "This source is not confirmed as a usable Library asset.",
    };
  }
  if (state.kind === "registered") {
    return {
      headline: "Registered",
      body: "Registered and reusable as an archived research asset; querying has not yet been proven.",
    };
  }
  return {
    headline: "Readiness unknown",
    body: "Current metadata does not establish a usable query path.",
  };
}

function looksOpsFace(text) {
  const s = String(text || "").trim();
  if (!s) return true;
  if (/^(Custom collect|Route prove|Synthesis)\b/i.test(s)) return true;
  if (/Using the Library asset/i.test(s)) return true;
  if (s.length > 96) return true;
  return false;
}

/** Prefer faculty meaning (title/display_name); hide ops jargon faces. */
export function displayName(dataset) {
  const candidates = [
    dataset?.display_name,
    dataset?.title,
    dataset?.faculty_title,
    dataset?.name,
  ];
  for (const c of candidates) {
    if (c && !looksOpsFace(c)) return String(c);
  }
  for (const c of candidates) {
    if (c) return String(c).slice(0, 72);
  }
  return dataset?.dataset_id || "Dataset";
}

export function rowSubtitle(dataset) {
  const parts = [dataset?.subtitle || dataset?.dataset_id || dataset?.doi || dataset?.url, dataset?.grain].filter(Boolean);
  const cov = dataset?.coverage || dataset?.date_range;
  if (cov) parts.push(String(cov));
  return parts.join(" · ");
}

export function detailFields(dataset) {
  const d = dataset || {};
  const partitionParts = [d.grain, d.coverage || d.date_range || d.temporal_coverage].filter(Boolean);
  const joinKeys = d.join_keys || [];
  return {
    description: d.description || d.recommended_use || "",
    coverage: d.coverage || d.date_range || d.temporal_coverage || null,
    source: d.source || d.publisher || d.domain || d.backend || null,
    access:
      d.access_mode ||
      d.access_shape ||
      (d.local_root ? `Vault · ${d.local_root}` : null) ||
      (d.backend?.includes("api") ? "API" : "Query engine :8765"),
    limitations: d.limitations || null,
    partition: partitionParts.length ? partitionParts.join(" · ") : null,
    joinKeys: joinKeys.length ? joinKeys : null,
    vault: d.local_root || d.local_path || d.vault_path || null,
    use: d.recommended_use || (d.grain ? `Panel at ${d.grain} grain` : null),
  };
}

export function buildSchemaRows(dataset, previewRow) {
  const rows = [];
  if (dataset?.time_field) rows.push({ name: dataset.time_field, type: "DATE/TEXT", note: "Time field" });
  (dataset?.entity_fields || []).forEach((f) => rows.push({ name: f, type: "TEXT", note: "Entity" }));
  (dataset?.join_keys || []).forEach((f) => {
    if (!rows.some((r) => r.name === f)) rows.push({ name: f, type: "TEXT", note: "Join key" });
  });
  if (previewRow) {
    Object.keys(previewRow)
      .slice(0, 12)
      .forEach((k) => {
        if (!rows.some((r) => r.name === k)) {
          const v = previewRow[k];
          rows.push({ name: k, type: typeof v === "number" ? "NUMERIC" : "TEXT", note: "Observed" });
        }
      });
  }
  return rows;
}
