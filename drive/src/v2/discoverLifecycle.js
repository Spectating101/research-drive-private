/**
 * Discover acquisition lifecycle authority (A1).
 *
 * Backend status inventory (YzuJobStore / orchestrator — do not invent strings):
 *
 * | backend status      | meaning                                      | terminal? | user lifecycle              | evidence |
 * |---------------------|----------------------------------------------|-----------|-----------------------------|---------|
 * | pending_approval    | waiting for approve before worker            | no        | approval-required           | status  |
 * | queued              | approved; waiting for worker                 | no        | queued                      | status  |
 * | running             | worker claimed / execute_job                 | no        | running                     | status; optional result stage fields |
 * | failed              | execute error or stale recovery              | yes       | failed                      | status + error |
 * | completed           | executor finished                            | yes       | completed-unregistered OR registered | status + registered_dataset_id |
 * | cancelled           | user cancel while pending/queued             | yes       | (not a Discover UI state)   | status  |
 *
 * Query-ready is NEVER a job status. It requires the registered dataset
 * (catalog / labIds) to satisfy isQueryReady().
 *
 * Linkage: exact candidate_key or exact connector_id only (jobMatchesCandidate).
 * No title matching.
 */

import { candidateKey, jobMatchesCandidate } from "./candidateKey.js";
import { isQueryReady, TAXONOMY } from "./discoverTaxonomy.js";

export const LIFECYCLE = {
  SUBMITTING: "submitting",
  APPROVAL_REQUIRED: "approval-required",
  QUEUED: "queued",
  RUNNING: "running",
  FAILED: "failed",
  COMPLETED_UNREGISTERED: "completed-unregistered",
  REGISTERED: "registered",
  QUERY_READY: "query-ready",
};

const ACTIVE = new Set(["pending_approval", "queued", "running"]);
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function trim(value) {
  return String(value ?? "").trim();
}

function jobStatus(job) {
  return String(job?.status || "").toLowerCase();
}

