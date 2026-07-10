import { DISCOVER_SUGGESTIONS } from "@/v2/deskSeed";

const COMMON_FALLBACK = ["TWSE governance", "MOPS filings", "stablecoin", "DataCite DOI"];

/** Profile-ranked Discover empty-state queries (same priority as Home suggested asks). */
export function discoverSuggestedQueries(profile, { limit = 6 } = {}) {
  const common = (DISCOVER_SUGGESTIONS.length ? DISCOVER_SUGGESTIONS : COMMON_FALLBACK).map(String);
  if (!profile || profile.unknown) {
    return { profileQueries: [], commonQueries: common.slice(0, limit) };
  }

  const fromRecs = (profile.procurement_recommendations || [])
    .flatMap((row) => [row?.search_query, row?.title, row?.query])
    .map((s) => String(s || "").trim())
    .filter(Boolean);

  const fromTracks = (profile.research_tracks || [])
    .map((t) => (typeof t === "string" ? t : t?.title || t?.name))
    .filter(Boolean)
    .slice(0, 2)
    .map((t) => `${t} dataset`);

  const defaultQ = String(profile.default_search_query || "").trim();
  const fromTags = (profile.domain_tags || []).slice(0, 2).map((t) => `${t} public data`);

  const profileQueries = [...new Set([defaultQ, ...fromRecs, ...fromTracks, ...fromTags].filter(Boolean))].slice(
    0,
    limit,
  );
  const commonQueries = common.filter((q) => !profileQueries.includes(q)).slice(0, 4);

  return { profileQueries, commonQueries };
}
