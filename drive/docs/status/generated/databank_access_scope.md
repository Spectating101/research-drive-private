# Databank access scope (entitlements vs materialized)

Generated: 2026-07-07T11:19:05+00:00

Declarative desk entitlements — what we CAN reach via license, connector, or public access. Independent of vault bytes and registry card count. Materialized truth lives in databank_research_coverage.json.

## Summary

- Entitlement sources: **21**
- Accessible cells (partial+): **42** / 99
- Gap cells (reachable but thin/absent on disk): **8**
- Materialized matrix loaded: **True**

## Entitlement heatmap (what we CAN reach)

| Geography | Prices | CtyNews | EntNews | Fund | Est/Rev | PIT | Risk | Join | Gov | Social | Chain |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US | not_wired | full | partial | not_wired | full | full | partial | partial | partial | partial | blocked |
| Taiwan | partial | blocked | blocked | partial | full | full | partial | blocked | partial | blocked | blocked |
| Indonesia | partial | blocked | partial | partial | partial | full | partial | blocked | blocked | blocked | blocked |
| Japan | partial | blocked | blocked | partial | partial | full | blocked | blocked | blocked | blocked | blocked |
| Korea | partial | blocked | blocked | partial | partial | full | blocked | blocked | blocked | blocked | blocked |
| HK_SG_ASEAN | blocked | blocked | blocked | blocked | blocked | blocked | blocked | blocked | blocked | blocked | blocked |
| Asia_multi_13 | partial | full | partial | blocked | blocked | full | blocked | partial | blocked | blocked | blocked |
| Crypto_global | on_demand | blocked | blocked | blocked | blocked | blocked | blocked | blocked | blocked | partial | on_demand |
| Macro_global | partial | full | blocked | blocked | blocked | blocked | blocked | blocked | on_demand | on_demand | blocked |

## Materialized heatmap (0–3 instant-panel scores)

| Geography | Prices | CtyNews | EntNews | Fund | Est/Rev | PIT | Risk | Join | Gov | Social | Chain |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US | 2 | 1 | 1 | 2 | 3 | 3 | 2 | 1 | 2 | 1 | 2 |
| Taiwan | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 1 | 2 | 1 | 1 |
| Indonesia | 3 | 2 | 2 | 2 | 2 | 3 | 2 | 2 | 2 | 2 | 1 |
| Japan | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 1 | 1 | 1 | 1 |
| Korea | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 1 | 1 | 1 | 1 |
| HK_SG_ASEAN | 2 | 2 | 1 | 1 | 2 | 2 | 1 | 1 | 1 | 1 | 1 |
| Asia_multi_13 | 2 | 3 | 2 | 1 | 1 | 2 | 2 | 2 | 1 | 1 | 2 |
| Crypto_global | 2 | 2 | 2 | 0 | 0 | 0 | 2 | 2 | 1 | 2 | 3 |
| Macro_global | 2 | 2 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |

## Priority gaps (accessible but not materialized)

- **US** × `country_news_shocks` — accessible `full`, materialized 1 (entitlement_gap) via gdelt
- **Japan** × `fundamentals` — accessible `partial`, materialized 1 (entitlement_gap) via lseg_edp
- **Korea** × `fundamentals` — accessible `partial`, materialized 1 (entitlement_gap) via lseg_edp
- **Taiwan** × `fundamentals` — accessible `partial`, materialized 1 (entitlement_gap) via lseg_edp
- **Taiwan** × `risk_overlay` — accessible `partial`, materialized 1 (entitlement_gap) via lseg_edp
- **US** × `entity_join_gdelt_ric` — accessible `partial`, materialized 1 (entitlement_gap) via derived_research_panels, gdelt, lseg_edp
- **US** × `entity_news_shocks` — accessible `partial`, materialized 1 (entitlement_gap) via derived_research_panels, gdelt
- **US** × `social_sentiment` — accessible `partial`, materialized 1 (entitlement_gap) via reddit_social

