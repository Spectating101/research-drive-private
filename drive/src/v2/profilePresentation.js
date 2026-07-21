/**
 * Profile centre + Detail rail presentation helpers.
 * Centre model is exactly Memory → Works → Lab.
 */

export const PROFILE_SECTION_ORDER = Object.freeze(["memory", "works", "lab"]);

export function isProfileBound(profile) {
  return Boolean(profile && !profile.unknown);
}

/** Unbound desks stay quiet — never auto-promote EXAMPLE as the primary centre. */
export function profileCentreMode(profile) {
  return isProfileBound(profile) ? "bound" : "unbound";
}

export function profilePrimaryCommand(mode) {
  if (mode === "unbound") {
    return { id: "connect-email", label: "Connect faculty email", tab: "settings" };
  }
  return null;
}

/**
 * Detail rail state. Never returns generic "Loading" once the page has a profile
 * payload (bound, unknown, or explicitly unbound/null-resolved).
 */
export function buildProfileRailState({
  profile = null,
  selectedWork = null,
  profileResolved = false,
} = {}) {
  const bound = isProfileBound(profile);

  if (!profileResolved && profile == null) {
    // Centre already paints unbound; Detail stays truthful, never Loading.
    return {
      status: "unbound",
      identity: ["Desk unbound", "Faculty identity pending"],
      judgement: "Connect a faculty email to load Memory, Works, and Lab.",
      facts: ["Profile ranking uses generic desk defaults until bound."],
      unknowns: ["Faculty identity", "Research memory", "Lab links"],
      primaryAction: { id: "connect-email", label: "Connect faculty email", tab: "settings" },
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  if (selectedWork?.title) {
    return {
      status: "work",
      identity: [
        selectedWork.title,
        selectedWork.type || "Publication",
        selectedWork.relationship || "Research output",
      ].filter(Boolean),
      judgement: "Selected work from your research record.",
      facts: [
        selectedWork.type ? `Type · ${selectedWork.type}` : null,
        selectedWork.relationship ? `Relation · ${selectedWork.relationship}` : null,
        selectedWork.raw && selectedWork.raw !== selectedWork.title
          ? `Source · publication highlight`
          : null,
      ].filter(Boolean).slice(0, 5),
      unknowns: [],
      primaryAction: { id: "ask-work", label: "Ask about this work" },
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  if (bound) {
    const name = profile.name_en || profile.name || "Faculty";
    const focus =
      (profile.research_tracks || []).find((t) => t && (t.title || t.name || typeof t === "string")) ||
      null;
    const focusTitle =
      typeof focus === "string" ? focus : String(focus?.title || focus?.name || "").trim();
    return {
      status: "context",
      identity: [
        name,
        [profile.title, profile.discipline].filter(Boolean).join(" · ") || "Faculty profile",
        profile.email || "",
      ].filter(Boolean),
      judgement: focusTitle
        ? `Active research context centres on ${focusTitle}.`
        : "Bound research context is available for ranking and Ask.",
      facts: [
        profile.email ? `Email · ${profile.email}` : null,
        Array.isArray(profile.specialties) && profile.specialties.length
          ? `Focus · ${profile.specialties.slice(0, 3).join(", ")}`
          : null,
        profile.paper_count_parsed || profile.paper_count
          ? `Works indexed · ${profile.paper_count_parsed || profile.paper_count}`
          : null,
      ].filter(Boolean).slice(0, 5),
      unknowns: [],
      primaryAction: { id: "edit-settings", label: "Edit identity", tab: "settings" },
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  // Unbound or unknown — explicit quiet state, never EXAMPLE / Loading
  return {
    status: "unbound",
    identity: ["Desk unbound", "No faculty email on this browser"],
    judgement: "Connect a faculty email to load Memory, Works, and Lab.",
    facts: ["Profile ranking uses generic desk defaults until bound."],
    unknowns: ["Faculty identity", "Research memory", "Lab links"],
    primaryAction: { id: "connect-email", label: "Connect faculty email", tab: "settings" },
    secondaryActions: [],
    loadingLabel: null,
  };
}

export function assertNoExamplePrimary(mode, command) {
  if (mode !== "unbound") return true;
  const label = String(command?.label || "").toLowerCase();
  return !/example|bind example|pilot/.test(label);
}
