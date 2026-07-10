import { DISCOVER_SAMPLES, SEED_DATASETS } from "@/v2/deskSeed";

const SAMPLE_URLS = {
  twse_openapi_governance_ext: "https://openapi.twse.com.tw/",
  mops_financial_statements_ext: "https://mops.twse.com.tw/",
  datacite_ocean_temperature_ext: "https://doi.org/10.5281/zenodo.example",
};

function asExternalSample(row) {
  if (!row) return null;
  const id = row.dataset_id || row.title;
  return {
    ...row,
    kind: row.kind || "external",
    url: row.url || SAMPLE_URLS[id] || row.url,
  };
}

function asLabSuggestion(dataset) {
  if (!dataset) return null;
  return {
    dataset_id: dataset.dataset_id,
    title: dataset.name || dataset.title,
    name: dataset.name || dataset.title,
    source: dataset.source || "lab vault",
    collect_via: "local_open",
    coverage: dataset.coverage,
    grain: dataset.grain,
    license: dataset.license || "Vaulted",
    description: dataset.description || dataset.recommended_use || "Already registered in the lab vault",
    kind: "lab",
    local_ready: true,
  };
}

/**
 * Soft recommendations for Discover first-open (bottom mini-cards, not SERP).
 * Prefer curated external samples, then one in-lab holding so the strip isn't barren.
 */
export function discoverSuggestedRows({ catalog = [], labIds = new Set(), limit = 4 } = {}) {
  const external = (DISCOVER_SAMPLES.length ? DISCOVER_SAMPLES : [])
    .map(asExternalSample)
    .filter(Boolean);

  const pool = catalog.length ? catalog : SEED_DATASETS;
  const inLab = pool
    .filter((d) => {
      if (!d?.dataset_id) return false;
      if (labIds.size) return labIds.has(d.dataset_id);
      // Offline / empty labIds: prefer registered seed panels (not *_ext samples).
      return !String(d.dataset_id).endsWith("_ext");
    })
    .slice(0, 2)
    .map(asLabSuggestion)
    .filter(Boolean);

  const seen = new Set();
  const out = [];
  for (const row of [...external, ...inLab]) {
    const key = String(row.dataset_id || row.title || "").toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(row);
    if (out.length >= limit) break;
  }
  return out;
}
