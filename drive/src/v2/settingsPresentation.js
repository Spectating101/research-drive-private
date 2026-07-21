/**
 * Settings centre + Detail rail presentation helpers.
 * Centre model is exactly Identity → Access → Defaults → Advanced recovery.
 */

export const SETTINGS_SECTION_ORDER = Object.freeze([
  "identity",
  "access",
  "defaults",
  "advanced",
]);

export const SETTINGS_GROUP_LABELS = Object.freeze({
  identity: "Identity",
  access: "Access",
  defaults: "Defaults",
  advanced: "Advanced recovery",
});

/** Advanced recovery stays collapsed on the normal path. */
export function settingsAdvancedDefaultOpen() {
  return false;
}

export function assistantStatusFromHealth(health) {
  const desk = health?.desk || {};
  const explicit = desk.composer_configured;
  const legacy = desk.legacy_llm_configured;
  const model = String(desk.composer_model || desk.brain || "").trim();

  if (explicit === true || legacy === true) {
    return {
      ready: true,
      known: true,
      label: "Ready",
      detail: model ? `${model} runtime` : "Ask and acquisition planning",
    };
  }
  if (explicit === false && legacy !== true) {
    return { ready: false, known: true, label: "Needs setup", detail: "Assistant health reports offline" };
  }
  // Never invent Ready from a bare model string alone when flags are absent
  if (model && (explicit === true || legacy === true)) {
    return { ready: true, known: true, label: "Ready", detail: `${model} runtime` };
  }
  return { ready: false, known: false, label: "Not reported", detail: "No assistant signal on /health" };
}

export function deskAccessStatusFromHealth(health, { hasToken = false, sessionBootstrapped = false } = {}) {
  const desk = health?.desk || {};
  if (hasToken) return { ok: true, label: "Connected", detail: "Session fallback" };
  if (sessionBootstrapped || desk.desk_session_cookie) {
    return { ok: true, label: "Connected", detail: "Browser session" };
  }
  if (desk.desk_token_required) {
    return { ok: false, label: "Needs connection", detail: "Authorization required" };
  }
  if (health?.status === "ok") {
    return { ok: true, label: "Open", detail: "Desk reachable" };
  }
  if (!health) {
    return { ok: null, label: "Not reported", detail: "No /health payload yet" };
  }
  return { ok: false, label: "Check desk", detail: health.status || "Health degraded" };
}

export function archiveStatusFromHealth(health) {
  const gdrive = health?.desk?.gdrive;
  if (!gdrive) return { ok: null, label: "Not reported", detail: "No archive health on /health" };
  if (gdrive.ok === false || gdrive.ready === false) {
    return { ok: false, label: "Needs review", detail: "Archive connection" };
  }
  if (gdrive.ok === true || gdrive.ready === true || gdrive.drive_list_ok === true) {
    return { ok: true, label: "Connected", detail: "Research archive" };
  }
  return { ok: null, label: "Not reported", detail: "Archive signal incomplete" };
}

/**
 * Concise Detail facts for a settings group — max 5, truth-backed only.
 */
export function buildSettingsRailState({
  group = "identity",
  settings = {},
  health = null,
  access = null,
  assistant = null,
  archive = null,
} = {}) {
  const g = SETTINGS_SECTION_ORDER.includes(group) ? group : "identity";
  const accessState = access || deskAccessStatusFromHealth(health);
  const assistantState = assistant || assistantStatusFromHealth(health);
  const archiveState = archive || archiveStatusFromHealth(health);
  const email = settings.email || "";

  if (g === "identity") {
    return {
      group: g,
      identity: ["Faculty email preference", email || "Not set"],
      judgement: email
        ? "Profile routing uses this faculty email preference for this browser."
        : "Desk is unbound until a faculty email preference is saved.",
      facts: [
        email ? `Email · ${email}` : "Email · not set",
        "Scope · this browser only (not authentication)",
        `Default tab · ${settings.defaultTab || "home"}`,
      ].slice(0, 5),
      unknowns: email ? [] : ["Faculty email preference"],
      primaryAction: { id: "focus-email", label: email ? "Update email" : "Save faculty email" },
      secondaryActions: [],
      disclosure: null,
    };
  }

  if (g === "access") {
    return {
      group: g,
      identity: ["Desk access", accessState.label],
      judgement: accessState.ok
        ? "This browser can reach the research desk."
        : "Connect this browser before write actions.",
      facts: [
        `Status · ${accessState.label}`,
        `Detail · ${accessState.detail}`,
        assistantState.known ? `Assistant · ${assistantState.label}` : "Assistant · Not reported",
        archiveState.ok != null ? `Archive · ${archiveState.label}` : "Archive · Not reported",
      ].slice(0, 5),
      unknowns: [
        !assistantState.known ? "Assistant health" : null,
        archiveState.ok == null ? "Archive health" : null,
      ].filter(Boolean).slice(0, 3),
      primaryAction: accessState.ok
        ? { id: "review-advanced", label: "Advanced recovery" }
        : { id: "connect-browser", label: "Connect browser" },
      secondaryActions: [],
      disclosure: "Session bootstrap and fallback tokens live under Advanced recovery.",
    };
  }

  if (g === "defaults") {
    return {
      group: g,
      identity: ["Workspace defaults", "Display preferences"],
      judgement: "Defaults affect first landing and selection behaviour only.",
      facts: [
        `Open on · ${settings.defaultTab || "home"}`,
        `On select · ${settings.onSelect === "ask" ? "Ask" : "Detail"}`,
      ],
      unknowns: [],
      primaryAction: { id: "focus-defaults", label: "Edit defaults" },
      secondaryActions: [],
      disclosure: null,
    };
  }

  // advanced
  const jobs = health?.desk?.jobs;
  const facts = [
    health?.status ? `API · ${health.status}` : "API · Not reported",
    assistantState.known ? `Assistant · ${assistantState.label}` : "Assistant · Not reported",
    jobs
      ? `Jobs · ${jobs.pending_approval ?? 0} pending · ${jobs.failed_recent ?? jobs.failed ?? 0} failed`
      : "Jobs · Not reported",
    accessState.detail ? `Access · ${accessState.detail}` : null,
  ].filter(Boolean).slice(0, 5);

  return {
    group: g,
    identity: ["Advanced recovery", "Diagnostics and session repair"],
    judgement: "Use only when the normal identity/access path needs recovery.",
    facts,
    unknowns: jobs ? [] : ["Job counters"],
    primaryAction: { id: "connect-browser", label: "Reconnect browser" },
    secondaryActions: [{ id: "save-fallback", label: "Save fallback token" }],
    disclosure: "Fallback tokens and raw health links are recovery tools, not daily controls.",
  };
}
