/**
 * Pure provider-mark identity helpers (no asset imports — safe for node:test).
 */

/** Named providers that must resolve to a real bundled mark (not the generic glyph). */
export const NAMED_PROVIDER_MARK_IDS = [
  "lseg",
  "wrds",
  "crsp",
  "moveit",
  "capital_iq",
  "sec_edgar",
  "twse",
  "mops",
  "yahoo",
  "bigquery",
  "datacite",
  "huggingface",
  "zenodo",
  "openalex",
  "coingecko",
  "playwright",
  "tavily",
  "duckduckgo",
  "web",
  "vault",
  "registry",
  "discover",
  "web_discover",
  "probe",
  "http",
  "cluster",
];

/** Local asset filenames expected on disk for named + generic marks. */
export const PROVIDER_MARK_FILES = {
  lseg: "lseg.svg",
  wrds: "wrds.png",
  crsp: "crsp.svg",
  moveit: "moveit.png",
  capital_iq: "capital-iq.svg",
  sec_edgar: "sec-edgar.png",
  twse: "twse.png",
  mops: "mops.svg",
  yahoo: "yahoo-finance.png",
  bigquery: "bigquery.svg",
  datacite: "datacite.svg",
  huggingface: "huggingface.svg",
  zenodo: "zenodo.svg",
  openalex: "openalex.png",
  coingecko: "coingecko.png",
  playwright: "playwright.svg",
  tavily: "tavily.png",
  duckduckgo: "duckduckgo.svg",
  web: "web-arbitrary.svg",
  vault: "vault-dictionary.svg",
  registry: "registry-catalog.svg",
  discover: "discover-search.svg",
  web_discover: "duckduckgo.svg",
  probe: "source-probe.svg",
  http: "direct-http.svg",
  cluster: "cluster-jobs.svg",
  generic: "generic-route.svg",
};

export function providerMarkHaystack(row = {}) {
  return [
    row.key,
    row.id,
    row.label,
    row.name,
    row.endpoint,
    row.manifest?.id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/**
 * @param {object} row
 * @returns {string}
 */
export function identifyProviderMarkId(row = {}) {
  const hay = providerMarkHaystack(row);
  const key = String(row.key || row.id || "").toLowerCase();

  // Prefer explicit source/layer keys first (stable).
  if (key.includes("lseg") || key.includes("refinitiv")) return "lseg";
  if (key.includes("wrds")) return "wrds";
  if (key.includes("crsp_moveit") || key.includes("moveit")) return "moveit";
  if (key.includes("crsp")) return "crsp";
  if (key.includes("capital_iq") || key.includes("compustat")) return "capital_iq";
  if (key.includes("sec_edgar") || key.includes("edgar")) return "sec_edgar";
  if (key.includes("twse")) return "twse";
  if (key.includes("mops")) return "mops";
  if (key.includes("yfinance") || key.includes("yahoo")) return "yahoo";
  if (key.includes("coingecko")) return "coingecko";
  if (key.includes("bigquery") || key === "source-bq") return "bigquery";
  if (key.includes("datacite")) return "datacite";
  if (key.includes("huggingface") || key.includes("hugging_face")) return "huggingface";
  if (key.includes("open_research") || (key.includes("zenodo") && key.includes("openalex"))) return "zenodo";
  if (key.includes("zenodo")) return "zenodo";
  if (key.includes("openalex")) return "openalex";
  if (key.includes("web_generic") || key === "source-web") return "web";
  if (key.includes("web_discover") || key.includes("layer-web_discover")) return "web_discover";
  if (key.includes("discover_search") || key.includes("layer-discover")) return "discover";
  if (key.includes("probe")) return "probe";
  if (key.includes("direct_http") || key.includes("layer-http") || key.includes("curl")) return "http";
  if (key.includes("playwright") || key.includes("scrape")) return "playwright";
  if (key.includes("cluster") || key.includes("layer-jobs") || key.includes("layer-harvest")) return "cluster";
  if (key.includes("vault") || key.includes("dictionary") || key.includes("layer-collection")) return "vault";
  if (key.includes("registry") || key.includes("catalog")) return "registry";
  if (key.includes("tavily")) return "tavily";

  // Label / haystack fallbacks.
  if (/lseg|refinitiv/.test(hay)) return "lseg";
  if (/\bwrds\b/.test(hay)) return "wrds";
  if (/moveit/.test(hay)) return "moveit";
  if (/\bcrsp\b/.test(hay)) return "crsp";
  if (/capital\s*iq|compustat|s&p/.test(hay)) return "capital_iq";
  if (/sec\s*edgar|\bedgar\b/.test(hay)) return "sec_edgar";
  if (/\btwse\b/.test(hay)) return "twse";
  if (/\bmops\b/.test(hay)) return "mops";
  if (/yahoo\s*finance|yfinance/.test(hay)) return "yahoo";
  if (/bigquery|\bbq\b/.test(hay)) return "bigquery";
  if (/datacite/.test(hay)) return "datacite";
  if (/huggingface|hugging\s*face/.test(hay)) return "huggingface";
  if (/coingecko/.test(hay)) return "coingecko";
  if (/playwright/.test(hay)) return "playwright";
  if (/tavily/.test(hay)) return "tavily";
  if (/duckduckgo/.test(hay)) return "duckduckgo";
  if (/zenodo/.test(hay) && /openalex/.test(hay)) return "zenodo";
  if (/zenodo/.test(hay)) return "zenodo";
  if (/openalex/.test(hay)) return "openalex";
  if (/web discover/.test(hay)) return "web_discover";
  if (/vault dictionary|materialized collection/.test(hay)) return "vault";
  if (/registry catalog|on-disk handler/.test(hay)) return "registry";
  if (/discover search|profile-aware registry/.test(hay)) return "discover";
  if (/source probe|classify public url/.test(hay)) return "probe";
  if (/direct http|curl-equivalent/.test(hay)) return "http";
  if (/cluster jobs|queue · harvest/.test(hay)) return "cluster";
  if (/web \(arbitrary\)|arbitrary web/.test(hay)) return "web";

  return "generic";
}
