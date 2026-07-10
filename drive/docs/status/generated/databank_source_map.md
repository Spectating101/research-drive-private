# Databank source map audit

Generated: 2026-07-07T11:19:04+00:00

## Summary

- Registry datasets: **158**
- Mapped to a source system: **158**
- Unmapped: **0**
- Source systems defined: **24**

## Sources

### LSEG Workspace / EDP (YZU seat) (`lseg_edp`)
- **Mode:** materialized_instant · **Status:** frozen_release · **Materialized:** yes · **Registry cards:** 9 (9 instant)
- **Desk connector:** LSEG Workspace / EDP (YZU seat)
- **Capabilities:** index_pit_survivorship, estimates_revisions, fundamentals, risk_overlay, daily_prices
- **Geographies:** US, Taiwan, Indonesia, Japan, Korea, Singapore
- **Gaps:** institutional_ownership license-blocked; StarMine / SmartEstimate license-blocked; FQ PIT fundamentals blocked; FY via FRQ=FY only; US vol daily history thin on EDP — use desktop rescue lane
- **Note:** Bulk harvest STOP. Targeted entitlement probes only.

### LSEG Eikon desktop rescue (US vol/skew/SI) (`lseg_desktop_rescue`)
- **Mode:** materialized_instant · **Status:** rescued_snapshot · **Materialized:** yes · **Registry cards:** 1 (1 instant)
- **Desk connector:** LSEG Workspace / EDP (YZU seat)
- **Capabilities:** risk_overlay
- **Geographies:** US
- **Note:** ~15.6M rows US vol/skew/SI; complements thin EDP vol history.

### In-house derived research panels (`derived_research_panels`)
- **Mode:** derived_internal · **Status:** active · **Materialized:** yes · **Registry cards:** 19 (18 instant)
- **Capabilities:** entity_news_shocks, country_news_shocks, daily_prices, estimates_revisions, index_pit_survivorship, entity_join_gdelt_ric
- **Geographies:** US, Taiwan, Indonesia, Japan, Korea, Asia_multi_13

### GDELT news graph (`gdelt`)
- **Mode:** materialized_bulk · **Status:** active · **Materialized:** yes · **Registry cards:** 2 (2 instant)
- **Desk connector:** GDELT
- **Capabilities:** country_news_shocks, entity_news_shocks, entity_join_gdelt_ric
- **Geographies:** Asia_multi_13, US, Macro_global
- **Bulk:** ~165 GiB normalized under news_shock_taxonomy/normalized; registry cards are thin instant surface only.

### WRDS — CRSP + Compustat (+ CCM) (`wrds_crsp_compustat`)
- **Mode:** planned · **Status:** not_available_on_desk · **Materialized:** no · **Registry cards:** 0 (0 instant)
- **Desk connector:** WRDS (CRSP · Compustat · CCM)
- **Capabilities:** daily_prices, fundamentals, index_pit_survivorship
- **Geographies:** US
- **Gaps:** Credentials in .env.local do not authenticate to WRDS; Desk uses CRSP MOVEit + Capital IQ instead
- **Note:** Optional future if YZU library provides WRDS account. Superseded operationally by crsp_moveit + capital_iq_compustat.

### CRSP MOVEit Cloud (`crsp_moveit`)
- **Mode:** materialized_bulk · **Status:** wired_manifest · **Materialized:** yes · **Registry cards:** 4 (0 instant)
- **Desk connector:** CRSP MOVEit Cloud
- **Capabilities:** daily_prices, index_pit_survivorship
- **Geographies:** US
- **Note:** Subscriber bulk via crsp.moveitcloud.com. SFTP/FTPS scripting with same credentials.

### S&P Capital IQ / Compustat (`capital_iq_compustat`)
- **Mode:** materialized_bulk · **Status:** pending_export · **Materialized:** yes · **Registry cards:** 1 (0 instant)
- **Desk connector:** S&P Capital IQ / Compustat
- **Capabilities:** fundamentals
- **Geographies:** US
- **Note:** Web seat verified. Export fundamentals to data_lake/compustat/raw/ — no enterprise XpressAPI on this seat.

