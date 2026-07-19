/** Canonical Discover URL state. Discover has only Explore and History modes. */
export function discoverModeFromLegacy(raw = "") {
  const mode = String(raw || "").trim().toLowerCase();
  if (mode === "history") return { mode: "history", focusAwaiting: false };
  if (mode === "approvals" || mode === "awaiting") return { mode: "explore", focusAwaiting: true };
  if (mode === "explore" || mode === "search" || mode === "activity" || !mode) {
    return { mode: "explore", focusAwaiting: false };
  }
  return { mode: "explore", focusAwaiting: false };
}

export function discoverModeToUrlState(mode = "explore") {
  return mode === "history" ? "history" : "";
}
