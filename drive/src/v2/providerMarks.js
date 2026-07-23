/**
 * Resources Source capabilities — local provider marks (no remote logo URLs).
 * See assets/providers/ATTRIBUTION.md for provenance.
 */

import bigqueryMark from "@/v2/assets/providers/bigquery.svg";
import capitalIqMark from "@/v2/assets/providers/capital-iq.svg";
import clusterJobsMark from "@/v2/assets/providers/cluster-jobs.svg";
import coingeckoMark from "@/v2/assets/providers/coingecko.png";
import crspMark from "@/v2/assets/providers/crsp.svg";
import dataciteMark from "@/v2/assets/providers/datacite.svg";
import directHttpMark from "@/v2/assets/providers/direct-http.svg";
import discoverSearchMark from "@/v2/assets/providers/discover-search.svg";
import duckduckgoMark from "@/v2/assets/providers/duckduckgo.svg";
import genericRouteMark from "@/v2/assets/providers/generic-route.svg";
import huggingfaceMark from "@/v2/assets/providers/huggingface.svg";
import lsegMark from "@/v2/assets/providers/lseg.svg";
import mopsMark from "@/v2/assets/providers/mops.svg";
import moveitMark from "@/v2/assets/providers/moveit.png";
import openalexMark from "@/v2/assets/providers/openalex.png";
import playwrightMark from "@/v2/assets/providers/playwright.svg";
import registryCatalogMark from "@/v2/assets/providers/registry-catalog.svg";
import secEdgarMark from "@/v2/assets/providers/sec-edgar.png";
import sourceProbeMark from "@/v2/assets/providers/source-probe.svg";
import tavilyMark from "@/v2/assets/providers/tavily.png";
import twseMark from "@/v2/assets/providers/twse.png";
import vaultDictionaryMark from "@/v2/assets/providers/vault-dictionary.svg";
import webArbitraryMark from "@/v2/assets/providers/web-arbitrary.svg";
import wrdsMark from "@/v2/assets/providers/wrds.png";
import yahooFinanceMark from "@/v2/assets/providers/yahoo-finance.png";
import zenodoMark from "@/v2/assets/providers/zenodo.svg";
import {
  identifyProviderMarkId,
  NAMED_PROVIDER_MARK_IDS,
  PROVIDER_MARK_FILES,
  providerMarkHaystack,
} from "@/v2/providerMarkIds";

export {
  identifyProviderMarkId,
  NAMED_PROVIDER_MARK_IDS,
  PROVIDER_MARK_FILES,
  providerMarkHaystack,
};

/** @typedef {{ id: string, src: string, alt: string, title: string, wide?: boolean, generic?: boolean }} ProviderMark */

/** @type {Record<string, Omit<ProviderMark, 'id'>>} */
const MARKS = {
  lseg: { src: lsegMark, alt: "LSEG", title: "LSEG Workspace / EDP", wide: true },
  wrds: { src: wrdsMark, alt: "WRDS", title: "Wharton Research Data Services", wide: true },
  crsp: { src: crspMark, alt: "CRSP", title: "CRSP" },
  moveit: { src: moveitMark, alt: "MOVEit", title: "Progress MOVEit" },
  capital_iq: { src: capitalIqMark, alt: "S&P Capital IQ", title: "S&P Capital IQ / Compustat" },
  sec_edgar: { src: secEdgarMark, alt: "SEC", title: "SEC EDGAR" },
  twse: { src: twseMark, alt: "TWSE", title: "Taiwan Stock Exchange" },
  mops: { src: mopsMark, alt: "MOPS", title: "MOPS Taiwan" },
  yahoo: { src: yahooFinanceMark, alt: "Yahoo Finance", title: "Yahoo Finance" },
  bigquery: { src: bigqueryMark, alt: "Google BigQuery", title: "Google BigQuery" },
  datacite: { src: dataciteMark, alt: "DataCite", title: "DataCite" },
  huggingface: { src: huggingfaceMark, alt: "Hugging Face", title: "Hugging Face" },
  zenodo: { src: zenodoMark, alt: "Zenodo", title: "Zenodo" },
  openalex: { src: openalexMark, alt: "OpenAlex", title: "OpenAlex" },
  coingecko: { src: coingeckoMark, alt: "CoinGecko", title: "CoinGecko" },
  playwright: { src: playwrightMark, alt: "Playwright", title: "Playwright" },
  tavily: { src: tavilyMark, alt: "Tavily", title: "Tavily" },
  duckduckgo: { src: duckduckgoMark, alt: "DuckDuckGo", title: "DuckDuckGo" },
  web: { src: webArbitraryMark, alt: "Web", title: "Web (arbitrary)" },
  vault: { src: vaultDictionaryMark, alt: "Vault dictionary", title: "Vault dictionary" },
  registry: { src: registryCatalogMark, alt: "Registry catalog", title: "Registry catalog" },
  discover: { src: discoverSearchMark, alt: "Discover search", title: "Discover search" },
  web_discover: { src: duckduckgoMark, alt: "Web discover", title: "Web discover" },
  probe: { src: sourceProbeMark, alt: "Source probe", title: "Source probe" },
  http: { src: directHttpMark, alt: "Direct HTTP", title: "Direct HTTP" },
  cluster: { src: clusterJobsMark, alt: "Cluster jobs", title: "Cluster jobs" },
  generic: {
    src: genericRouteMark,
    alt: "Source route",
    title: "Source route",
    generic: true,
  },
};

/**
 * Resolve a compact local mark for a source/layer capability row.
 * Prefers official/bundled logos for named providers; never invents two-letter badges.
 *
 * @param {object} row
 * @returns {ProviderMark}
 */
export function resolveProviderMark(row = {}) {
  const id = identifyProviderMarkId(row);
  const base = MARKS[id] || MARKS.generic;
  const hay = providerMarkHaystack(row);

  if (id === "zenodo" && /zenodo/.test(hay) && /openalex/.test(hay)) {
    return {
      id,
      ...base,
      alt: "Zenodo and OpenAlex",
      title: "Zenodo · OpenAlex",
    };
  }

  if (id === "generic") {
    const label = String(row.label || row.name || "Source route");
    return {
      id: "generic",
      ...MARKS.generic,
      alt: `${label} route`,
      title: label,
    };
  }

  return { id, ...base };
}

export function providerMarkAssetMap() {
  return { ...MARKS };
}