### Google BigQuery (public datasets) (`bigquery_public`)
- **Mode:** live_connector · **Status:** active · **Materialized:** live/partial · **Registry cards:** 1 (0 instant)
- **Desk connector:** Google BigQuery
- **Capabilities:** onchain_crypto
- **Geographies:** Crypto_global
- **Note:** Live remote SQL; USDT Ethereum flow pack materialized as catalogue card + RPC pilot CSVs.

### DataCite metadata harvest (operator bulk) (`datacite_harvest`)
- **Mode:** materialized_bulk · **Status:** active · **Materialized:** yes · **Registry cards:** 1 (0 instant)
- **Desk connector:** DataCite
- **Bulk:** ~32 GiB sharded JSONL harvest; procurement search substrate, not professor partition.

### DataCite DOI procured datasets (`datacite_procured`)
- **Mode:** procurement_catalog · **Status:** active · **Materialized:** yes · **Registry cards:** 8 (5 instant)
- **Desk connector:** DataCite

### SEC EDGAR (`sec_edgar`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** yes · **Registry cards:** 3 (0 instant)
- **Desk connector:** SEC EDGAR
- **Capabilities:** governance_regulatory
- **Geographies:** US

### TWSE Open API (`twse_official`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** yes · **Registry cards:** 1 (0 instant)
- **Desk connector:** TWSE Open API
- **Capabilities:** governance_regulatory, daily_prices
- **Geographies:** Taiwan

### Taiwan MOPS / governance procured (`mops_taiwan`)
- **Mode:** procurement_catalog · **Status:** procurement_wired · **Materialized:** yes · **Registry cards:** 1 (0 instant)
- **Desk connector:** MOPS Taiwan
- **Capabilities:** governance_regulatory
- **Geographies:** Taiwan

### Yahoo Finance (yfinance) (`yfinance_public`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** yes · **Registry cards:** 1 (1 instant)
- **Desk connector:** Yahoo Finance
- **Capabilities:** daily_prices
- **Geographies:** US, Asia_multi_13
- **Note:** Alpha paper panel + queue universes; not CRSP-quality US equity history.

### CoinGecko (`coingecko`)
- **Mode:** live_connector · **Status:** active · **Materialized:** live/partial · **Registry cards:** 27 (0 instant)
- **Desk connector:** CoinGecko
- **Capabilities:** daily_prices, onchain_crypto
- **Geographies:** Crypto_global

### Ethereum / USDT on-chain (`ethereum_onchain`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** yes · **Registry cards:** 4 (1 instant)
- **Desk connector:** Google BigQuery
- **Capabilities:** onchain_crypto
- **Geographies:** Crypto_global

### Web scrape index (sites saved to disk) (`web_scrape_catalog`)
- **Mode:** procurement_catalog · **Status:** active · **Materialized:** live/partial · **Registry cards:** 35 (29 instant)
- **Desk connector:** Web (arbitrary)

### Lab procured downloads (non-DOI) (`procured_misc`)
- **Mode:** procurement_catalog · **Status:** active · **Materialized:** live/partial · **Registry cards:** 27 (20 instant)
- **Desk connector:** Web (arbitrary)

### Hugging Face datasets (`huggingface`)
- **Mode:** live_connector · **Status:** active · **Materialized:** live/partial · **Registry cards:** 0 (0 instant)
- **Desk connector:** HuggingFace

### Zenodo · OpenAlex · external catalogs (`open_research_catalogs`)
- **Mode:** live_connector · **Status:** active · **Materialized:** live/partial · **Registry cards:** 3 (0 instant)
- **Desk connector:** Zenodo · OpenAlex

### Reddit ingest (`reddit_social`)
- **Mode:** materialized_bulk · **Status:** active · **Materialized:** no · **Registry cards:** 0 (0 instant)
- **Desk connector:** Reddit
- **Capabilities:** social_sentiment

### Public macro baselines (Ken French etc.) (`public_macro`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** yes · **Registry cards:** 1 (1 instant)
- **Desk connector:** Public macro baseline
- **Geographies:** Macro_global

### Investment / ops platform JSON snapshots (`ops_investment_platform`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** live/partial · **Registry cards:** 8 (7 instant)

### OpenSea NFT metadata (`nft_opensea`)
- **Mode:** materialized_instant · **Status:** active · **Materialized:** live/partial · **Registry cards:** 1 (0 instant)
- **Desk connector:** Web (arbitrary)
- **Capabilities:** onchain_crypto

