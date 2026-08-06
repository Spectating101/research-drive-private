import { displayName, isQueryReadyReadiness } from "./datasetMeta.js";
import { candidateKey } from "./candidateKey.js";
import { assetAuthorityContext } from "./assetAuthority.js";
import { connectorContext } from "./connectorContract.js";
import { normalizeSynthesisExecution } from "./executionLifecycle.js";

function readinessLabel(dataset) {
  const raw = String(dataset?.analysis_readiness || "").trim();
  if (!raw) return "";
  // Exact tokens only — `/ready|query/` falsely labels not_ready / metadata_search.
  if (isQueryReadyReadiness(raw)) return "Query-ready";
  return raw.replace(/_/g, " ");
}

function vaultPath(dataset) {
  return dataset?.vault_path || dataset?.gdrive_path || dataset?.local_root || "";
}

function lifecycleSelection(lifecycle = {}) {
  const proof = lifecycle.proof || {};
  const routing = lifecycle.routing || {};
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
    routing_status: routing.status || undefined,
    required_capabilities: routing.required?.length ? routing.required : undefined,
    missing_capabilities: routing.missing?.length ? routing.missing : undefined,
    eligible_workers: routing.eligible_workers?.length ? routing.eligible_workers : undefined,
  };
}

function surfaceLabel(tab) {
  const t = String(tab || "").toLowerCase();
  if (t === "browse") return "discover";
  if (t === "library") return "library";
  if (t === "synthesis") return "synthesis";
  if (t === "home") return "home";
  if (t === "resources") return "resources";
  return t || "desk";
}

