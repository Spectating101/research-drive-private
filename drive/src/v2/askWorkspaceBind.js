/** Bind Ask to the open desk surface so Discover/Library/Synthesis do not share a detached thread. */

export function workspaceAskBindKey(railContext, dataset) {
  const rail = railContext && typeof railContext === "object" ? railContext : {};
  const workspace = rail.workspace && typeof rail.workspace === "object" ? rail.workspace : {};
  const surface = String(workspace.surface || rail.surface || "").toLowerCase();
  if (surface === "discover" || surface === "browse") {
    const query = String(workspace.query || rail.search_query || "").trim().toLowerCase();
    const focus = String(workspace.focus_source_id || workspace.focus_candidate_key || "").trim();
    return `discover:${query}|${focus}`;
  }
  if (surface === "library") {
    const id = String(
      workspace.dataset_id || rail.dataset_id || dataset?.dataset_id || workspace.folder_id || rail.folder_id || "",
    ).trim();
    return `library:${id}`;
  }
  if (surface === "synthesis") {
    const id = String(
      workspace.thread_id || rail.thread_id || dataset?.thread_id || dataset?.id || "",
    ).trim();
    return `synthesis:${id}`;
  }
  return `desk:${surface || "home"}`;
}
