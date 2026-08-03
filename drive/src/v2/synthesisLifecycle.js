/**
 * Synthesis lifecycle truth labels.
 *
 * These keep the frozen Synthesis state distinctions honest:
 *
 *   accepted method != execution specified != approved execution
 *   completed worker != archive verified != registered != query-ready
 *
 * An execution specification is a plan, not permission. A completed worker
 * build says nothing about archive verification or registry promotion, and
 * registration does not establish query readiness.
 */

function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

function normalizeStatus(status) {
  return text(status).toLowerCase().replace(/-/g, "_");
}

/** Lifecycle states that can only be reached after researcher approval. */
export const POST_APPROVAL_STATUSES = [
  "queued",
  "running",
  "registering",
  "archiving",
  "registered",
  "query_ready",
  "completed",
  "failed",
];

/**
 * Detail line for the Build stage. Never claims approval from the mere
 * presence of an execution specification.
 */
export function buildStageDetail(thread) {
  const state = thread?.state || {};
  const status = normalizeStatus(state.execution?.status);
  if (status === "pending_approval") return "Approval required";
  if (POST_APPROVAL_STATUSES.includes(status)) return "Approved execution";
  if (state.execution_spec) return "Execution specified";
  return "Execution record";
}

/**
 * The five-row execution track. `completed` advances the worker row only —
 * archive/registry remain unverified until an explicit registered or
 * query_ready state, and query readiness is never inferred from registration.
 */
export function executionTrack(status, registered, queryReady = false) {
  const normalized = normalizeStatus(status);
  const approved = POST_APPROVAL_STATUSES.includes(normalized);
  const workerDone = ["registering", "archiving", "registered", "query_ready", "completed"].includes(normalized);
  const archiveDone = ["registered", "query_ready"].includes(normalized);
  const archiveActive = ["registering", "archiving"].includes(normalized);
  return [
    { label: "Method accepted", detail: "Revision bound", state: "done" },
    {
      label: "Researcher approval",
      detail: normalized === "pending_approval" ? "Decision required" : approved ? "Approved" : "Not requested",
      state: normalized === "pending_approval" ? "now" : approved ? "done" : "",
    },
    {
      label: "Worker build",
      detail: normalized === "running"
        ? "Running"
        : normalized === "queued"
          ? "Queued"
          : workerDone
            ? "Completed"
            : normalized === "failed"
              ? "Failed"
              : "Waiting",
      state: ["queued", "running", "failed"].includes(normalized) ? "now" : workerDone ? "done" : "",
    },
    {
      label: "Archive + registry",
      detail: archiveActive
        ? "Verifying"
        : archiveDone
          ? "Verified"
          : normalized === "completed"
            ? "Awaiting verification"
            : "Waiting",
      state: archiveActive ? "now" : archiveDone ? "done" : "",
    },
    {
      label: "Library handoff",
      detail: queryReady
        ? "Query-ready asset"
        : registered
          ? "Registered · query readiness unverified"
          : "Not registered",
      state: registered ? "done" : "",
    },
  ];
}
