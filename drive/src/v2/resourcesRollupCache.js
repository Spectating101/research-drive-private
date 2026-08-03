/** Last-known Resources rollup for cache-first Sources rendering. */

export const RESOURCES_ROLLUP_CACHE_KEY = "rd.v2.resources.rollup.v1";

export function readResourcesRollupCache() {
  try {
    const raw = sessionStorage.getItem(RESOURCES_ROLLUP_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function writeResourcesRollupCache(rollup) {
  try {
    if (!rollup || typeof rollup !== "object") {
      sessionStorage.removeItem(RESOURCES_ROLLUP_CACHE_KEY);
      return;
    }
    sessionStorage.setItem(RESOURCES_ROLLUP_CACHE_KEY, JSON.stringify(rollup));
  } catch {
    // Storage can be unavailable or full; the Sources manifest still renders.
  }
}
