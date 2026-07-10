# Databank dataset coverage map

Generated: 2026-07-07T11:19:09+00:00

Dataset-level coverage + proxy/synthetic paths. Registry cards are the query surface; collections hold bulk bytes; proxies declare how thin cells can still be researched.

## Summary

- Datasets profiled: **158** (94 instant)
- Materialized instant panels: **30** (disk probed: 30)
- Collection partitions: **25**
- Bulk-rich / thin registry surface: `news.gdelt-asia, news.gdelt-expanded, catalog.datacite-harvest, markets.crypto-landscape, markets.crypto-coingecko, markets.equities-asia, ops.spectator-archives, ops.cluster-jobs, reference.crsp-moveit`
- Proxy capability blocks: **7**

## Collections (bulk vs registry surface)

### GDELT Asia news graph & shock panels (`news.gdelt-asia`)
- Disk: 343.81 GiB · instant cards: 1 · registry cards: 1
- Time span: 2018–ongoing (Asia backfill + rolling)
- Latent capabilities: country_news_shocks, entity_news_shocks
- Surface vs bulk: Country-day instant panel + URL index; bulk holds full GKG normalized shards (~156 GiB)
- Synthetic paths:
  - asia_country_week_news_market_primary → country broadcast to tickers
  - daily_ticker_entity_shock_panel → entity shock (thin window today)
  - entity_market_spine + GDELT bridge → ric-level shocks

### GDELT expanded news graph (Asia + US/EU/MENA adjunct) (`news.gdelt-expanded`)
- Disk: 157.92 GiB · instant cards: 1 · registry cards: 1
- Time span: US/EU/MENA adjunct
- Latent capabilities: country_news_shocks, entity_news_shocks
- Surface vs bulk: URL/event index on disk; expanded normalized bulk under gdelt_gkg_expanded_bulk

### DataCite metadata harvest (operator bulk) (`catalog.datacite-harvest`)
- Disk: 4.99 GiB · instant cards: 0 · registry cards: 0
- Time span: DataCite network (harvest shards y2025–y2026)
- Latent capabilities: governance_regulatory
- Surface vs bulk: 32 GiB metadata harvest; procurement search substrate — bytes via datacite_collect_doi
- Synthetic paths:
  - datacite_search → datacite_collect_doi → acquired.procured partition

### Curated dataset index (human-readable) (`catalog.curated-index`)
- Disk: 135.57 GiB · instant cards: 29 · registry cards: 41

### Crypto protocol & token landscape snapshots (`markets.crypto-landscape`)
- Disk: 12.03 GiB · instant cards: 0 · registry cards: 0

### CoinGecko daily price archive (local cache) (`markets.crypto-coingecko`)
- Disk: 3.82 GiB · instant cards: 0 · registry cards: 27
- Latent capabilities: daily_prices, onchain_crypto
- Surface vs bulk: Live API at query time; cards are instrument catalogue not history mirror

### Ethereum USDT on-chain flows (professor package) (`markets.ethereum-usdt`)
- Disk: 4.5 MiB · instant cards: 1 · registry cards: 4
- Latent capabilities: onchain_crypto
- Surface vs bulk: Catalogue + pilots; BigQuery public ethereum tables reachable live

### Asia equity prices & ticker universes (`markets.equities-asia`)
- Disk: 2.82 GiB · instant cards: 0 · registry cards: 0

### OpenSea NFT collection metadata (`markets.nft-opensea`)
- Disk: 538 KiB · instant cards: 0 · registry cards: 1

### Taiwan TWSE exchange OpenAPI snapshots (`official.exchange-disclosures`)
- Disk: 194.6 MiB · instant cards: 0 · registry cards: 0

### Taiwan MOPS & governance procured files (`official.mops-disclosures`)
- Disk: 9.7 MiB · instant cards: 0 · registry cards: 1

### Asia public macro & market baselines (`official.macro-asia`)
- Disk: 152.5 MiB · instant cards: 1 · registry cards: 1

### Asia ticker & entity resolution maps (`reference.entity-mapping-asia`)
- Disk: 23.8 MiB · instant cards: 0 · registry cards: 0

### US SEC EDGAR ticker ↔ CIK reference (`reference.sec-edgar`)
- Disk: 169.0 MiB · instant cards: 0 · registry cards: 0

### Refinitiv complete harvest 2026-07-06 (frozen) (`reference.refinitiv-backfill`)
- Disk: 55.3 MiB · instant cards: 10 · registry cards: 10
- Time span: run 2026-07-06-complete (PIT monthly, estimates daily, fundamentals annual)
- Latent capabilities: index_pit_survivorship, estimates_revisions, fundamentals, risk_overlay, entity_join_gdelt_ric
- Surface vs bulk: Frozen EDP harvest; derived panels in research_panels/refinitiv/

### Reddit raw ingest & sentiment archive (`social.reddit`)
- Disk: 87.4 MiB · instant cards: 0 · registry cards: 0

