/**
 * Normalize heterogeneous YZU worker/job payloads into one additive execution contract.
 *
 * The shape is intentionally compatible with OpenLineage-style run events without
 * requiring OpenLineage or a new orchestrator. Existing API payloads remain valid;
 * richer backends may add lifecycle/events/worker/output fields incrementally.
 */

const STAGE_ALIASES = new Map([
  ["pending_approval", "pending_approval"],
  ["needs_approval", "pending_approval"],
  ["approval_required", "pending_approval"],
  ["submitted", "queued"],
  ["pending", "queued"],
  ["queued", "queued"],
  ["assigned", "assigned"],
  ["claimed", "assigned"],
  ["starting", "assigned"],
  ["retrying", "retrying"],
  ["retry_scheduled", "retrying"],
  ["running", "running"],
  ["executing", "running"],
  ["collecting", "running"],
  ["validating", "validating"],
  ["verifying", "validating"],
  ["testing", "validating"],
  ["archiving", "archiving"],
  ["uploading", "archiving"],
  ["registering", "registering"],
  ["materializing", "registering"],
  ["materialising", "registering"],
  ["registered", "registered"],
  ["query_ready", "registered"],
  ["materialized", "registered"],
  ["materialised", "registered"],
  ["completed", "completed"],
  ["complete", "completed"],
  ["succeeded", "completed"],
  ["success", "completed"],
  ["blocked", "blocked"],
  ["stalled", "blocked"],
  ["paused", "blocked"],
  ["cancelled", "blocked"],
  ["canceled", "blocked"],
  ["failed", "failed"],
  ["error", "failed"],
]);

const STAGE_LABELS = {
  pending_approval: "pending approval",
  queued: "queued",
  assigned: "assigned",
  retrying: "retrying",
  running: "running",
  validating: "validating",
  archiving: "archiving",
  registering: "registering",
  registered: "registered",
  completed: "completed",
  blocked: "blocked",
  failed: "failed",
  unknown: "unknown",
};

const STAGE_PRIORITY = {
  pending_approval: 0,
  failed: 0,
  blocked: 0,
  retrying: 1,
  running: 1,
  validating: 1,
  archiving: 1,
  registering: 1,
  assigned: 2,
  queued: 3,
  unknown: 4,
  completed: 9,
  registered: 9,
};

const VISIBLE_STAGES = new Set([
  "pending_approval",
  "queued",
  "assigned",
  "retrying",
  "running",
  "validating",
  "archiving",
  "registering",
  "blocked",
  "failed",
]);

const TERMINAL_STAGES = new Set(["registered", "completed", "blocked", "failed"]);

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}

function identifier(value) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (!value || typeof value !== "object") return null;
  return firstValue(value.dataset_id, value.asset_id, value.id, value.name, value.uri, value.path) || null;
}

function eventTimestamp(event) {
  return firstValue(event?.ts, event?.timestamp, event?.at, event?.event_time, event?.created_at) || null;
}

function latestEvent(events) {
  if (!events.length) return null;
  return events.reduce((latest, event) => {
    const currentTs = Date.parse(eventTimestamp(event) || "");
    const latestTs = Date.parse(eventTimestamp(latest) || "");
    if (Number.isFinite(currentTs) && (!Number.isFinite(latestTs) || currentTs > latestTs)) return event;
    return latest;
  }, events[events.length - 1]);
}

function normalizeStage(rawStage) {
  const key = String(rawStage || "unknown").trim().toLowerCase().replace(/[\s-]+/g, "_");
  return STAGE_ALIASES.get(key) || (key || "unknown");
}

function normalizeProgress(job) {
  const progress = firstValue(job?.lifecycle?.progress, job?.execution?.progress, job?.progress);
  if (typeof progress === "number" && Number.isFinite(progress)) {
    return Math.max(0, Math.min(100, Math.round(progress)));
  }
  if (progress && typeof progress === "object") {
    const pct = firstValue(progress.pct, progress.percent, progress.percentage);
    if (Number.isFinite(Number(pct))) return Math.max(0, Math.min(100, Math.round(Number(pct))));
    const current = Number(firstValue(progress.current, progress.completed, progress.done));
    const total = Number(firstValue(progress.total, progress.expected));
    if (Number.isFinite(current) && Number.isFinite(total) && total > 0) {
      return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
    }
  }
  return null;
}

function workerLabel(job) {
  const worker = firstValue(
    job?.lifecycle?.worker,
    job?.execution?.worker,
    job?.assigned_worker,
    job?.worker,
    job?.worker_id,
    job?.host,
  );
  if (typeof worker === "string" || typeof worker === "number") return String(worker);
  if (worker && typeof worker === "object") {
    return firstValue(worker.label, worker.name, worker.id, worker.host, worker.hostname) || null;
  }
  const pool = firstValue(job?.worker_pool, job?.pool, job?.execution?.pool);
  return pool ? String(pool) : null;
}

function truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return /^(true|yes|verified|registered|ready|ok|success)$/i.test(value.trim());
  return false;
}