function buildWorkspace({
  tab,
  searchQuery,
  discoverMode,
  discoverSummary,
  folderId,
  entity,
  selected,
  dataset,
}) {
  const surface = surfaceLabel(tab);
  const query = String(searchQuery || discoverSummary?.query || "").trim();
  const workspace = {
    surface,
    label:
      surface === "discover"
        ? "Discover"
        : surface === "library"
          ? "Library"
          : surface === "synthesis"
            ? "Synthesis"
            : surface === "home"
              ? "Home"
              : surface,
  };
  if (query) workspace.query = query.slice(0, 240);
  if (surface === "discover") {
    if (discoverMode) workspace.mode = String(discoverMode);
    if (discoverSummary && typeof discoverSummary === "object") {
      workspace.held_count = Number(discoverSummary.held || 0);
      workspace.route_offerings = Number(discoverSummary.offerings || 0);
      workspace.web_context = Number(discoverSummary.webContext || 0);
      if (discoverSummary.engine) workspace.engine = String(discoverSummary.engine);
      if (discoverSummary.next_action) workspace.next_action = String(discoverSummary.next_action);
      if (discoverSummary.summary) workspace.summary = String(discoverSummary.summary).slice(0, 320);
      if (Array.isArray(discoverSummary.held_titles) && discoverSummary.held_titles.length) {
        workspace.held = discoverSummary.held_titles.slice(0, 5);
      }
      if (Array.isArray(discoverSummary.route_titles) && discoverSummary.route_titles.length) {
        workspace.routes = discoverSummary.route_titles.slice(0, 5);
      }
    }
  }
  if (surface === "library") {
    if (folderId) workspace.folder_id = String(folderId);
    if (dataset?.dataset_id) {
      workspace.dataset_id = dataset.dataset_id;
      workspace.dataset_title = displayName(dataset);
    }
  }
  if (surface === "synthesis" && selected) {
    if (selected.thread_id) workspace.thread_id = selected.thread_id;
    if (selected.objective) workspace.objective = String(selected.objective).slice(0, 320);
    if (selected.maturity) workspace.maturity = selected.maturity;
    if (selected.proposal_id) workspace.proposal_id = selected.proposal_id;
    if (selected.proposal && typeof selected.proposal === "object") {
      workspace.proposal = {
        id: selected.proposal.id,
        title: selected.proposal.title,
        summary: selected.proposal.summary,
        proposal_hash: selected.proposal.proposal_hash || selected.proposal.hash,
      };
    }
    if (selected.has_method) workspace.has_method = true;
    if (selected.can_request_execution) workspace.can_request_execution = true;
    if (selected.method_not_executable) workspace.method_not_executable = true;
    if (selected.has_execution_spec) workspace.has_execution_spec = true;
    if (selected.output_ready) workspace.output_ready = true;
    if (selected.query_ready) workspace.query_ready = true;
    if (selected.output_dataset_id) workspace.output_dataset_id = selected.output_dataset_id;
    if (Array.isArray(selected.mapped_evidence) && selected.mapped_evidence.length) {
      workspace.mapped_evidence = selected.mapped_evidence.slice(0, 8);
    }
  }
  if (entity?.kind) {
    workspace.focus_kind = entity.kind;
    workspace.focus_title = entity.title || entity.id || undefined;
  }
  if (selected?.source_id) workspace.focus_source_id = selected.source_id;
  if (selected?.candidate_key) workspace.focus_candidate_key = selected.candidate_key;
  return workspace;
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
  discoverMode = "",
  discoverSummary = null,
} = {}) {
  let entity = null;
  let datasetId = "";
  let actions = [];
  let selected = null;

  if (activeObject?.kind === "external_candidate") {
    const row = activeObject.row || {};
    const contract = connectorContext(row);
    const key = row.candidate_key || candidateKey(row) || activeObject.id || "";
    entity = {
      kind: "external_candidate",
      id: activeObject.id,
      title: activeObject.title,
      source_id: contract.source_id,
      connector_id: contract.connector_id,
      candidate_key: key || undefined,
      status: contract.access_state || undefined,
    };
    selected = {
      title: activeObject.title,
      candidate_key: key || undefined,
      ...contract,
    };
    datasetId = row.dataset_id || row.doi || "";
    actions = ["ask_about"];
    if (contract.supported) actions.push("probe");
    if (contract.access_state === "available") actions.unshift("add_to_lab");
    if (contract.refresh_policy) actions.push("schedule_refresh");
    if (contract.credential_required) actions.push("configure_access");
    if (contract.access_state === "rate_limited" && contract.retryable) actions.push("retry_later");
    if (!contract.supported) actions.push("find_alternative_source");
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
    const sourceContract = row.kind === "source" ? connectorContext(row) : null;
    entity = {
      kind: "resource_row",
      id: activeObject.id,
      title: activeObject.title,
      status: lifecycle.stage || sourceContract?.access_state || row.metric || undefined,
    };
    selected = {
      title: activeObject.title,
      resource_kind: row.kind || undefined,
      status: lifecycle.stage || sourceContract?.access_state || row.metric || undefined,
      detail: row.detail || lifecycle.detail || undefined,
      ...(sourceContract || {}),
      ...lifecycleSelection(lifecycle),
    };
    actions = ["explain"];
    if (lifecycle.stage === "pending_approval" || row.job?.status === "pending_approval") {
      actions.push("approve_job");
    }
    if (lifecycle.retryable && /failed|blocked/.test(String(lifecycle.stage || ""))) {
      actions.push("retry_job");
    }
    if (sourceContract?.credential_required) actions.push("configure_access");
    if (sourceContract?.probe_required) actions.push("probe");
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
    const proposal =
      state.proposal && typeof state.proposal === "object" ? state.proposal : null;
    entity = {
      kind: "synthesis_thread",
      id: activeObject.id,
      title: activeObject.title,
      status: lifecycle.stage !== "unknown" ? lifecycle.stage : state.maturity || undefined,
    };
    const executionSpec =
      state.execution_spec && typeof state.execution_spec === "object" ? state.execution_spec : null;
    const hasMetrics =
      Array.isArray(executionSpec?.metrics) && executionSpec.metrics.length > 0;
    const hasRowTransforms =
      Boolean(executionSpec?.row_output) &&
      Array.isArray(executionSpec?.transforms) &&
      executionSpec.transforms.length > 0;
    const hasBoundedExecutionSpec = Boolean(
      executionSpec &&
        String(executionSpec.input_dataset_id || "").trim() &&
        String(executionSpec.output_dataset_id || "").trim() &&
        (hasMetrics || hasRowTransforms),
    );
    const hasMethod = Boolean(
      state.spec ||
        executionSpec ||
        hasBoundedExecutionSpec ||
        (Array.isArray(state.nodes) && state.nodes.length) ||
        (Array.isArray(state.activity) &&
          state.activity.some((row) => /accepted proposal/i.test(String(row?.message || "")))),
    );
    const outputReady =
      lifecycle.stage === "registered" ||
      lifecycle.stage === "query_ready" ||
      Boolean(lifecycle.proof?.registry_verified);
    const queryReady =
      lifecycle.stage === "query_ready" || Boolean(lifecycle.proof?.query_ready);
    // Spec alone is not enough once the durable output already exists.
    const canRequestExecution = Boolean(!proposal && hasBoundedExecutionSpec && !outputReady);
    const mappedEvidence = (
      Array.isArray(state.nodes)
        ? state.nodes
            .filter((node) => node && typeof node === "object" && String(node.dataset_id || "").trim())
            .map((node) => ({
              dataset_id: String(node.dataset_id).trim(),
              title: String(node.label || node.title || node.dataset_id).trim(),
              grain: String(node.grain || "").trim() || undefined,
              coverage: String(node.coverage || "").trim() || undefined,
              role: String(node.role || "").trim() || undefined,
              status: String(node.status || "").trim() || undefined,
            }))
        : []
    ).slice(0, 8);
    selected = {
      thread_id: activeObject.id,
      title: activeObject.title,
      objective: thread.objective || state.objective || undefined,
      required_grain: state.required_grain || state.spec?.grain || undefined,
      maturity: state.maturity || state.maturityLabel || undefined,
      proposal_id: proposal?.id || undefined,
      proposal_hash: proposal?.proposal_hash || undefined,
      proposal: proposal || undefined,
      has_method: hasMethod || undefined,
      // Only offer Request execution when the registry executor can actually run it
      // and the thread has not already produced a registered / query-ready output.
      can_request_execution: canRequestExecution || undefined,
      method_not_executable: (!proposal && hasMethod && !hasBoundedExecutionSpec && !outputReady) || undefined,
      has_execution_spec: hasBoundedExecutionSpec || undefined,
      output_ready: outputReady || undefined,
      query_ready: queryReady || undefined,
      mapped_evidence: mappedEvidence.length ? mappedEvidence : undefined,
      output_dataset_id: outputId || undefined,
      ...lifecycleSelection(lifecycle),
    };
    actions = ["ask_about", "challenge_method", "review_proposal"];
    if (proposal) actions.unshift("review_proposal");
    if (canRequestExecution) actions.push("request_execution");
    if (!proposal && hasMethod && !hasBoundedExecutionSpec && !outputReady) {
      actions.push("refine_execution_spec");
    }
    if (lifecycle.stage === "pending_approval") actions.push("review_execution");
    if (lifecycle.retryable && /failed|blocked/.test(lifecycle.stage)) actions.push("retry_execution");
    if (outputReady) actions.push("open_output", "refresh_output");
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

  const workspace = buildWorkspace({
    tab,
    searchQuery,
    discoverMode,
    discoverSummary,
    folderId,
    entity,
    selected,
    dataset,
  });

  return {
    tab,
    mode,
    surface: workspace.surface,
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
    thread_id: selected?.thread_id || undefined,
    workspace,
  };
}
