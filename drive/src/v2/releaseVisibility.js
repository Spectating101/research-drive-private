/**
 * Public Discover/Library release boundary (Terra donor: ba1f4c9).
 *
 * Showcase default: Synthesis stays visible for the demo.
 * Flip SYNTHESIS_NAV_DEFERRED to true after the showcase to hide public nav/deep links
 * while keeping Synthesis pages/APIs/tests in-tree.
 */
export const SYNTHESIS_NAV_DEFERRED = false;

/** Where public `tab=synthesis` deep links land while Synthesis is deferred. */
export const SYNTHESIS_RELEASE_REDIRECT_TAB = "library";

export function normalizeReleaseTab(tab) {
  if (SYNTHESIS_NAV_DEFERRED && tab === "synthesis") {
    return SYNTHESIS_RELEASE_REDIRECT_TAB;
  }
  return tab;
}
