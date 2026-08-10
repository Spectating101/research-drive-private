/**
 * Classify structured Ask failures/acknowledgements into recoverable UI states.
 *
 * Assistant prose is not a control protocol. This helper only accepts explicit
 * backend fields, so a model mentioning a provider or saying "context received"
 * cannot accidentally change the UI state.
 */

function textOf(value) {
  return String(value || "").trim();
}

const PROVIDER_CODES = new Set([
  "CAPABILITY_UNAVAILABLE",
  "PROVIDER_UNAVAILABLE",
  "PROVIDER_NOT_LINKED",
  "ASSISTANT_UNAVAILABLE",
]);
const PROVIDER_ACTIONS = new Set(["composer_unavailable", "composer_error", "composer_timeout"]);
const NON_ANSWER_STATUSES = new Set(["context_ack", "not_grounded", "no_answer"]);

/**
 * @param {{ action?: string, errorCode?: string, error_code?: string, error?: Error, recoveryKind?: string, recovery_kind?: string, kind?: string, answerStatus?: string, answer_status?: string, entityKind?: string }} input
 * @returns {null | { kind: string, title: string, detail: string, recoverable: true, retryPrompt?: string }}
 */
export function classifyAskRecovery(input = {}) {
  const entityKind = textOf(input.entityKind);
  const isSynthesis = entityKind === "synthesis_thread";
  const code = textOf(input.errorCode || input.error_code || input.error?.code).toUpperCase();
  const action = textOf(input.action || input.error?.action).toLowerCase();
  const recoveryKind = textOf(input.recoveryKind || input.recovery_kind || input.kind).toLowerCase();
  const answerStatus = textOf(input.answerStatus || input.answer_status).toLowerCase();

  if (PROVIDER_CODES.has(code) || PROVIDER_ACTIONS.has(action) || recoveryKind === "provider_unavailable") {
    return {
      kind: "provider",
      title: "Assistant provider is unavailable",
      detail:
        "The research objective is preserved on this thread. Reconnect or configure the assistant provider, then retry from the same conversation.",
      recoverable: true,
      retryPrompt: isSynthesis
        ? "Retry interpreting this Synthesis objective with the attached thread context."
        : "Retry the previous question with the attached research context.",
    };
  }

  if (isSynthesis && NON_ANSWER_STATUSES.has(answerStatus)) {
    return {
      kind: "plumbing",
      title: "No grounded interpretation yet",
      detail:
        "The desk acknowledged the thread but did not return a research answer. Keep this objective and retry the conversation.",
      recoverable: true,
      retryPrompt: "Interpret this research objective and propose the smallest defensible construction.",
    };
  }

  return null;
}
