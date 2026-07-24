/**
 * Ask intent → affordance contracts — Phase 1 truth.
 * Status-only turns must not surface Queue DOI / procure / technical tool dumps.
 */

const STATUS_RE =
  /\b(status|health|ping|alive|up\??|ok|okay|are you (up|there|online)|desk status|assistant status)\b/i;
const PROCURE_RE = /\b(collect|procure|queue\s*doi|acquire|download|ingest|approve)\b/i;
const PROCURE_ACTION = new Set([
  "collect",
  "acquire",
  "collect_doi",
  "approve_collect",
  "queue",
  "schedule_refresh",
]);
const TECHNICAL_TOOL_RE = /describe[_ ]?dataset|planning|working|tool[_ ]?call|function[_ ]?call/i;
const PROCURE_PROMPT_RE = /queue\s*doi|collect\s+for|procure|approve\s+job|schedule\s+refresh/i;

export function classifyAskIntent(text) {
  const value = String(text || "").trim();
  if (!value) return "general";
  if (STATUS_RE.test(value) && !PROCURE_RE.test(value)) return "status";
  if (PROCURE_RE.test(value)) return "procure";
  return "general";
}

export function isProcureAction(action) {
  return PROCURE_ACTION.has(String(action || "").toLowerCase());
}

export function isTechnicalToolName(name) {
  return TECHNICAL_TOOL_RE.test(String(name || ""));
}

export function filterSuggestedPromptsForIntent(intent, prompts = []) {
  const list = Array.isArray(prompts) ? prompts.map((p) => String(p || "").trim()).filter(Boolean) : [];
  if (intent !== "status") return list;
  return list.filter((p) => !PROCURE_PROMPT_RE.test(p) && !TECHNICAL_TOOL_RE.test(p));
}

/**
 * Shape an assistant reply for the active user intent.
 */
function filterNextStepsForIntent(intent, steps = []) {
  const list = Array.isArray(steps) ? steps : [];
  if (intent !== "status") return list;
  return list.filter((step) => {
    const label = typeof step === "string"
      ? step
      : `${step?.label || ""} ${step?.prompt || ""}`;
    return !PROCURE_PROMPT_RE.test(label) && !TECHNICAL_TOOL_RE.test(label);
  });
}

export function shapeAskReplyForIntent(intent, reply = {}) {
  if (intent !== "status") return reply;
  const action = isProcureAction(reply.action) ? null : reply.action;
  const toolName = isTechnicalToolName(reply.toolName) ? null : reply.toolName;
  return {
    ...reply,
    action,
    toolName,
    pendingJobId: null,
    jobStatus: null,
    suggestedPrompts: filterSuggestedPromptsForIntent(intent, reply.suggestedPrompts),
    nextSteps: filterNextStepsForIntent(intent, reply.nextSteps),
    // Status answers should not dump Composer phase chrome after completion.
    activityLog: [],
    activity: "",
  };
}
