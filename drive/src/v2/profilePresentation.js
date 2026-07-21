/**
 * Profile centre + Detail rail presentation helpers.
 * Bound centre model is exactly Memory → Works → Lab.
 * Unbound centre is a single zero-state (no empty Memory/Works/Lab shells).
 */

export const PROFILE_SECTION_ORDER = Object.freeze(["memory", "works", "lab"]);

/** Explicit local test identity only — never an automatic fallback or EXAMPLE CTA. */
export const PROFILE_TEST_EMAIL = "drkong@saturn.yzu.edu.tw";

export function isProfileBound(profile) {
  return Boolean(profile && !profile.unknown);
}

/** Unbound desks stay quiet — never auto-promote EXAMPLE / pilot as the primary centre. */
export function profileCentreMode(profile) {
  return isProfileBound(profile) ? "bound" : "unbound";
}

/** Bound desks render Memory → Works → Lab; unbound renders none of those shells. */
export function profileSectionsVisible(profile) {
  return isProfileBound(profile);
}

export function profilePrimaryCommand(mode) {
  if (mode === "unbound") {
    return { id: "connect-email", label: "Open Settings", tab: "settings" };
  }
  return null;
}

/** Compact unbound centre copy — one truthful zero state, no pilot identity. */
export function buildUnboundProfileCentre() {
  return {
    badge: "Unbound",
    title: "No researcher context",
    lead: "Connect a faculty email in Settings to load Memory, Works, and Lab for this browser.",
    hint: "Faculty email is a contextual preference saved on this browser — not a sign-in.",
    primary: profilePrimaryCommand("unbound"),
  };
}

function unboundRailState() {
  return {
    status: "unbound",
    identity: ["Desk unbound", "No researcher context"],
    judgement: "Save a faculty email in Settings to bind research context for this browser.",
    facts: [
      "Binding · browser preference (not authentication)",
      "Ranking · generic desk defaults until bound",
    ],
    unknowns: [],
    primaryAction: { id: "connect-email", label: "Open Settings", tab: "settings" },
    secondaryActions: [],
    loadingLabel: null,
  };
}

/**
 * Detail rail state. Never returns generic "Loading" once the page has a profile
 * payload (bound, unknown, or explicitly unbound/null-resolved).
 * Unbound Detail stays compact — identity/context facts only, no Memory/Works/Lab lists.
 */
export function buildProfileRailState({
  profile = null,
  selectedWork = null,
  profileResolved = false,
} = {}) {
  const bound = isProfileBound(profile);

  if (!profileResolved && profile == null) {
    return unboundRailState();
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
      primaryAction: { id: "edit-settings", label: "Edit faculty email", tab: "settings" },
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  // Unbound or unknown registry stub — quiet zero state, never EXAMPLE / Loading / fabricated name
  return unboundRailState();
}

export function assertNoExamplePrimary(mode, command) {
  if (mode !== "unbound") return true;
  const label = String(command?.label || "").toLowerCase();
  return !/example|bind example|pilot|drkong/.test(label);
}

/** Guard: pilot test email must never appear unless explicitly stored by the operator. */
export function assertNoAutomaticPilotIdentity(storedEmail = "") {
  const stored = String(storedEmail || "").trim().toLowerCase();
  if (!stored) return true;
  return stored === PROFILE_TEST_EMAIL.toLowerCase() ? Boolean(stored) : true;
}
