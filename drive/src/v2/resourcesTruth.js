/** Fail-closed Resources helpers — never invent a healthy desk from missing rollup. */

export function measuredComposerLabel(model) {
  const text = String(model || "").trim();
  return text || "Not reported";
}

export function rollupIsMeasured(rollup) {
  return Boolean(rollup) && rollup._placeholder !== true;
}

export function unmeasuredResourcesPanels() {
  return {
    hero: null,
    ai: [],
    metered: [],
    usage: [],
    motion: [],
    compute: [],
    providers: [],
    layers: [],
    connect: { source_count: 0, layer_count: 0 },
    issuesCount: 0,
    issuesFromRollup: [],
    offline: true,
    unmeasured: true,
  };
}
