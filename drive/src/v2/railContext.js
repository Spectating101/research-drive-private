import { displayName } from "@/v2/datasetMeta";
import { candidateKey } from "@/v2/candidateKey";
import { assetAuthorityContext } from "@/v2/assetAuthority";
import { normalizeSynthesisExecution } from "@/v2/executionLifecycle";

function readinessLabel(dataset) {
  const raw = String(dataset?.analysis_readiness || "").trim();
  if (!raw) return "";
  if (/instant|ready|query/i.test(raw)) return "Query-ready";
  return raw.replace(/_/g, " ");
}

function vaultPath(dataset) {
  return dataset?.vault_path || dataset?.gdrive_path || dataset?.local_root || "";
}

function lifecycleSelection(lifecycle = {}) {
  const proof = lifecycle.proof || {};
  return {
    execution_status: lifecycle.stage || undefined,
    progress: lifecycle.progress ?? undefined,
    run_id: proof.run_id || undefined,
    worker: proof.worker || undefined,
    worker_pool: proof.pool || undefined,
    attempt: proof.attempt ?? undefined,
    heartbeat_at: proof.heartbeat_at || undefined,
    latest_event_at: proof.latest_event_at || undefined,
    manifest_id: proof.manifest_id || undefined,
    registration_id: proof.registration_id || undefined,
    archive_verified: proof.archive_verified || undefined,
    registry_verified: proof.registry_verified || undefined,
    rows: proof.rows ?? undefined,
    fields: proof.fields ?? undefined,
    entities: proof.entities ?? undefined,
    inputs: proof.inputs?.length ? proof.inputs : undefined,
    outputs: proof.outputs?.length ? proof.outputs : undefined,
    error: lifecycle.error || undefined,
    retryable: lifecycle.retryable || undefined,
  };
}