## Sources (entitlement view)

### `lseg_edp` — active
- License: YZU university EDP / Workspace seat
- Fetch: lseg_data_api, entitlement_probe, frozen_release_read
- Products: Security master / TRBC; PIT index membership (US + Asia 0# indices); Corporate actions; Consensus estimates + revision history; PIT fundamentals (FY; FQ blocked); Vol / skew / put-call / short interest (thin US daily on EDP)
- **Blocked:** institutional_ownership — G1 ownership not on YZU EDP
- **Blocked:** supply_chain — I1 supply chain graph not on EDP
- **Blocked:** estimates_revisions — StarMine / SmartEstimate license-blocked

### `lseg_desktop_rescue` — active
- License: Desktop Eikon export (operator)
- Fetch: desktop_export, frozen_release_read
- Products: US vol / skew / put-call / short-interest daily history

### `crsp_moveit` — active
- License: YZU CRSP subscriber (MOVEit)
- Fetch: moveit_web, sftp_ftps, manifest
- Products: CRSP US Stock 2.5 CIZ ASCII; CRSP US Index 1925+; Index History quarterly release
- Note: MOVEit login verified. Manifest task crsp_moveit_manifest enabled.

### `capital_iq_compustat` — active
- License: YZU Capital IQ seat
- Fetch: capital_iq_web_export
- Products: Compustat North America fundamentals; Capital IQ Financials screens
- Note: Okta login verified. No WRDS; manual or scripted export path.

### `wrds_crsp_compustat` — unavailable
- License: Wharton WRDS
- Note: Desk credentials do not authenticate. Ask library if institutional WRDS desired.

### `gdelt` — public
- Fetch: bulk_download, doc_api, pipeline_harvest
- Products: GKG 2.0; Events; DOC API; country/entity taxonomy overlays

### `bigquery_public` — active
- License: GCP ADC + public dataset catalog
- Fetch: bigquery_sql, dry_run, mcp_live_query
- Products: bigquery-public-data.crypto_ethereum.*; bigquery-public-data.crypto_bitcoin.*; US census / NOAA / other public tables (on demand)

### `datacite_harvest` — public
- Fetch: bulk_harvest, search_index
- Products: DataCite DOI metadata graph (~all registered DOIs)

### `datacite_procured` — public
- Fetch: datacite_collect_doi, per_doi_download
- Products: Any open DataCite DOI dataset

### `sec_edgar` — public
- Fetch: http_manifest, queue_harvest

### `twse_official` — public
- Fetch: twse_openapi, queue_harvest

### `mops_taiwan` — public
- Fetch: web_scrape, queue_collect

### `yfinance_public` — public
- Fetch: yfinance_api, queue_panel_build

### `coingecko` — active
- License: CoinGecko API key
- Fetch: live_api, registry_quote_cards

### `ethereum_onchain` — public
- Fetch: ethereum_rpc, bigquery_public, local_csv

### `reddit_social` — public
- Fetch: reddit_api, bulk_ingest

### `public_macro` — public
- Fetch: ken_french_zip, queue_download

### `huggingface` — public
- Fetch: hf_datasets_api, mcp_search

### `open_research_catalogs` — public
- Fetch: zenodo_api, openalex_api, web_discover

### `web_scrape_catalog` — public
- Fetch: probe_url, playwright_scrape, yzu_submit_job

### `derived_research_panels` — internal
- Fetch: internal_build
- Note: Derived from upstream sources; ceiling follows bridge quality (~10.9% spine).

## LSEG entitlement probe (frozen run)

- Run: `2026-07-06-complete` — pass 9, fail 3
- Blocked: Institutional ownership — Institutional ownership fields not on YZU EDP
- Blocked: Supply chain suppliers / customers — Supply chain graph fields not on YZU EDP
- Blocked: StarMine / SmartEstimate probe — StarMine / SmartEstimate fields not on YZU EDP