### Chat & DOI procured downloads (`acquired.procured`)
- Disk: 479.9 MiB · instant cards: 25 · registry cards: 37
- Latent capabilities: governance_regulatory
- Surface vs bulk: Metadata cards; bytes on disk when collect completed

### Merged research panels (analysis-ready) (`derived.research-panels`)
- Disk: 1.53 GiB · instant cards: 18 · registry cards: 19

### Web scrape archives (local USB) (`ops.spectator-archives`)
- Disk: 1.55 GiB · instant cards: 0 · registry cards: 0

### YZU cluster job state (local only) (`ops.cluster-jobs`)
- Disk: 1004.8 MiB · instant cards: 0 · registry cards: 0

### CRSP US Stock & Index (MOVEit) (`reference.crsp-moveit`)
- Disk: 5.03 GiB · instant cards: 1 · registry cards: 5
- Time span: 1925+ US stock and index history
- Latent capabilities: daily_prices, index_pit_survivorship
- Surface vs bulk: MOVEit Product_Downloads; manifest wired; daily CIZ pending download

### Compustat fundamentals (Capital IQ export) (`reference.compustat-capitaliq`)
- Disk: 212 B · instant cards: 0 · registry cards: 1
- Latent capabilities: fundamentals
- Surface vs bulk: Capital IQ web export → data_lake/compustat/raw/


## Instant datasets with disk coverage

- **`cross_asset_fused_primary_panel`** — 5,694 rows · 2018-01-05 00:00:00 → 2026-05-29 00:00:00 · caps: — · geo: —
- **`ticker_week_country_broadcast_panel`** — 460,103 rows · 2016-05-27 00:00:00 → 2026-05-29 00:00:00 · caps: — · geo: —
- **`ticker_week_entity_market_panel`** — 1,713 rows · 2026-05-01 00:00:00 → 2026-05-29 00:00:00 · caps: — · geo: —
- **`ticker_week_entity_long_panel`** — 460,103 rows · 2016-05-27 00:00:00 → 2026-05-29 00:00:00 · caps: — · geo: —
- **`ticker_week_entity_residual_panel`** — 6,199 rows · 2023-10-06 00:00:00 → 2025-05-02 00:00:00 · caps: — · geo: —
- **`refinitiv_security_master`** — 570 rows · 2026-07-06T10:44:16.646351+00:00 → 2026-07-06T10:44:16.646351+00:00 · caps: entity_join_gdelt_ric · geo: —
- **`refinitiv_index_membership_pit`** — 548,460 rows · 2010-01-15 → 2026-06-15 · caps: index_pit_survivorship · geo: US, Indonesia, Japan, Korea, Taiwan, Asia_multi_13
- **`refinitiv_corporate_actions_snapshot`** — 570 rows · 2026-07-06T11:09:03.219469+00:00 → 2026-07-06T11:09:03.219469+00:00 · caps: daily_prices · geo: —
- **`refinitiv_risk_tape_daily`** — 733,528 rows · 2015-01-01 → 2026-07-06 · caps: risk_overlay · geo: —
- **`refinitiv_estimate_revisions_daily`** — 576,968 rows · 2017-09-20 → 2026-07-06 · caps: estimates_revisions · geo: —
- **`refinitiv_rescued_us_risk_desktop`** — 15,572,700 rows · 2014-12-31 → 2025-12-15 · caps: risk_overlay · geo: US
- **`refinitiv_fundamentals_snapshot`** — 797 rows · 2026-07-06T11:18:30.663312+00:00 → 2026-07-06T11:22:51.508816+00:00 · caps: fundamentals · geo: —
- **`refinitiv_index_membership_current`** — 2,641 rows · 2026-07-06T11:22:57.709868+00:00 → 2026-07-06T11:23:05.660951+00:00 · caps: index_pit_survivorship · geo: —
- **`refinitiv_analyst_consensus_snapshot`** — 570 rows · 2026-07-06T11:17:10.255155+00:00 → 2026-07-06T11:17:10.255155+00:00 · caps: estimates_revisions · geo: —
- **`refinitiv_esg_snapshot`** — 570 rows · 2026-07-06T11:17:11.579214+00:00 → 2026-07-06T11:17:11.579214+00:00 · caps: governance_regulatory · geo: —
- **`refinitiv_survivorship_universe_panel`** — 548,460 rows · 2010-01 → 2026-06 · caps: index_pit_survivorship, daily_prices · geo: —
- **`refinitiv_us_risk_overlay`** — 234,971 rows · 2015-01-01 → 2026-07-06 · caps: risk_overlay · geo: US
- **`refinitiv_estimate_revision_panel`** — 98,873 rows · 2017-10-19 → 2026-07-06 · caps: estimates_revisions · geo: US, Taiwan, Indonesia, Japan, Korea
- **`refinitiv_fundamental_annual_panel`** — 227 rows · nan → nan · caps: fundamentals · geo: US, Taiwan, Indonesia
- **`refinitiv_entity_market_spine`** — 570 rows · 2026-07-06T12:31:59.687370+00:00 → 2026-07-06T12:31:59.687370+00:00 · caps: entity_join_gdelt_ric, daily_prices · geo: —
- **`idn_fry_daily_cross_section`** — 1,043,042 rows · 2019-07-16 00:00:00 → 2026-05-18 00:00:00 · caps: daily_prices, risk_overlay, entity_news_shocks · geo: Indonesia
- **`idn_fry_episode_gdelt_features`** — 5,734 rows · caps: — · geo: —
- **`idn_episode_reward_daily`** — 52,175 rows · 2022-03-02 00:00:00 → 2026-05-14 00:00:00 · caps: — · geo: —
- **`asia_country_week_news_market_primary`** — 5,671 rows · 2018-01-05 00:00:00 → 2026-05-29 00:00:00 · caps: country_news_shocks · geo: —
- **`daily_ticker_entity_shock_panel`** — 6,659 rows · 2026-05-01 00:00:00 → 2026-05-25 00:00:00 · caps: entity_news_shocks, entity_join_gdelt_ric · geo: —
- **`jkse_pit_idn_microstructure_revisions`** — 180,774 rows · 2010-01 → 2026-06 · caps: estimates_revisions, index_pit_survivorship · geo: —
- **`pit_index_revision_momentum`** — 548,460 rows · 2010-01 → 2026-06 · caps: estimates_revisions, index_pit_survivorship · geo: —
- **`public_macro_ff_factors_daily`** — 26,253 rows · 1926-07-01 00:00:00 → 2026-05-29 00:00:00 · caps: daily_prices · geo: —
- **`refinitiv_entity_market_spine_expanded`** — 570 rows · caps: entity_join_gdelt_ric · geo: —
- **`public_equity_us_sp500_yfinance_daily`** — 1,221,685 rows · 2016-07-06 04:00:00 → 2026-07-06 04:00:00 · caps: — · geo: —

