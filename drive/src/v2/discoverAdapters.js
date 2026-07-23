/** Discover Explore/History adapters — map BE contracts to faculty UI rows. */

import { isReceiptOnlyAsset, isQueryReadyReadiness, statusPillKind } from "./datasetMeta.js";

export function normalizeDiscoverMode(raw = "") {
  const mode = String(raw || "").trim().toLowerCase();
  if (mode === "history") return "history";
  // Legacy Search/Activity/Approvals collapse to Explore (focusAwaiting handled by discoverMode.js).
  if (
    mode === "explore" ||
    mode === "search" ||
    mode === "activity" ||
    mode === "approvals" ||
    mode === "awaiting" ||
    !mode
  ) {
    return "explore";
  }
  return "explore";
}

function endpointToUrl(endpoint) {
  const text = String(endpoint || "").trim();
  if (!text) return "";
  if (/^https?:\/\//i.test(text)) return text;
  if (/^[a-z0-9.-]+\.[a-z]{2,}(\/|$)/i.test(text)) return `https://${text}`;
  return "";
}

export function sourceResultToCandidate(row = {}) {
  const label = row.title || row.label || row.name || row.source_id || "External source";
  const caps = Array.isArray(row.capabilities) ? row.capabilities : [];
  const collect = Array.isArray(row.collect_via) ? row.collect_via : row.collect_via ? [row.collect_via] : [];
  const url = row.url || endpointToUrl(row.endpoint);
  return {
    ...row,
    kind: row.kind || "source",
    title: label,
    name: row.name || row.label || label,
    source: row.provider || row.source || row.label,
    publisher: row.provider || row.publisher || row.source,
    description:
      row.description ||
      [row.access_mode, ...caps.slice(0, 3)].filter(Boolean).join(" · "),
    access_mode: row.access_mode || row.access || "",
    collect_via: collect[0] || row.collect_via || "",
    url,
    external: true,
    preview_supported: Boolean(row.preview_supported),
    candidate_key: row.candidate_key || "",
    source_id: row.source_id || "",
    connector_id: row.connector_id || row.desk_connector_id || "",
  };
}

export function sourcesResponseToRows(data) {
  const results = Array.isArray(data?.results) ? data.results : [];
  const searchMeta = {
    search_mode: data?.search_mode || null,
    result_kind: data?.result_kind || null,
    query: data?.query || null,
    cached: data?.cached ?? null,
    freshness: data?.freshness || data?.as_of || null,
  };
  return results.map((row) => ({
    ...sourceResultToCandidate(row),
    _search_meta: searchMeta,
    search_meta: searchMeta,
    cached: row.cached ?? data?.cached,
  }));
}

/**
 * Normalize discover / semantic / unified search hits for Explore selection.
 * Never invents URLs or readiness — only derives dataset: candidate_key when
 * dataset_id is present and BE omitted candidate_key (unified search shape).
 */
export function searchHitToCandidate(row = {}) {
  if (!row || typeof row !== "object") return null;
  const datasetId =
    row.dataset_id ||
    (row.kind === "local_registry" || row.kind === "registry_dataset" ? row.id : "") ||
    "";
  const url = row.url || endpointToUrl(row.endpoint);
  const candidateKey =
    row.candidate_key || (datasetId ? `dataset:${datasetId}` : "") || "";
  return {
    ...row,
    dataset_id: datasetId || row.dataset_id || "",
    title: row.title || row.name || row.label || datasetId || url || "Untitled",
    name: row.name || row.title || row.label || datasetId || "",
    url: url || row.url || "",
    candidate_key: candidateKey,
    source_id: row.source_id || "",
    connector_id: row.connector_id || row.desk_connector_id || "",
  };
}

export function searchResponseToRows(data) {
  const fromSections = (data?.sections || []).flatMap((section) => section.rows || []);
  const flat = fromSections.length
    ? fromSections
    : data?.rows || data?.results || data?.hits || [];
  return (Array.isArray(flat) ? flat : []).map(searchHitToCandidate).filter(Boolean);
}

function pickIdentity(item = {}, plan = {}) {
  return {
    job_id: item.job_id || plan.job_id || "",
    intent_id: item.intent_id || "",
    candidate_key: item.candidate_key || plan.candidate_key || "",
    source_id: item.source_id || plan.source_id || "",
    connector_id:
      item.connector_id ||
      item.desk_connector_id ||
      plan.connector_id ||
      plan.catalog_connector_id ||
      "",
    subscription_id: item.subscription_id || "",
    dataset_id:
      item.dataset_id ||
      plan.dataset_id ||
      item.registration_receipt?.dataset_id ||
      "",
    registry_id: item.registry_id || item.registration_receipt?.registry_id || "",
    manifest_id: item.manifest_id || item.registration_receipt?.manifest_id || "",
  };
}

/**
 * History ledger often omits source_id/connector_id; jobs carry them.
 * Only fill empty identity fields from a matching job — never overwrite or invent.
 */
export function enrichHistoryEventsFromJobs(events = [], jobs = []) {
  if (!events?.length || !jobs?.length) return events || [];
  const byId = new Map();
  for (const job of jobs) {
    const id = String(job?.id || "").trim();
    if (id) byId.set(id, job);
  }
  return events.map((event) => {
    const jobId = String(event?.job_id || event?.meta?.job_id || "").trim();
    const job = jobId ? byId.get(jobId) : null;
    if (!job) return event;
    const fromJob = pickIdentity(
      {
        job_id: jobId,
        candidate_key: job.candidate_key,
        source_id: job.source_id,
        connector_id: job.connector_id || job.desk_connector_id,
        dataset_id: job.registered_dataset_id || job.dataset_id,
      },
      { ...(job.request || {}), ...(job.plan || {}) },
    );
    const meta = { ...(event.meta || {}) };
    const next = { ...event, meta };
    for (const key of ["candidate_key", "source_id", "connector_id", "dataset_id", "job_id"]) {
      const value = fromJob[key];
      if (!value) continue;
      if (!next[key]) next[key] = value;
      if (!meta[key]) meta[key] = value;
    }
    return next;
  });
}

export function durableHistoryToEvents(data) {
  const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
  return items
    .filter((item) => item && (item.id || item.title))
    .map((item) => {
      const identity = pickIdentity(item, item.plan || item.request || {});
      const archiveVerified =
        item.archive_verified ?? item.registration_receipt?.archive_verified ?? null;
      const registryReadback =
        item.registry_readback ?? item.registration_receipt?.registry_readback ?? null;
      const vaultPath = item.vault_path || item.registration_receipt?.vault_path || "";
      const readiness = item.readiness || item.registration_receipt?.readiness || item.status || "";
      return {
        id: item.id,
        ts: item.updated_at || item.created_at || "",
        action: item.kind || "discover",
        target: item.title || item.summary || item.id,
        meta: {
          status: item.status,
          kind: item.kind,
          summary: item.summary,
          readiness,
          query_ready: item.query_ready,
          cadence: item.cadence,
          requested_schedule: item.requested_schedule,
          execution_mode: item.execution_mode,
          archive_verified: archiveVerified,
          registry_readback: registryReadback,
          vault_path: vaultPath,
          usable: item.usable,
          catalog_reconciliation: item.catalog_reconciliation || null,
          registration_receipt: item.registration_receipt || null,
          ...identity,
        },
        durable: true,
        status: item.status,
        kind: item.kind,
        summary: item.summary,
        cadence: item.cadence,
        requested_schedule: item.requested_schedule,
        candidate_key: identity.candidate_key,
        source_id: identity.source_id,
        connector_id: identity.connector_id,
        job_id: identity.job_id,
        dataset_id: identity.dataset_id,
        archive_verified: archiveVerified,
        registry_readback: registryReadback,
        catalog_reconciliation: item.catalog_reconciliation || null,
      };
    });
}

export function mergeHistoryEvents(durableEvents = [], deskEvents = []) {
  const seen = new Set();
  const out = [];
  for (const event of [...durableEvents, ...deskEvents]) {
    if (!event) continue;
    const key = String(event.id || `${event.ts}:${event.action}:${event.target}`).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(event);
  }
  return out.sort((a, b) => String(b.ts || "").localeCompare(String(a.ts || "")));
}

/** Resolve the Discover History row that corresponds to a desk job, if any. */
export function historyEventForJob(events = [], job = null) {
  if (!job) return null;
  const jobId = String(job.id || "").trim();
  if (!jobId) return null;
  const match = (events || []).find((event) => {
    const metaId = String(event?.meta?.job_id || event?.job_id || "").trim();
    const eventId = String(event?.id || "").trim();
    return metaId === jobId || eventId === jobId || eventId === `job-${jobId}`;
  });
  if (match) return match;
  const plan = job.plan || {};
  const identity = pickIdentity(
    {
      job_id: jobId,
      candidate_key: plan.candidate_key || job.request?.candidate_key,
      source_id: plan.source_id,
      connector_id: plan.connector_id || plan.catalog_connector_id || job.request?.connector_id,
      dataset_id: plan.dataset_id,
    },
    plan,
  );
  const syntheticId = jobId.startsWith("job-") ? jobId : `job-${jobId}`;
  return {
    id: syntheticId,
    ts: job.updated_at || job.created_at || "",
    action: "collection_run",
    target: plan.title || job.title || job.name || jobId,
    status: job.status || job.state || "",
    durable: true,
    kind: "collection_run",
    meta: {
      job_id: identity.job_id,
      status: job.status || job.state || "",
      candidate_key: identity.candidate_key,
      source_id: identity.source_id,
      connector_id: identity.connector_id,
      dataset_id: identity.dataset_id,
    },
    summary: String(job.status || job.state || "collection").replace(/_/g, " "),
    candidate_key: identity.candidate_key,
    source_id: identity.source_id,
    connector_id: identity.connector_id,
    job_id: identity.job_id,
    dataset_id: identity.dataset_id,
  };
}

/**
 * Faculty holding truth for a History event.
 * Never promotes receipt_only / query_allowed:false to query-ready.
 * collected ≠ registered ≠ query-ready.
 */
export function historyHoldingTruth(event = null) {
  const meta = event?.meta || {};
  const datasetId = meta.dataset_id || event?.dataset_id || "";
  const jobId = meta.job_id || event?.job_id || "";
  const candidateKey = meta.candidate_key || event?.candidate_key || "";
  const sourceId = meta.source_id || event?.source_id || "";
  const connectorId = meta.connector_id || event?.connector_id || "";
  const recon = meta.catalog_reconciliation || event?.catalog_reconciliation || null;
  const receiptOnly = isReceiptOnlyAsset({ catalog_reconciliation: recon });
  const status = String(meta.status || event?.status || "").toLowerCase();
  const readiness = String(meta.readiness || "").toLowerCase();
  const collected = Boolean(
    jobId ||
      event?.kind === "collection_run" ||
      event?.action === "collection_run" ||
      /pending_approval|queued|running|completed|cancelled|failed/.test(status),
  );

  const asDataset = datasetId
    ? {
        dataset_id: datasetId,
        analysis_readiness: readiness || status,
        catalog_reconciliation: recon,
      }
    : null;
  const pill = asDataset ? statusPillKind(asDataset) : null;
  const queryReady = Boolean(pill && pill.kind === "query-ready");
  const completedOnly = Boolean(
    datasetId &&
      !queryReady &&
      !receiptOnly &&
      (pill?.kind === "completed" ||
        readiness === "completed" ||
        readiness === "complete" ||
        status === "completed"),
  );
  const registered = Boolean(
    datasetId &&
      !completedOnly &&
      (receiptOnly ||
        pill?.kind === "registered" ||
        pill?.kind === "query-ready" ||
        /register|registered|query_ready/.test(status) ||
        meta.query_ready === true ||
        isQueryReadyReadiness(readiness)),
  );

  let label = "Recorded";
  if (queryReady) label = "Query-ready";
  else if (receiptOnly) label = "Registered · reconciliation pending";
  else if (registered) label = "Registered";
  else if (completedOnly) label = "Completed";
  else if (/pending_approval|ready_for_review|awaiting|needs_approval/.test(status)) {
    label = "Needs approval";
  } else if (/queued|running|active|in_progress/.test(status)) {
    label = status === "running" ? "Collecting" : "Active";
  } else if (/failed|error|needs_recovery|blocked/.test(status)) {
    label = "Needs recovery";
  } else if (collected) {
    label = "Collected";
  }

  return {
    collected,
    registered: Boolean(registered || queryReady),
    completed: completedOnly,
    queryReady,
    receiptOnly,
    label,
    datasetId,
    jobId,
    candidateKey,
    sourceId,
    connectorId,
    /** Explicit triad — never collapse these in UI copy. */
    stages: {
      collected,
      registered: Boolean(registered || queryReady || receiptOnly || completedOnly),
      completed: completedOnly,
      queryReady,
    },
  };
}

/** Library / Explore handoff payload — preserves identities without inventing readiness. */
export function historyLibraryHandoff(event = null) {
  const truth = historyHoldingTruth(event);
  const meta = event?.meta || {};
  if (!truth.datasetId) return null;
  return {
    dataset_id: truth.datasetId,
    candidate_key: truth.candidateKey || undefined,
    source_id: truth.sourceId || undefined,
    connector_id: truth.connectorId || undefined,
    job_id: truth.jobId || undefined,
    catalog_reconciliation: meta.catalog_reconciliation || undefined,
    analysis_readiness: truth.queryReady
      ? "query_ready"
      : truth.completed
        ? "completed"
        : truth.registered || truth.receiptOnly
          ? "registered"
          : meta.readiness || undefined,
  };
}

export function historyLifecycleBucket(event) {
  const truth = historyHoldingTruth(event);
  const status = String(event?.status || event?.meta?.status || "").toLowerCase();
  const kind = String(event?.kind || event?.action || "").toLowerCase();
  // Refresh subscriptions are scheduled records even when status is "active".
  if (
    kind === "subscription" ||
    kind === "refresh_subscription" ||
    /scheduled|paused|subscription/.test(status)
  ) {
    return "scheduled";
  }
  if (/pending_approval|ready_for_review|awaiting|needs_approval/.test(status)) return "needs_approval";
  if (/cancelled|canceled/.test(status)) return "ready";
  if (/queued|running|active|in_progress/.test(status)) return "active";
  if (/failed|error|needs_recovery|blocked/.test(status)) return "needs_recovery";
  // Lifecycle "ready" means acquisition finished — not necessarily query-ready.
  if (
    truth.stages.registered ||
    truth.queryReady ||
    /completed|ready|registered|archived|done|succeeded|query_ready/.test(status)
  ) {
    return "ready";
  }
  return "all";
}