function countValue(...values) {
  const value = Number(firstValue(...values));
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function normalizeExecutionLifecycle(job = {}) {
  const events = [
    ...toArray(job?.lifecycle?.events),
    ...toArray(job?.execution?.events),
    ...toArray(job?.events),
  ].filter((event) => event && typeof event === "object");
  const latest = latestEvent(events);
  const rawStage = firstValue(
    job?.lifecycle?.stage,
    job?.execution?.stage,
    latest?.stage,
    latest?.event_type,
    latest?.type,
    job?.stage,
    job?.status,
    job?.state,
  );
  const stage = normalizeStage(rawStage);
  const worker = workerLabel(job);
  const attempt = Number(firstValue(job?.attempt, job?.execution?.attempt, job?.lifecycle?.attempt));
  const inputs = toArray(firstValue(job?.lifecycle?.inputs, job?.execution?.inputs, job?.inputs))
    .map(identifier)
    .filter(Boolean);
  const outputs = toArray(firstValue(job?.lifecycle?.outputs, job?.execution?.outputs, job?.outputs, job?.artifacts))
    .map(identifier)
    .filter(Boolean);
  const progress = normalizeProgress(job);
  const latestLabel = firstValue(latest?.label, latest?.message, latest?.event_type, latest?.type);
  const manifestId = firstValue(
    job?.manifest_id,
    job?.manifest?.id,
    job?.lifecycle?.manifest_id,
    job?.execution?.manifest_id,
    job?.registration?.manifest_id,
  );
  const archiveVerified = truthy(
    firstValue(
      job?.archive_verified,
      job?.drive_verified,
      job?.lifecycle?.archive_verified,
      job?.execution?.archive_verified,
      job?.registration?.archive_verified,
    ),
  );
  const registryVerified =
    stage === "registered" ||
    truthy(
      firstValue(
        job?.registry_verified,
        job?.registered,
        job?.lifecycle?.registry_verified,
        job?.execution?.registry_verified,
        job?.registration?.registry_verified,
      ),
    );
  const registrationId = firstValue(
    job?.registration_id,
    job?.registry_id,
    job?.lifecycle?.registration_id,
    job?.execution?.registration_id,
    job?.registration?.id,
  );
  const error = firstValue(job?.error, job?.error_message, job?.lifecycle?.error, job?.execution?.error, latest?.error);
  const retryable = truthy(firstValue(job?.retryable, job?.lifecycle?.retryable, job?.execution?.retryable));
  const detail = [
    worker ? `worker ${worker}` : null,
    Number.isFinite(attempt) && attempt > 1 ? `attempt ${attempt}` : null,
    outputs.length ? `${outputs.length} output${outputs.length === 1 ? "" : "s"}` : null,
    manifestId ? "manifest recorded" : null,
    latestLabel && normalizeStage(latestLabel) !== stage ? String(latestLabel).replace(/_/g, " ") : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    stage,
    label: STAGE_LABELS[stage] || stage.replace(/_/g, " "),
    priority: STAGE_PRIORITY[stage] ?? STAGE_PRIORITY.unknown,
    visible: VISIBLE_STAGES.has(stage),
    terminal: TERMINAL_STAGES.has(stage),
    ok: !["failed", "blocked", "pending_approval"].includes(stage),
    warn: ["failed", "blocked", "pending_approval"].includes(stage),
    progress,
    detail: detail || null,
    error: error ? String(error) : null,
    retryable,
    proof: {
      run_id: String(firstValue(job?.run_id, job?.lifecycle?.run_id, job?.execution?.run_id, job?.job_id, job?.id) || ""),
      worker,
      pool: firstValue(job?.worker_pool, job?.pool, job?.execution?.pool, job?.lifecycle?.pool) || null,
      attempt: Number.isFinite(attempt) ? attempt : null,
      heartbeat_at: firstValue(job?.heartbeat_at, job?.lifecycle?.heartbeat_at, job?.execution?.heartbeat_at) || null,
      started_at: firstValue(job?.started_at, job?.lifecycle?.started_at, job?.execution?.started_at) || null,
      finished_at: firstValue(job?.finished_at, job?.completed_at, job?.lifecycle?.finished_at, job?.execution?.finished_at) || null,
      latest_event_at: eventTimestamp(latest),
      event_count: events.length,
      inputs,
      outputs,
      manifest_id: manifestId || null,
      registration_id: registrationId || null,
      archive_verified: archiveVerified,
      registry_verified: registryVerified,
      rows: countValue(job?.rows, job?.row_count, job?.execution?.rows, job?.lifecycle?.rows),
      fields: countValue(job?.fields, job?.field_count, job?.execution?.fields, job?.lifecycle?.fields),
      entities: countValue(job?.entities, job?.entity_count, job?.execution?.entities, job?.lifecycle?.entities),
    },
  };
}

export function normalizeSynthesisExecution(thread = {}) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const spec = state.execution_spec || execution.execution_spec || {};
  const materialisation = firstValue(thread?.materialisation, state?.materialisation, execution?.materialisation);
  const registered = normalizeStage(materialisation) === "registered" || normalizeStage(execution?.status) === "registered";
  const status = registered ? "registered" : firstValue(execution?.status, materialisation, "unknown");
  const outputId = firstValue(execution?.output_dataset_id, spec?.output_dataset_id);
  const inputIds = firstValue(execution?.inputs, spec?.input_dataset_ids, spec?.input_dataset_id);

  return normalizeExecutionLifecycle({
    ...execution,
    id: firstValue(execution?.job_id, execution?.run_id, thread?.id),
    job_id: firstValue(execution?.job_id, execution?.run_id),
    status,
    inputs: inputIds,
    outputs: firstValue(execution?.outputs, outputId),
    manifest_id: firstValue(execution?.manifest_id, state?.manifest_id),
    drive_verified: firstValue(execution?.drive_verified, execution?.archive_verified),
    registry_verified: registered,
    registration_id: firstValue(execution?.registration_id, execution?.registry_id, outputId),
  });
}

export function isExecutionVisible(job) {
  return normalizeExecutionLifecycle(job).visible;
}

export function executionSortPriority(job) {
  return normalizeExecutionLifecycle(job).priority;
}
