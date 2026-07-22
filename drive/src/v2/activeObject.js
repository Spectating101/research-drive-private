import { displayName } from "@/v2/datasetMeta";

function compactText(value, fallback = "") {
  return String(value || fallback).trim();
}

function folderPath(trail = []) {
  return trail.map((crumb) => crumb.name).filter(Boolean).join(" / ") || "Lab";
}

export function datasetObject(row) {
  if (!row) return null;
  const id = row.dataset_id || row.id || row.title || row.name || "dataset";
  return {
    kind: "dataset",
    id,
    title: displayName(row),
    row,
  };
}

export function externalCandidateObject(row) {
  if (!row) return null;
  const id =
    row.candidate_key || row.source_id || row.dataset_id || row.doi || row.url || row.title || "external";
  return {
    kind: "external_candidate",
    id,
    title: compactText(row.title || row.name || row.label || row.dataset_id || row.source_id, "External source"),
    row,
  };
}

export function historyEventObject(event) {
  if (!event) return null;
  const id = event.id || event.ts || event.target || "history-event";
  return {
    kind: "history_event",
    id,
    title: compactText(
      event.target,
      String(event.action || event.kind || "Research history").replace(/_/g, " "),
    ),
    event,
  };
}

export function resourceObject(row) {
  if (!row) return null;
  return {
    kind: "resource_row",
    id: row.key || row.id || row.label || "resource",
    title: compactText(row.label?.split("·")[0], row.label || "Resources row"),
    row,
  };
}

export function libraryFolderObject({
  folderId = "",
  trail = [],
  destination,
  note,
  folderCount = 0,
  datasetCount = 0,
  readyCount = 0,
  itemCount = 0,
} = {}) {
  const root = !folderId;
  const title = root ? "Lab root" : compactText(trail[trail.length - 1]?.name, "Library folder");
  return {
    kind: "library_folder",
    id: folderId || "lab-root",
    folderId,
    title,
    path: folderPath(trail),
    destination: compactText(destination, title),
    note,
    counts: {
      folders: folderCount,
      datasets: datasetCount,
      queryReady: readyCount,
      items: itemCount,
    },
  };
}

export function libraryIntakeObject(mode, folder) {
  const base = folder?.kind === "library_folder" ? folder : libraryFolderObject();
  const title =
    mode === "upload"
      ? "Upload files"
      : mode === "url"
        ? "Add URL / DOI"
        : "Procure branch";
  return {
    kind: "library_intake",
    mode,
    id: `${mode}:${base.id}`,
    title,
    folderId: base.folderId || "",
    path: base.path || "Lab",
    destination: base.destination || base.title || "Lab root",
    counts: base.counts || {},
  };
}

export function homeAttentionObject(item) {
  if (!item) return null;
  return {
    kind: "home_attention",
    id: item.id || item.kind || "home-attention",
    title: compactText(item.title, "Home attention"),
    row: item,
  };
}

export function synthesisThreadObject(thread) {
  if (!thread) return null;
  const draft = Boolean(thread.localDraft);
  const evidence = compactText(thread.state?.selectedEvidence);
  const step = evidence
    ? `Evidence · ${evidence}`
    : compactText(thread.state?.selectedStepLabel || thread.state?.selectedStep);
  const title = draft
    ? "Local current-session draft"
    : compactText(thread.title || thread.state?.title, "Synthesis profile");
  return {
    kind: "synthesis_thread",
    id: thread.id || (draft ? "local-draft" : "synthesis-profile"),
    title,
    status: draft
      ? "Local current-session draft · local only"
      : compactText(thread.state?.maturityLabel || thread.materialisation, "Proposal-ready"),
    selectedNode: compactText(thread.state?.selectedStep),
    nodeLabel: step,
    draft,
    thread,
  };
}

export function pageObject(page) {
  return {
    kind: "page",
    id: page,
    title: page,
  };
}

export function activeObjectSelectionHint(object) {
  if (!object) return "";
  if (object.kind === "library_intake") return `${object.title} · ${object.destination}`;
  if (object.kind === "library_folder") return object.title || object.path || "Library folder";
  if (object.kind === "synthesis_thread") {
    const step = object.nodeLabel || object.thread?.state?.selectedStepLabel;
    if (object.draft || object.thread?.localDraft) {
      return step ? `Local current-session draft · ${step}` : "Local current-session draft · local only";
    }
    return step ? `${object.title} · ${step}` : object.title || object.id || "";
  }
  return object.title || object.id || "";
}
