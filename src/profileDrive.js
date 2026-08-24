/** Profile-aware dataset ranking for drive visibility (mirrors faculty_profile.py). */

const TOKEN_RE = /[a-z][a-z0-9_]{2,}/g;

const DOMAIN_DEMOTE_WHEN_ABSENT = {
  social_media: ["coingecko", "gdelt", "fair", "climate"],
  marketing_consumer: ["gdelt", "fair", "climate", "patent"],
  org_behavior: ["coingecko", "gdelt", "crypto", "bitcoin", "opensea"],
  psychology_survey: ["coingecko", "gdelt", "crypto", "equities"],
  patents: ["coingecko", "gdelt", "consumer", "brand"],
  accounting: ["coingecko", "gdelt", "opensea", "nft"],
  green_marketing: ["gdelt", "crypto", "bitcoin"],
};

const DOMAIN_BOOST_TOKENS = {
  fintech: ["fintech", "crypto", "bitcoin", "ethereum", "coingecko", "blockchain", "defi", "usdt", "stablecoin", "bigquery"],
  equities: ["equity", "stock", "return", "twse", "crsp", "factor"],
  econometrics: ["panel", "time series", "econometric", "regression"],
  machine_learning: ["machine learning", "ml", "neural", "prediction"],
  social_media: ["social", "influencer", "youtube", "instagram", "brand", "community"],
  marketing_consumer: ["consumer", "retail", "survey", "brand", "purchase"],
  patents: ["patent", "uspto", "citation", "invention"],
  forecasting: ["forecast", "diffusion", "foresight"],
  org_behavior: ["survey", "leadership", "team", "workplace", "hrm"],
  psychology_survey: ["scale", "psycholog", "stress", "personality"],
  accounting: ["accounting", "audit", "earnings", "financial statement", "esg"],
  international_business: ["fdi", "international", "trade", "diversification"],
  taiwan_market: ["taiwan", "twse", "mops"],
  asia_pacific: ["asia", "gdelt", "country"],
  banking: ["bank", "credit", "lending"],
  corporate_finance: ["corporate", "governance", "sec", "edgar"],
};

function rowBlob(row) {
  return [
    row?.name,
    row?.dataset_id,
    row?.description,
    row?.recommended_use,
    row?.backend,
    row?.local_root,
    row?.local_path,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function profileTags(profile) {
  return new Set((profile?.domain_tags || []).map((t) => String(t)));
}

/** Ingestion / backfill outputs — not personal uploads, not default Lab Drive root folders. */
export function isPipelineDataset(row) {
  const raw = String(row?.local_root || row?.local_path || "");
  if (raw.includes("news_shock_taxonomy")) return true;
  if (raw.includes("dataset_catalog")) return true;
  if (String(row?.analysis_readiness || "") === "metadata_search") return true;
  if (String(row?.backend || "").includes("catalog")) return true;
  return false;
}

export function profileDatasetScore(row, profile) {
  if (!profile || profile.unknown) return 0;
  const blob = rowBlob(row);
  const tags = profileTags(profile);
  let delta = 0;

  for (const tag of tags) {
    for (const needle of DOMAIN_BOOST_TOKENS[tag] || []) {
      if (blob.includes(needle)) delta += 0.35;
    }
  }

  const absentDemote = new Set();
  for (const [tag, needles] of Object.entries(DOMAIN_DEMOTE_WHEN_ABSENT)) {
    if (tags.has(tag)) continue;
    for (const n of needles) absentDemote.add(n);
  }
  for (const needle of absentDemote) {
    if (blob.includes(needle)) delta -= 0.6;
  }

  const preferred = new Set((profile.preferred_sources || []).map((s) => String(s).toLowerCase()));
  if (preferred.has("twse_openapi") && blob.includes("twse")) delta += 0.5;
  if (preferred.has("bigquery") && (blob.includes("bigquery") || blob.includes("usdt") || blob.includes("ethereum_usdt"))) delta += 0.45;
  if (preferred.has("datacite") && blob.includes("datacite")) delta += 0.25;

  const keywords = (profile.research_keywords || []).map((k) => String(k).toLowerCase());
  for (const kw of keywords) {
    if (kw.length >= 5 && blob.includes(kw)) delta += 0.25;
  }

  return delta;
}

/** Default Lab Drive: profile-matched analysis datasets; pipelines tucked away unless matched. */
export function filterDatasetsForProfile(datasets, profile, { includeAll = false, pipelineMinScore = 0.55 } = {}) {
  if (includeAll || !profile || profile.unknown) return datasets || [];
  const minScore = 0.15;
  return (datasets || []).filter((row) => {
    const score = profileDatasetScore(row, profile);
    if (isPipelineDataset(row)) return score >= pipelineMinScore;
    return score >= minScore;
  });
}

export function pickProfileShowcase(datasets, profile, limit = 6) {
  const rows = datasets || [];
  if (!profile || profile.unknown) return rows.slice(0, limit);
  return [...rows]
    .map((d) => ({ d, score: profileDatasetScore(d, profile) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((x) => x.d);
}
