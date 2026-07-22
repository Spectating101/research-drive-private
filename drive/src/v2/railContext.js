import { displayName } from "@/v2/datasetMeta";

function readinessLabel(dataset) {
  const raw = String(dataset?.analysis_readiness || "").trim();
  if (!raw) return "";
  if (/instant|ready|query/i.test(raw)) return "Query-ready";
  return raw.replace(/_/g, " ");
}

function vaultPath(dataset) {
  return dataset?.vault_path || dataset?.gdrive_path || dataset?.local_root || "";
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

  if (activeObject?.kind === "external_candidate") {
    entity = {
      kind: "external_candidate",
      id: activeObject.id,
      title: activeObject.title,
    };
    datasetId = activeObject.row?.dataset_id || activeObject.row?.doi || "";
    actions = ["add_to_lab", "probe", "ask_about"];
  } else if (activeObject?.kind === "resource_row") {
    entity = { kind: "resource_row", id: activeObject.id, title: activeObject.title };
    actions = ["explain", "approve_job"];
  } else if (activeObject?.kind === "history_event") {
    entity = { kind: "history_event", id: activeObject.id, title: activeObject.title };
    datasetId = activeObject.event?.meta?.dataset_id || "";
    actions = ["open_outcome", "repeat_search", "ask_about"];
  } else if (activeObject?.kind === "library_folder" || activeObject?.kind === "library_intake") {
    entity = { kind: activeObject.kind, id: activeObject.id, title: activeObject.title };
    actions = ["upload", "add_url", "procure"];
  } else if (activeObject?.kind === "home_attention") {
    entity = { kind: "home_attention", id: activeObject.id, title: activeObject.title };
    actions = ["open", "ask_about"];
  } else if (activeObject?.kind === "synthesis_thread") {
    const thread = activeObject.thread || {};
    const state = thread.state || {};
    entity = {
      kind: "synthesis_thread",
      id: activeObject.id,
      title: activeObject.title,
      status:
        activeObject.status ||
        state.maturityLabel ||
        state.execution?.status ||
        state.maturity ||
        undefined,
      selected_node: activeObject.selectedNode || state.selectedStep || undefined,
      draft: Boolean(activeObject.draft || thread.localDraft) || undefined,
      proposal: state.proposal || undefined,
    };
    actions = ["ask_about", "propose_state"];
  } else if (dataset?.dataset_id) {
    entity = {
      kind: "dataset",
      id: dataset.dataset_id,
      title: displayName(dataset),
    };
    datasetId = dataset.dataset_id;
    actions = ["preview_rows", "ask_about"];
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

  const synthesisThreadId =
    activeObject?.kind === "synthesis_thread" && !activeObject.draft && !activeObject.thread?.localDraft
      ? activeObject.id
      : undefined;
  const synthesisSessionId =
    activeObject?.kind === "synthesis_thread"
      ? activeObject.thread?.session_id || undefined
      : undefined;

  return {
    tab,
    mode,
    entity,
    dataset_id: datasetId || undefined,
    folder_id: folderId || undefined,
    search_query: searchQuery?.trim() || undefined,
    profile_email: profileEmail || undefined,
    readiness: dataset ? readinessLabel(dataset) : undefined,
    vault_path: dataset ? vaultPath(dataset) : undefined,
    compare: compare || undefined,
    actions: actions.length ? actions : undefined,
    thread_id: synthesisThreadId || undefined,
    session_id: synthesisSessionId || undefined,
    conversation_id:
      (activeObject?.kind === "synthesis_thread" && activeObject.thread?.conversation_id) || undefined,
  };
}
