const GENERIC_PROMPTS = [
  "What query-ready datasets do we already hold for my research?",
  "Find missing public datasets we should collect into the lab vault.",
  "Summarize what is in the Research panels folder.",
  "What procurement approvals or jobs need attention right now?",
];

/** Profile-aware suggested asks — mirrors faculty_profile cold_start_prompts priority. */
export function homeSuggestedPrompts(profile, { limit = 4 } = {}) {
  const cap = Math.max(1, Math.min(limit, 6));
  if (!profile || profile.unknown) {
    return GENERIC_PROMPTS.slice(0, cap);
  }

  const starters = (profile.starter_prompts || []).map((s) => String(s).trim()).filter(Boolean);
  if (starters.length) {
    return starters.slice(0, cap);
  }

  const fromRecs = (profile.procurement_recommendations || [])
    .map((row) => String(row?.prompt || "").trim())
    .filter(Boolean);
  if (fromRecs.length) {
    return fromRecs.slice(0, cap);
  }

  const defaultQuery = String(profile.default_search_query || "").trim();
  if (defaultQuery) {
    return [`Search the vault and registries for ${defaultQuery}`, ...GENERIC_PROMPTS].slice(0, cap);
  }

  return GENERIC_PROMPTS.slice(0, cap);
}
