/** Profiled recommendation clusters for Discover — mirrors faculty_profile.py routes. */

export const ROUTE_META = {
  vault: {
    label: "Lab stack",
    hint: "Vault pipelines built for your research — open or extend",
  },
  bigquery: {
    label: "BigQuery",
    hint: "On-chain panels — dry-run before export",
  },
  twse_openapi: {
    label: "Taiwan market",
    hint: "TWSE / MOPS equity and fundamentals",
  },
  datacite: {
    label: "DataCite",
    hint: "Comparable academic deposits (live catalog search)",
  },
  procure: {
    label: "Procure",
    hint: "Search and acquire from the open web",
  },
};

const ROUTE_ORDER = ["vault", "bigquery", "twse_openapi", "datacite", "procure"];

function shorten(text, max = 52) {
  const s = String(text || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}

export function clusterRecommendations(profile) {
  if (!profile || profile.unknown) return [];
  const raw = profile.recommendation_clusters;
  const clusters = raw && typeof raw === "object" && !Array.isArray(raw)
    ? raw
    : groupByRoute(profile.procurement_recommendations || []);

  return ROUTE_ORDER
    .filter((route) => (clusters[route] || []).length > 0)
    .map((route) => ({
      route,
      ...(ROUTE_META[route] || ROUTE_META.procure),
      items: clusters[route],
    }));
}

function groupByRoute(recs) {
  const out = {};
  for (const rec of recs) {
    const route = rec.source_route || "procure";
    if (!out[route]) out[route] = [];
    out[route].push(rec);
  }
  return out;
}

export function profileStarterClickables(profile) {
  if (!profile || profile.unknown) return { chatStarters: [], searchStarters: [] };

  const chatStarters = (profile.starter_prompts || []).map((prompt, i) => ({
    id: `chat-${i}`,
    label: shorten(prompt, 56),
    prompt: String(prompt).trim(),
    action: "chat",
  }));

  const searchStarters = [];
  for (const scope of profile.datacite_scopes || []) {
    for (const [i, seed] of (scope.seed_queries || []).slice(0, 2).entries()) {
      searchStarters.push({
        id: `dc-${scope.id || "scope"}-${i}`,
        label: shorten(seed, 40),
        prompt: String(seed).trim(),
        action: "search",
        route: "datacite",
        scopeId: scope.id,
      });
    }
  }

  for (const hint of profile.bigquery_hints || []) {
    searchStarters.push({
      id: `bq-${hint.registry_id}`,
      label: shorten(hint.label || hint.registry_id, 40),
      prompt: `Dry-run BigQuery export for ${hint.label || hint.registry_id}`,
      action: "chat",
      route: "bigquery",
      registryId: hint.registry_id,
    });
  }

  return { chatStarters, searchStarters };
}

export function primaryTrackTitle(profile) {
  const tracks = profile?.research_tracks || [];
  if (!tracks.length) return "";
  const top = [...tracks].sort((a, b) => (Number(b.weight) || 0) - (Number(a.weight) || 0))[0];
  return top?.title || "";
}

export function recommendationClickAction(rec) {
  const route = rec?.source_route || "procure";
  if (route === "vault" && rec?.dataset_id) return "open";
  if (route === "bigquery") return "chat";
  if (route === "datacite") return "search";
  if (route === "twse_openapi") return "chat";
  return "search";
}
