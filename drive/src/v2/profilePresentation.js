/**
 * Profile centre + Detail rail presentation helpers.
 * Bound: deterministic research understanding, then Memory → Works → Lab.
 * Unbound: one compact zero-state (no empty Memory/Works/Lab shells).
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

/** Bound desks render understanding + Memory → Works → Lab; unbound renders none of those shells. */
export function profileSectionsVisible(profile) {
  return isProfileBound(profile);
}

export function profilePrimaryCommand(mode) {
  if (mode === "unbound") {
    // Binding lives inline on Research context — no handoff to Workspace preferences.
    return { id: "connect-email", label: "Connect faculty email", inline: true };
  }
  return null;
}

/** Compact unbound centre copy — one truthful zero state, no pilot identity. */
export function buildUnboundProfileCentre() {
  return {
    badge: "Unbound",
    title: "No researcher context",
    lead: "Connect a faculty email to load research understanding for this browser.",
    hint: "Faculty email is a contextual preference saved on this browser — not a sign-in.",
    primary: profilePrimaryCommand("unbound"),
  };
}

/**
 * Detail rail state. Never returns generic "Loading" once the page has a profile
 * payload (bound, unknown, or explicitly unbound/null-resolved).
 *
 * Bound (no work): show derivation/provenance of the understanding block —
 * not a verbatim restatement of centre synthesis.
 * Sticky primary only for real Ask / Connect actions.
 */
export function buildProfileRailState({
  profile = null,
  selectedWork = null,
  profileResolved = false,
  understanding = null,
} = {}) {
  const bound = isProfileBound(profile);

  if (!profileResolved && profile == null) {
    return {
      status: "unbound",
      identity: ["Desk unbound", "No researcher context"],
      judgement: "Connect a faculty email in Research context to bind this browser.",
      facts: [
        "Binding · browser preference (not authentication)",
        "Ranking · generic desk defaults until bound",
      ],
      unknowns: [],
      provenance: [],
      primaryAction: { id: "connect-email", label: "Connect faculty email", inline: true },
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
      ].filter(Boolean),
      judgement: "Selected work — Ask opens with this title as structured context.",
      facts: [
        selectedWork.relationship ? `Theme · ${selectedWork.relationship}` : null,
        "Does not change saved research context.",
      ].filter(Boolean).slice(0, 4),
      unknowns: [],
      provenance: [{ kind: "works", label: "Publication highlight selection" }],
      primaryAction: { id: "ask-work", label: "Ask about this work" },
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  if (bound) {
    const name = profile.name_en || profile.name || "Faculty";
    const role = [profile.title, profile.discipline].filter(Boolean).join(" · ") || "Faculty profile";
    const provenance = understanding?.provenance?.length
      ? understanding.provenance
      : [
          profile.specialties?.length ? { kind: "memory", label: "Saved research focus" } : null,
          (profile.research_tracks || []).length
            ? { kind: "tracks", label: "Research tracks on file" }
            : null,
          (profile.publication_highlights || []).length
            ? { kind: "works", label: "Publication highlights" }
            : null,
          (profile.lab_fintech_stack || []).length
            ? { kind: "lab", label: "Linked lab evidence" }
            : null,
        ].filter(Boolean);

    const derivationFacts = [
      ...(understanding?.facts || []).slice(0, 3),
      "Interpretation is deterministic from those inputs — not a model conclusion.",
      "Shapes Discover ranking and Ask context on this browser only.",
    ].filter(Boolean).slice(0, 5);

    return {
      status: "context",
      identity: [name, role],
      judgement: "Derivation of the centre understanding — facts and sources, not a restated synopsis.",
      facts: derivationFacts,
      unknowns: (understanding?.unknowns || []).slice(0, 3),
      provenance,
      primaryAction: understanding?.askContext
        ? { id: "ask-context", label: "Ask about this context" }
        : null,
      secondaryActions: [],
      loadingLabel: null,
    };
  }

  return {
    status: "unbound",
    identity: ["Desk unbound", "No researcher context"],
    judgement: "Connect a faculty email in Research context to bind this browser.",
    facts: [
      "Binding · browser preference (not authentication)",
      "Ranking · generic desk defaults until bound",
    ],
    unknowns: [],
    provenance: [],
    primaryAction: { id: "connect-email", label: "Connect faculty email", inline: true },
    secondaryActions: [],
    loadingLabel: null,
  };
}

export function assertNoExamplePrimary(mode, command) {
  if (mode !== "unbound") return true;
  const label = String(command?.label || "").toLowerCase();
  return !/example|bind example|pilot/.test(label);
}

/** Build a concrete Ask prompt from structured profile context — no invented claims. */
export function buildProfileContextAskPrompt(askContext) {
  if (!askContext || askContext.kind !== "profile_context") return "";
  const lines = [
    "Ask about this bound research context.",
    askContext.name ? `Researcher: ${askContext.name}` : null,
    askContext.synthesis ? `System reading: ${askContext.synthesis}` : null,
    askContext.threads?.length ? `Threads seen: ${askContext.threads.join("; ")}` : null,
    askContext.held ? `Most relevant held evidence: ${askContext.held}` : null,
    askContext.missing ? `Important missing evidence: ${askContext.missing}` : null,
    askContext.provenance?.length
      ? `Interpretation sources: ${askContext.provenance.join("; ")}`
      : null,
    askContext.facts?.length ? `Facts on file: ${askContext.facts.join(" | ")}` : null,
    askContext.unknowns?.length ? `Unknowns: ${askContext.unknowns.join("; ")}` : null,
    "Explain how Discover ranking and Ask should use this structured context. Do not invent facts beyond these inputs.",
  ].filter(Boolean);
  return lines.join("\n");
}
