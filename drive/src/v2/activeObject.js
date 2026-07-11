import { displayName } from "@/v2/datasetMeta";
import { candidateKey } from "@/v2/candidateKey";

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
  const id = candidateKey(row) || row.dataset_id || row.doi || row.url || row.title || "external";
  return {
    kind: "external_candidate",
    id,
    title: compactText(row.title || row.name || row.dataset_id, "External dataset"),
    row,
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
  connectedCount = 0,
  metadataOnlyCount = 0,
  unknownCount = 0,
  itemCount = 0,
} = {}) {
  const root = !folderId;
  const title = root ? "Lab" : compactText(trail[trail.length - 1]?.name, "Library collection");
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
      connected: connectedCount,
      metadataOnly: metadataOnlyCount,
      unknown: unknownCount,
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
    destination: base.destination || base.title || "Lab",
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
  return object.title || object.id || "";
}
