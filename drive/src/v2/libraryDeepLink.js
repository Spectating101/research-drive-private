/**
 * Library deep-link reconciliation — folder centre and selected asset must agree.
 * Never render an empty folder alongside a selected asset that is not in that folder.
 */

import { collectDatasetDescendants } from "../driveTree.js";

/** Folder id that directly contains the dataset leaf, or null if unknown. */
export function findDatasetFolderId(tree, datasetId) {
  const id = String(datasetId || "").trim();
  if (!id) return null;
  const hit = collectDatasetDescendants(tree, "").find((item) => item?.id === id);
  if (!hit) return null;
  const path = Array.isArray(hit.path) ? hit.path.filter(Boolean) : [];
  if (path.length >= 2) return path.slice(0, -1).join("/");
  return "";
}

export function selectionBelongsToFolder(tree, folderId, selectedId) {
  const id = String(selectedId || "").trim();
  if (!id) return false;
  return collectDatasetDescendants(tree, folderId || "").some((item) => item?.id === id);
}

/**
 * @returns {{ folderId: string, selectedId: string }}
 */
export function reconcileLibraryDeepLink({ folderId = "", selectedId = "", tree } = {}) {
  const folder = String(folderId || "");
  const selected = String(selectedId || "").trim();
  if (!selected) return { folderId: folder, selectedId: "" };
  if (!tree) return { folderId: folder, selectedId: selected };
  if (selectionBelongsToFolder(tree, folder, selected)) {
    return { folderId: folder, selectedId: selected };
  }
  const home = findDatasetFolderId(tree, selected);
  if (home != null) {
    return { folderId: home, selectedId: selected };
  }
  return { folderId: folder, selectedId: "" };
}
