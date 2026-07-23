/**
 * Settings centre + Detail rail presentation helpers.
 * Centre model: Research context → Workspace → Advanced (collapsed).
 * Only durable browser-local controls — no operational health as configuration.
 */

export const SETTINGS_SECTION_ORDER = Object.freeze([
  "context",
  "workspace",
  "advanced",
]);

export const SETTINGS_GROUP_LABELS = Object.freeze({
  context: "Research context",
  workspace: "Workspace",
  advanced: "Advanced",
});

/** Advanced stays collapsed on the normal path. */
export function settingsAdvancedDefaultOpen() {
  return false;
}

/**
 * Quiet Detail facts for a settings group — 2–4 local values only.
 * No Judgement paragraph. Primary action only when Clear context is available.
 */
export function buildSettingsRailState({
  group = "context",
  settings = {},
  profile = null,
  tokenPresent = false,
} = {}) {
  const g = SETTINGS_SECTION_ORDER.includes(group) ? group : "context";
  const email = settings.email || "";
  const boundName =
    profile && !profile.unknown
      ? profile.name_en || profile.name || ""
      : "";

  if (g === "context") {
    return {
      group: g,
      identity: [SETTINGS_GROUP_LABELS.context],
      judgement: null,
      facts: [
        ["Bound as", boundName || (email ? "Unresolved on this browser" : "None")],
        ["Email", email || "Not set"],
        ["Scope", "Browser preference — not authentication"],
      ].slice(0, 4),
      unknowns: [],
      primaryAction: email
        ? { id: "clear-context", label: "Clear context" }
        : null,
      secondaryActions: [],
      disclosure: null,
    };
  }

  if (g === "workspace") {
    return {
      group: g,
      identity: [SETTINGS_GROUP_LABELS.workspace],
      judgement: null,
      facts: [
        ["Default tab", settings.defaultTab || "home"],
        ["On select", settings.onSelect === "ask" ? "Open Ask" : "Show Detail"],
        ["Scope", "This browser only"],
      ].slice(0, 4),
      unknowns: [],
      primaryAction: null,
      secondaryActions: [],
      disclosure: null,
    };
  }

  return {
    group: g,
    identity: [SETTINGS_GROUP_LABELS.advanced],
    judgement: null,
    facts: [
      ["Fallback token", tokenPresent ? "Present" : "Absent"],
      ["Research email", email || "Not set"],
      ["Default tab", settings.defaultTab || "home"],
    ].slice(0, 4),
    unknowns: [],
    primaryAction: null,
    secondaryActions: [],
    disclosure: null,
  };
}