function jobTime(job) {
  const raw = job?.updated_at || job?.updatedAt || job?.created_at || job?.createdAt || 0;
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

/**
 * Exact-linked jobs for a candidate. No title matching.
 */
export function exactJobsForCandidate(row, jobs = []) {
  if (!row || !Array.isArray(jobs)) return [];
  return jobs.filter((j) => jobMatchesCandidate(j, row));
}

/**
 * Prefer active nonterminal exact job; else newest exact terminal job.
 * Among ties, newest by updated_at/created_at.
 */
export function selectLifecycleJob(row, jobs = []) {
  const exact = exactJobsForCandidate(row, jobs);
  if (!exact.length) return null;

  const active = exact
    .filter((j) => ACTIVE.has(jobStatus(j)))
    .sort((a, b) => jobTime(b) - jobTime(a));
  if (active.length) return active[0];

  const terminal = exact
    .filter((j) => TERMINAL.has(jobStatus(j)) && jobStatus(j) !== "cancelled")
    .sort((a, b) => jobTime(b) - jobTime(a));
  return terminal[0] || null;
}

function registeredId(job) {
  return trim(
    job?.registered_dataset_id ||
      job?.result?.registered_dataset_id ||
      (Array.isArray(job?.result?.registry_promotion)
        ? job.result.registry_promotion.find((p) => p?.dataset_id)?.dataset_id
        : "") ||
      "",
  );
}

function outputManifestId(job) {
  return trim(
    job?.output_manifest_id ||
      job?.result?.output_manifest_id ||
      job?.result?.manifest_id ||
      job?.result?.materialized?.manifest_id ||
      "",
  );
}

function connectorIdOf(job, row) {
  return trim(
    job?.connector_id ||
      job?.request?.connector_id ||
      job?.plan?.connector_id ||
      row?.connector_id ||
      row?.probe_connector_id ||
      row?.connector?.connector_id ||
      row?.connector?.id ||
      "",
  );
}

function findRegisteredDataset(registeredDatasetId, catalog = []) {
  if (!registeredDatasetId || !Array.isArray(catalog)) return null;
  return catalog.find((d) => d?.dataset_id === registeredDatasetId) || null;
}

function runningEvidence(job) {
  const evidence = [];
  const result = job?.result || {};
  const stage =
    result.stage ||
    result.current_stage ||
    result.progress?.stage ||
    result.status_detail ||
    "";
  if (trim(stage)) evidence.push({ label: "Stage", value: String(stage) });

  const files = result.files_processed ?? result.items_processed ?? result.progress?.files;
  if (files != null && files !== "") evidence.push({ label: "Processed", value: String(files) });

  const rows = result.rows_written ?? result.artifacts_written ?? result.progress?.rows;
  if (rows != null && rows !== "") evidence.push({ label: "Written", value: String(rows) });

  const bytes = result.bytes ?? result.bytes_written ?? result.progress?.bytes;
  if (bytes != null && bytes !== "") evidence.push({ label: "Bytes", value: String(bytes) });

  const source = result.current_source || result.source_url || "";
  if (trim(source)) evidence.push({ label: "Source", value: String(source) });

  const updated = job?.updated_at || job?.updatedAt || "";
  if (trim(updated)) evidence.push({ label: "Last update", value: String(updated) });

  // Never invent percentage from stage count.
  return evidence;
}

function failureSummary(job) {
  const err = trim(job?.error);
  if (err) return err.length > 180 ? `${err.slice(0, 179).trim()}…` : err;
  const events = Array.isArray(job?.events) ? job.events : [];
  const errorEvent = [...events].reverse().find((e) => /error/i.test(String(e?.level || "")));
  if (errorEvent?.message) return String(errorEvent.message);
  return "Collection failed. Review the job in Resources for details.";
}

/**
 * Classify one exact job (+ optional catalog) into a user lifecycle state.
 */
export function classifyJobLifecycle(job, { catalog = [], labIds = null } = {}) {
  if (!job) return null;
  const status = jobStatus(job);
  const regId = registeredId(job);
  const manifestId = outputManifestId(job);

  if (status === "pending_approval") {
    return {
      state: LIFECYCLE.APPROVAL_REQUIRED,
      label: "Approval required",
      explanation: "This collection plan is waiting for approval before work begins.",
      primaryAction: { id: "review_approval", label: "Review approval" },
      secondaryActions: [{ id: "track_resources", label: "Track in Resources" }],
      evidence: [],
      registeredDatasetId: regId || null,
      outputManifestId: manifestId || null,
      terminal: false,
    };
  }
  if (status === "queued") {
    return {
      state: LIFECYCLE.QUEUED,
      label: "Queued",
      explanation: "This collection request is queued and waiting for a worker.",
      primaryAction: { id: "track_resources", label: "Track in Resources" },
      secondaryActions: [],
      evidence: [],
      registeredDatasetId: regId || null,
      outputManifestId: manifestId || null,
      terminal: false,
    };
  }
  if (status === "running") {
    return {
      state: LIFECYCLE.RUNNING,
      label: "Running",
      explanation: "Collection is running.",
      primaryAction: { id: "track_resources", label: "Track in Resources" },
      secondaryActions: [],
      evidence: runningEvidence(job),
      registeredDatasetId: regId || null,
      outputManifestId: manifestId || null,
      terminal: false,
    };
  }
  if (status === "failed") {
    return {
      state: LIFECYCLE.FAILED,
      label: "Failed",
      explanation: failureSummary(job),
      primaryAction: { id: "track_resources", label: "Track in Resources" },
      secondaryActions: [{ id: "ask", label: "Ask about this source" }],
      evidence: trim(job?.updated_at)
        ? [{ label: "Last attempt", value: String(job.updated_at) }]
        : [],
      registeredDatasetId: regId || null,
      outputManifestId: manifestId || null,
      terminal: true,
      failureDetail: trim(job?.error) || "",
    };
  }
  if (status === "completed") {
    if (!regId) {
      return {
        state: LIFECYCLE.COMPLETED_UNREGISTERED,
        label: "Collection complete · Registration pending",
        explanation:
          "Collection finished, but the output is not yet registered as a reusable Library dataset.",
        primaryAction: { id: "track_resources", label: "Track in Resources" },
        secondaryActions: [],
        evidence: [],
        registeredDatasetId: null,
        outputManifestId: manifestId || null,
        terminal: true,
      };
    }
    const dataset = findRegisteredDataset(regId, catalog);
    const ready = dataset ? isQueryReady(dataset) : false;
    // Also accept lab membership + readiness when catalog row missing but flags on job.result
    const resultReady =
      job?.result?.query_ready === true ||
      /instant|query_ready|queryable/i.test(String(job?.result?.analysis_readiness || ""));
    if (ready || resultReady) {
      return {
        state: LIFECYCLE.QUERY_READY,
        label: "In Library · Query ready",
        explanation: "The collected output is registered and can be queried in the Library.",
        primaryAction: { id: "open_library", label: "Open in Library" },
        secondaryActions: [{ id: "track_resources", label: "Track in Resources" }],
        evidence: [{ label: "Dataset", value: regId }],
        registeredDatasetId: regId,
        outputManifestId: manifestId || null,
        terminal: true,
      };
    }
    return {
      state: LIFECYCLE.REGISTERED,
      label: "Registered in Library",
      explanation: "The collected output now has a Library dataset record.",
      primaryAction: { id: "open_library", label: "Open in Library" },
      secondaryActions: [{ id: "track_resources", label: "Track in Resources" }],
      evidence: [{ label: "Dataset", value: regId }],
      registeredDatasetId: regId,
      outputManifestId: manifestId || null,
      terminal: true,
    };
  }
  return null;
}

/**
 * Full lifecycle model for a Discover candidate.
 * @param {object} opts
 * @param {object} opts.row
 * @param {object[]} opts.jobs
 * @param {object[]} [opts.catalog]
 * @param {Set|null} [opts.labIds]
 * @param {boolean} [opts.submitting]
 * @param {boolean} [opts.refreshFailed]
 * @param {object|null} [opts.lastKnown] previous lifecycle model to preserve on refresh failure
 */
export function buildDiscoverLifecycle({
  row,
  jobs = [],
  catalog = [],
  labIds = null,
  submitting = false,
  refreshFailed = false,
  lastKnown = null,
} = {}) {
  if (submitting) {
    return {
      state: LIFECYCLE.SUBMITTING,
      label: "Submitting collection…",
      explanation: "Sending the collection request. Waiting for the job record.",
      job: null,
      candidateKey: candidateKey(row),
      connectorId: connectorIdOf(null, row) || null,
      registeredDatasetId: null,
      outputManifestId: null,
      primaryAction: null,
      secondaryActions: [],
      evidence: [],
      terminal: false,
      refreshFailed: false,
      stages: ["submitted"],
    };
  }

  const job = selectLifecycleJob(row, jobs);
  const scopedLast =
    lastKnown &&
    row &&
    lastKnown.candidateKey &&
    lastKnown.candidateKey === candidateKey(row)
      ? lastKnown
      : null;

  if (!job) {
    if (refreshFailed && scopedLast) {
      return { ...scopedLast, refreshFailed: true };
    }
    return null;
  }

  const classified = classifyJobLifecycle(job, { catalog, labIds });
  if (!classified) {
    if (refreshFailed && scopedLast) {
      return { ...scopedLast, refreshFailed: true };
    }
    return null;
  }

  const stages = lifecycleStagesReached(classified.state);

  return {
    ...classified,
    job,
    candidateKey: candidateKey(row),
    connectorId: connectorIdOf(job, row) || null,
    refreshFailed: Boolean(refreshFailed),
    stages,
  };
}

/**
 * Candidate lifecycle path stages reached from actual state evidence only.
 * Submitted → Approval/Queue → Running → Registered (query-ready is readiness handoff).
 */
export function lifecycleStagesReached(state) {
  const submitted = ["submitted"];
  switch (state) {
    case LIFECYCLE.SUBMITTING:
      return submitted;
    case LIFECYCLE.APPROVAL_REQUIRED:
      return [...submitted, "approval"];
    case LIFECYCLE.QUEUED:
      return [...submitted, "queue"];
    case LIFECYCLE.RUNNING:
      return [...submitted, "queue", "running"];
    case LIFECYCLE.FAILED:
      return [...submitted, "queue", "running", "failed"];
    case LIFECYCLE.COMPLETED_UNREGISTERED:
      return [...submitted, "queue", "running", "complete"];
    case LIFECYCLE.REGISTERED:
    case LIFECYCLE.QUERY_READY:
      return [...submitted, "queue", "running", "registered"];
    default:
      return submitted;
  }
}

export function isLifecycleActive(lifecycle) {
  if (!lifecycle) return false;
  return !lifecycle.terminal && lifecycle.state !== LIFECYCLE.SUBMITTING;
}

/**
 * Usability/readiness projection for terminal registered/query-ready handoffs.
 * Preserves canonical candidate_key / source identity; stamps discover_taxonomy only.
 */
export function projectDiscoverCandidateLifecycle(row, lifecycle) {
  if (!row || !lifecycle) return row;
  const key = candidateKey(row);
  if (lifecycle.candidateKey && key && lifecycle.candidateKey !== key) return row;

  if (lifecycle.state === LIFECYCLE.QUERY_READY) {
    const base = TAXONOMY["local-query-ready"];
    return {
      ...row,
      discover_taxonomy: {
        ...base,
        key: "local-query-ready",
        label: "In Library · Query ready",
        lifecycle_projected: true,
      },
    };
  }
  if (lifecycle.state === LIFECYCLE.REGISTERED) {
    const base = TAXONOMY["local-connected"];
    return {
      ...row,
      discover_taxonomy: {
        ...base,
        key: "local-connected",
        label: "In lab · Registered",
        readiness: "Registered",
        lifecycle_projected: true,
      },
    };
  }
  return row;
}

function lifecycleHandoffUnknowns(state) {
  if (state === LIFECYCLE.QUERY_READY) {
    return [
      "Freshness / last refresh not described",
      "Known caveats not described",
      "Schema details not shown",
      "Coverage completeness not verified",
    ];
  }
  if (state === LIFECYCLE.REGISTERED) {
    return [
      "Instant query path not confirmed",
      "Freshness / last refresh not described",
      "Known caveats not described",
      "Schema details not shown",
      "Coverage completeness not verified",
    ];
  }
  if (state === LIFECYCLE.COMPLETED_UNREGISTERED) {
    return [
      "Registration not complete",
      "Reusable dataset path not yet confirmed",
      "Query readiness not established",
    ];
  }
  return null;
}

/**
 * Apply terminal lifecycle handoff to the Evaluation decision surface.
 * Non-terminal lifecycles leave the evaluation unchanged.
 */
export function applyLifecycleToEvaluation(evaluation, lifecycle) {
  if (!evaluation || !lifecycle) return evaluation;

  if (lifecycle.state === LIFECYCLE.QUERY_READY) {
    return {
      ...evaluation,
      taxonomyKey: "local-query-ready",
      taxonomyLabel: "In Library · Query ready",
      decision: {
        headline: "In Library · Query ready",
        body: "You can query this dataset now.",
      },
      unknowns: lifecycleHandoffUnknowns(LIFECYCLE.QUERY_READY),
    };
  }
  if (lifecycle.state === LIFECYCLE.REGISTERED) {
    return {
      ...evaluation,
      taxonomyKey: "local-connected",
      taxonomyLabel: "In lab · Registered",
      decision: {
        headline: "Registered in Library",
        body: "A Library dataset record exists. Instant query access is not confirmed.",
      },
      unknowns: lifecycleHandoffUnknowns(LIFECYCLE.REGISTERED),
    };
  }
  if (lifecycle.state === LIFECYCLE.COMPLETED_UNREGISTERED) {
    return {
      ...evaluation,
      decision: {
        headline: "Not yet reusable",
        body: "Collection finished, but registration is still pending.",
      },
      unknowns: lifecycleHandoffUnknowns(LIFECYCLE.COMPLETED_UNREGISTERED),
    };
  }
  return evaluation;
}

export function resourceRowForJob(job) {
  if (!job?.id) return null;
  const st = jobStatus(job);
  const title = job.plan?.title || job.title || job.type || "Collection job";
  return {
    section: "Running",
    kind: "active",
    key: `job-${job.id}`,
    label: title,
    metric: st.replace(/_/g, " "),
    ok: st === "completed" || st === "running",
    warn: st === "pending_approval" || st === "queued" || st === "failed",
    job,
  };
}
