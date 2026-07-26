/**
 * Profile / Home search recommendations → Discover Explore handoff.
 * Pure contract so regression tests can pin URL + query state without React.
 */

export function discoverSearchHandoff(query) {
  const q = String(query || "").trim();
  if (!q) return null;
  return {
    tab: "browse",
    q,
    discoverSearchQuery: q,
  };
}