## Proxy & synthetic coverage paths

### US × `daily_prices` (effective rank 2)
- [primary] CRSP daily CIZ (MOVEit) — **pending_ingest** (rank 3)
- [proxy] Refinitiv survivorship sample — **materialized** (rank 2)
- [proxy] yfinance multi-asset paper panel (13 names) — **materialized** (rank 2)
- [proxy] EDP OHLCV bulk intentionally skipped — **skipped** (rank 1)

### US × `entity_news_shocks` (effective rank 2)
- [synthetic] Entity shock panel (short window) — **thin** (rank 2)
- [synthetic] Country-week broadcast to constituents (ecological) — **proxy** (rank 2)
- [synthetic] GDELT shock → estimate revision event study — **recipe** (rank 3)
- [proxy] GKG bulk US adjunct not entity-instant yet — **bulk_latent** (rank 1)

### US × `entity_join_gdelt_ric` (effective rank 2)
- [direct] ~10.9% spine bridged to GDELT entity — **materialized** (rank 2)
- [synthetic] Fuzzy ticker/name bridge expansion — **recipe** (rank 3)

### Indonesia × `daily_prices` (effective rank 3)
- [direct] IDN FRY daily cross-section — **materialized** (rank 3)
- [synthetic] JKSE PIT × IDN micro × revisions — **built** (rank 3)
- [proxy] JKSE PIT membership filter — **materialized** (rank 2)

### Crypto_global × `onchain_crypto` (effective rank 2)
- [primary] BigQuery crypto_ethereum public tables — **on_demand** (rank 3)
- [direct] USDT flow catalogue card — **catalogue** (rank 2)
- [synthetic] Skynet + GDELT + DeFiLlama synthesis — **built** (rank 2)
- [proxy] CoinGecko prices as liquidity proxy — **live** (rank 2)

### Macro_global × `governance_regulatory` (effective rank 2)
- [primary] 32 GiB DOI metadata search — **bulk_metadata** (rank 2)
- [proxy] 8 procured DOI datasets on disk — **per_doi** (rank 2)
- [proxy] Zenodo/OpenAlex discover → collect — **live** (rank 2)

### Asia_multi_13 × `country_news_shocks` (effective rank 3)
- [direct] GDELT Asia country-day panel — **materialized** (rank 3)
- [direct] Fused country-week news+market — **materialized** (rank 3)
- [proxy] Full GKG shards — rebuild panels on demand — **bulk_latent** (rank 2)


## Built synthesis recipes

- **JKSE PIT × IDN microstructure × estimate revisions** (`jkse_pit_idn_microstructure_revisions`) — joins: ric, as_of_month, yahoo_symbol
- **Skynet + Etherscan stablecoin synthesis** (`skynet_etherscan_stablecoin`) — joins: primary_ethereum_address
- **Stablecoin trust ↔ engagement (full synthesis)** (`stablecoin_trust_engagement`) — joins: entity_id

