/** Normalize chat complete payloads into renderable artifact blocks. */

function rowsFromSearchBlock(block) {
  if (!block || typeof block !== "object") return [];
  if (Array.isArray(block.rows)) return block.rows;
  if (Array.isArray(block.sections)) {
    return block.sections.flatMap((s) => (Array.isArray(s?.rows) ? s.rows : []));
  }
  return [];
}

export function extractAskArtifacts(message) {
  if (!message || message.role !== "assistant") {
    return { searchRows: [], probe: null, queryPreview: null, candidates: [] };
  }
  const artifacts = message.artifacts || {};
  const searchBlock = artifacts.search || artifacts.preview?.search || message.search;
  let searchRows = rowsFromSearchBlock(searchBlock);
  if (!searchRows.length && Array.isArray(message.candidates)) {
    searchRows = message.candidates;
  }
  const probe = artifacts.probe || artifacts.connector || message.probe || null;
  const queryBlock = artifacts.query || message.queryPreview;
  const queryPreview =
    queryBlock && (queryBlock.rows || queryBlock.columns)
      ? {
          rows: queryBlock.rows || queryBlock.data || [],
          columns: queryBlock.columns || [],
        }
      : message.preview && message.preview.rows
        ? { rows: message.preview.rows, columns: message.preview.columns || [] }
        : null;
  const candidates = Array.isArray(message.candidates) ? message.candidates : [];
  return { searchRows, probe, queryPreview, candidates };
}

export function rowTitle(row) {
  return (
    row?.title ||
    row?.name ||
    row?.dataset_id ||
    row?.doi ||
    row?.id ||
    "untitled"
  );
}

export function rowKind(row) {
  return row?.kind || row?.source || row?.type || "result";
}

const TERMINAL_JOB = new Set(["completed", "failed", "cancelled", "error"]);

export function isTerminalJobStatus(status) {
  return TERMINAL_JOB.has(String(status || "").toLowerCase());
}

export function jobStatusLabel(status) {
  const s = String(status || "unknown").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Map persisted chat session rows into Ask rail message shape. */
export function mapSessionMessageToUi(row, state = {}) {
  if (!row || row.role === "user") {
    return { role: "user", text: String(row?.content || "") };
  }
  const artifacts = row.artifacts || {};
  const pendingJobId =
    artifacts.job_id ||
    artifacts.pending_job_id ||
    state.pending_job_id ||
    artifacts.collect?.job?.id ||
    null;
  const jobStatus =
    artifacts.job_status ||
    state.job_status ||
    artifacts.collect?.job?.status ||
    (pendingJobId ? "queued" : null);
  return {
    role: "assistant",
    text: String(row.content || ""),
    action: artifacts.action || null,
    artifacts,
    search: artifacts.search,
    probe: artifacts.probe,
    preview: artifacts.preview,
    queryPreview: artifacts.query,
    candidates: artifacts.candidates || [],
    suggestedPrompts: artifacts.suggestions || artifacts.suggested_prompts || [],
    pendingJobId,
    jobStatus,
    composerPending: Boolean(
      artifacts.still_working || artifacts.action === "composer_pending" || state.composer_pending,
    ),
    backgroundCompletion: Boolean(artifacts.background_completion),
    licenseBlocked: Boolean(artifacts.collect?.blocked || artifacts.blocked),
    licenseDoi: artifacts.doi || artifacts.collect?.resolved?.doi || "",
  };
}