export function buildRailContext({
  tab = "home",
  mode = "detail",
  dataset = null,
  activeObject = null,
  searchQuery = "",
  folderId = "",
  clusterContext = null,
  profileEmail = "",
} = {}) {
  let entity = null;
  let datasetId = "";
  let actions = [];
  let selected = null;

  if (activeObject?.kind === "external_candidate") {
    const row = activeObject.row || {};
    const sourceId = row.source_id || "";
    const connectorId = row.connector_id || row.desk_connector_id || "";
    const key = row.candidate_key || candidateKey(row) || activeObject.id || "";
    entity = {
      kind: "external_candidate",
      id: activeObject.id,
      title: activeObject.title,
      source_id: sourceId || undefined,
      connector_id: connectorId || undefined,
      candidate_key: key || undefined,
    };
    selected = {
      title: activeObject.title,
      source_id: sourceId || undefined,
      connector_id: connectorId || undefined,
      candidate_key: key || undefined,
      endpoint: row.endpoint || row.url || undefined,
    };
    datasetId = row.dataset_id || row.doi || "";
    actions = ["add_to_lab", "probe", "ask_about", "schedule_refresh"];
  } else if (activeObject?.kind === "discover_history") {
    const row = activeObject.row || {};
    const meta = row.meta || {};
    const status = row.status || meta.status || "";
    const sourceId = meta.source_id || row.source_id || "";
    const candidateKey = meta.candidate_key || row.candidate_key || "";
    const eventId = row.id || meta.intent_id || meta.job_id || meta.subscription_id || activeObject.id || "";
    entity = {
      kind: "discover_history",
      id: eventId,
      title: activeObject.title,
      status: status || undefined,
      event_kind: row.kind || row.action || undefined,
    };
    selected = {
      title: activeObject.title,
      status: status || undefined,
      event_kind: row.kind || row.action || undefined,
      source_id: sourceId || undefined,
      candidate_key: candidateKey || undefined,
      job_id: meta.job_id || row.job_id || undefined,
      intent_id: meta.intent_id || undefined,
      summary: meta.summary || row.summary || undefined,
    };
    actions = ["explain", "ask_about"];
    if (/pending_approval|ready_for_review|awaiting|needs_approval/i.test(String(status))) {
      actions.push("review_request");
    }
  } else if (activeObject?.kind === "resource_row") {
    const row = activeObject.row || {};
    const lifecycle = row.lifecycle || {};
    entity = {
      kind: "resource_row",
      id: activeObject.id,
      title: activeObject.title,
      status: lifecycle.stage || row.metric || undefined,
    };
    selected = {
      title: activeObject.title,
      resource_kind: row.kind || undefined,
      status: lifecycle.stage || row.metric || undefined,
      detail: row.detail || lifecycle.detail || undefined,
      ...lifecycleSelection(lifecycle),
    };
    actions = ["explain"];
    if (lifecycle.stage === "pending_approval" || row.job?.status === "pending_approval") {
      actions.push("approve_job");
    }
    if (lifecycle.retryable && /failed|blocked/.test(String(lifecycle.stage || ""))) {
      actions.push("retry_job");
    }
  } else if (activeObject?.kind === "library_folder" || activeObject?.kind === "library_intake") {
    entity = { kind: activeObject.kind, id: activeObject.id, title: activeObject.title };
    actions = ["upload", "add_url", "procure"];
  } else if (activeObject?.kind === "home_attention") {
    entity = { kind: "home_attention", id: activeObject.id, title: activeObject.title };
    actions = ["open", "ask_about"];
  } else if (activeObject?.kind === "synthesis_thread") {
    const thread = activeObject.thread || {};
    const state = thread.state || {};
    const lifecycle = normalizeSynthesisExecution(thread);
    const outputId = lifecycle.proof?.outputs?.[0] || state.execution?.output_dataset_id || state.execution_spec?.output_dataset_id;
    entity = {
      kind: "synthesis_thread",
      id: activeObject.id,
      title: activeObject.title,
      status: lifecycle.stage !== "unknown" ? lifecycle.stage : state.maturity || undefined,
    };
    selected = {
      thread_id: activeObject.id,
      title: activeObject.title,
      objective: thread.objective || state.objective || undefined,
      required_grain: state.required_grain || state.spec?.grain || undefined,
      maturity: state.maturity || state.maturityLabel || undefined,
      proposal_id: state.proposal?.id || undefined,
      proposal_hash: state.proposal?.proposal_hash || undefined,
      output_dataset_id: outputId || undefined,
      ...lifecycleSelection(lifecycle),
    };
    actions = ["ask_about", "challenge_method", "review_proposal"];
    if (lifecycle.stage === "pending_approval") actions.push("review_execution");
    if (lifecycle.retryable && /failed|blocked/.test(lifecycle.stage)) actions.push("retry_execution");
    if (lifecycle.stage === "registered") actions.push("open_output", "refresh_output");
  } else if (dataset?.dataset_id) {
    const authority = assetAuthorityContext(dataset);
    entity = {
      kind: "dataset",
      id: dataset.dataset_id,
      title: displayName(dataset),
      status: authority.readiness || undefined,
    };
    selected = {
      title: displayName(dataset),
      ...authority,
    };
    datasetId = dataset.dataset_id;
    actions = ["ask_about", "inspect_lineage"];
    if (authority.readiness === "query_ready") actions.unshift("preview_rows");
    if (authority.refresh_policy) actions.push("refresh_asset");
  }

  const compare =
    clusterContext?.a?.dataset_id && clusterContext?.b?.dataset_id
      ? {
          left: clusterContext.a.dataset_id,
          right: clusterContext.b.dataset_id,
          shared_keys: clusterContext.shared || [],
        }
      : null;

  if (compare) {
    actions = ["ask_about_overlap", "preview_rows"];
  }

  return {
    tab,
    mode,
    entity,
    selected: selected || undefined,
    dataset_id: datasetId || undefined,
    folder_id: folderId || undefined,
    search_query: searchQuery?.trim() || undefined,
    profile_email: profileEmail || undefined,
    readiness: dataset ? readinessLabel(dataset) : undefined,
    vault_path: dataset ? vaultPath(dataset) : undefined,
    compare: compare || undefined,
    actions: actions.length ? actions : undefined,
  };
}
