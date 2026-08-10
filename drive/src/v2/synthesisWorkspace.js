/**
 * Pure helpers for the agent-led Synthesis centre surface.
 */

export function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

export function titleFor(thread) {
  return text(thread?.title || thread?.state?.title, "Untitled synthesis");
}

export function stateFor(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const lifecycle = text(execution.status || thread?.materialisation).toLowerCase().replace(/-/g, "_");
  if (lifecycle === "query_ready") return "query_ready";
  if (lifecycle === "registered") return "registered";
  if (lifecycle === "failed") return "failed";
  if (execution.status) return "execution";
  if (state.proposal) return "proposal";
  if ((state.nodes || []).length) return "explore";
  return "draft";
}

/** Centre card after a durable thread exists but before evidence/proposal stages. */
export function threadCreatedCardModel(thread) {
  const state = thread?.state || {};
  const objective = text(thread?.objective || state.objective, "Research objective not recorded");
  const grain = text(state.required_grain || state.spec?.grain, "Not inferred yet");
  return {
    eyebrow: "Thread created",
    title: "Research decision started",
    status: text(state.maturityLabel || state.maturity, "Exploring"),
    objective,
    grain,
    nextStep: "Interpret held evidence and draft one recommended construction",
    truth:
      "Nothing has been accepted, executed, or registered. The conversation and this canvas stay attached to the same durable thread.",
  };
}

/**
 * User-facing execution action. Backend may still move through pending_approval;
 * the desk exposes one material approval boundary.
 */
export function executionPrimaryAction(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const mode = stateFor(thread);
  const queryReady = mode === "query_ready";
  const registered = mode === "registered" || queryReady;
  const failed = execution.status === "failed";
  const hasSpec = Boolean(state.execution_spec?.input_dataset_id && state.execution_spec?.output_dataset_id);
  const awaitingApproval = execution.status === "pending_approval" && Boolean(execution.job_id);
  const idleReady = hasSpec && !execution.status;

  if (registered) return { kind: "open_library", label: "Open in Library" };
  if (failed || !hasSpec) return null;
  if (awaitingApproval || idleReady) return { kind: "approve_and_run", label: "Approve and run" };
  return null;
}
