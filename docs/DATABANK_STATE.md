# YZU Cluster — Databank State (equal-weight inventory)

**Snapshot:** 2026-07-06  
**Audience:** Operators and researchers — what exists, where it lives, how to query it.  
**Principle:** No single lane is the “center.” GDELT, Refinitiv, Indonesia panels, crypto scrapes, procured downloads, and live APIs are **peer components** of one catalog.

**Neutral inventory only.** Ranked next steps and activation work live in [`DESK_ACTIVATION.md`](DESK_ACTIVATION.md) and should be filtered through `research_faculty_profile` — not prescribed globally here.

Regenerate machine-readable audits:

```bash
python3 scripts/databank_coverage_report.py          # registry + disk + partitions
python3 scripts/databank_research_coverage.py      # capability matrix + synthesis catalog
```

Outputs: `docs/status/generated/databank_coverage_report.json`, `docs/status/generated/databank_research_coverage.md`, `drive/docs/status/generated/platform_progress.json`

Run `python3 drive/scripts/sync_drive_platform_state.py` to refresh the **drive/** canonical copies.

---

## 1. What this is

YZU Cluster is a **research databank with three simultaneous jobs**:

| Job | Mechanism |
|-----|-----------|
| **Catalog** | 150 registry cards — search, describe, procure |
| **Query** | 41 instant datasets — filter/project without re-downloading |
| **Collect** | Job queue + MCP tools + GDrive vault write-back |

Physical files, metadata cards, and live remote connectors are **different layers of the same inventory**, not separate products.

Related scope docs: [`DESK_STATUS.md`](DESK_STATUS.md) (faculty desk), [`STORAGE_ARCHITECTURE.md`](STORAGE_ARCHITECTURE.md) (tiers), [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md) (MCP/HTTP).

---

## 2. Headline numbers (2026-07-06)

| Measure | Value |
|---------|------:|
| Registry datasets | **150** |
| Instant-query (`analysis_readiness: instant`) | **41** |
| Metadata / search-only | **104** |
| Professor-visible collection partitions | **22** |
| Live desk source connectors | **14** |
| Synthesis profiles (`config/synthesis_profiles.json`) | **3** |
| Parquet panels under `data_lake/research_panels/` | **94 files** (~1.51 GiB) |
| Registry IDs not mapped to a partition | **93** (mostly scrape/metadata catalog) |

---

## 3. Registry families (equal weight)

Counts from `config/research_query_registry.json`. None of these “wins” — they answer different questions.

| Family | Registry cards | Instant-query | Typical backend | Role |
|--------|---------------:|--------------:|-----------------|------|
| **Web scrape catalog** | 61 | 0 | `local_json_glob`, `local_file` | Indexed scrapes (sites, APIs saved to disk); searchable, not always panelized |
| **Procured catalog** | 36 | 0 | `local_json_file`, `local_file` | Chat/DOI/manual downloads; procurement flywheel targets |
| **Refinitiv institutional** | 15 | 15 | `local_parquet_panel` | PIT membership, estimates, fundamentals, spine, risk |
| **Instant ops / investment JSON** | 14 | 14 | `local_json_file` | Platform snapshots (accounting, gates, capability audit) |
| **Asia derived panels** | 10 | 7 | `local_parquet_panel` | Country-week news+market, cross-asset fused, ticker-week |
| **Metadata other** | 5 | 0 | mixed | Reference rows, harvest status |
| **GDELT / news shock** | 3 | 3 | `local_gdelt_panel_csv` | Country-day Asia panel, high-priority URL index |
| **Crypto / NFT** | 3 | 0 | mixed | CoinGecko catalog, OpenSea, stablecoin packs |
| **Indonesia regional** | 3 | 3 | `local_parquet_panel` | FRY daily, episode GDELT features, episode reward daily |
| **Live remote** | 1 | 0 | `coingecko_simple_price_api` | Query-time API (plus BigQuery catalogue card) |

**Read:** The majority of registry **count** is catalog/procurement (97 cards). The majority of **instant** cards split across Refinitiv (15), ops JSON (14), Asia derived (7), GDELT (3), Indonesia (2).

---

## 4. Three access modes (use the right layer)

```text
A. INSTANT     analysis_readiness = instant     → query engine / MCP research_query_dataset
B. METADATA    analysis_readiness = metadata_search → discover + procure + describe
C. LIVE        desk_sources.json connectors      → BigQuery, SEC, TWSE, DataCite, … at request time
```

| Mode | Count | When to use |
|------|------:|-------------|
| A Instant | 41 | You need rows now (parquet, CSV, JSON snapshot) |
| B Metadata | 104 | You need to know something exists and how to acquire it |
| C Live | 14 connectors | Bytes are not mirrored locally; query remote with ADC/API |

BigQuery and HuggingFace are **live connectors** — not fully duplicated as instant registry panels unless a job materializes them.

---

## 5. Where bytes live (storage map)

Tier policy: `config/storage_tiers.json` — **GDrive vault = canonical**, NVMe = hot/query, USB/Transcend = bulk cache.

### 5.1 Local `data_lake/` lanes (NVMe + symlinks)

| Path | ~Size | Contents |
|------|------:|----------|
| `data_lake/news_shock_taxonomy/normalized/` | **165 GiB** | GDELT GKG/events normalized bulk (often symlinked to Transcend) |
| `data_lake/research_panels/` | **1.51 GiB** | Derived parquet panels (all lanes) |
| `data_lake/yzu_cluster/` | **1.0 GiB** | Job artifacts, cluster run outputs |
| `data_lake/procured/` | **480 MiB** | Procured download staging |
| `data_lake/refinitiv_backfill/rescued_desktop_20251215/` | **20 MiB** | Rescued US risk desktop merge |
| `data_lake/refinitiv_backfill/2026-07-06-complete/` | **6 MiB** | Frozen Refinitiv complete harvest (processed parquet) |

### 5.2 Canonical vault (GDrive)

`gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data`  
Professor share: `collection/` only — see [`VAULT_LAYOUT.md`](VAULT_LAYOUT.md), [`GDRIVE_WHERE_TO_LOOK.md`](GDRIVE_WHERE_TO_LOOK.md).

### 5.3 Bulk cache (USB / Transcend)

`RESEARCH_BULK_ROOT` — mirrors for GDELT, crypto pipeline, coingecko archive when NVMe symlink present.

---

## 6. Collection partitions (22 professor-visible)

Authority: `config/collection_partitions.json`. Partitions are **organizational labels on Drive**, not research priority ranks.

| Partition ID | Domain | Status | Registry IDs |
|--------------|--------|--------|-------------:|
| `news.gdelt-asia` | news | migrated | 2 |
| `news.gdelt-expanded` | news | active | 0 |
| `catalog.curated-index` | catalog | migrated | 0 |
| `markets.crypto-landscape` | markets | migrated | 0 |
| `markets.crypto-coingecko` | markets | synced | 26 |
| `markets.ethereum-usdt` | markets | — | 1 |
| `markets.equities-asia` | markets | migrated | 0 |
| `markets.nft-opensea` | markets | synced | 1 |
| `official.exchange-disclosures` | official | migrated | 1 |
| `official.mops-disclosures` | official | procurement_wired | 1 |
| `official.macro-asia` | official | migrated | 0 |
| `reference.entity-mapping-asia` | reference | migrated | 0 |
| `reference.sec-edgar` | reference | migrated | 1 |
| `reference.refinitiv-backfill` | markets | frozen_release | 15 |
| `social.reddit` | social | migrated | 0 |
| `acquired.procured` | acquired | migrated | 3 |
| `derived.research-panels` | derived | migrated | 12 |
| `derived.research-models` | derived | migrated | 0 |
| `ops.pipeline-manifests` | ops | migrated | 0 |
| `ops.spectator-archives` | ops | synced | 0 |
| `ops.collection-queue` | ops | migrated | 0 |
| `ops.cluster-jobs` | ops | local_only | 0 |

---

## 7. Instant-query catalog (41 datasets)

Authority: `config/research_query_registry.json`. Query via:

```bash
bash scripts/run_research_query_engine.sh    # HTTP :8765
bash scripts/run_research_data_mcp.sh        # MCP stdio
```

### 7.1 Refinitiv institutional (15)

| dataset_id | Grain | Primary path |
|------------|-------|--------------|
| `refinitiv_security_master` | instrument snapshot | `data_lake/refinitiv_backfill/2026-07-06-complete/processed/` |
| `refinitiv_index_membership_pit` | index × as-of × constituent | same |
| `refinitiv_index_membership_current` | index × constituent snapshot | same |
| `refinitiv_estimate_revisions_daily` | ric × day × metric | same |
| `refinitiv_risk_tape_daily` | ric × day × metric | same |
| `refinitiv_fundamentals_snapshot` | instrument snapshot | same |
| `refinitiv_corporate_actions_snapshot` | instrument snapshot | same |
| `refinitiv_analyst_consensus_snapshot` | instrument snapshot | same |
| `refinitiv_esg_snapshot` | instrument snapshot | same |
| `refinitiv_rescued_us_risk_desktop` | ric × day × metric | `refinitiv_backfill/rescued_desktop_20251215/processed/` |
| `refinitiv_survivorship_universe_panel` | index × month × constituent | `research_panels/refinitiv/2026-07-06-complete/` |
| `refinitiv_us_risk_overlay` | ric × day | same |
| `refinitiv_estimate_revision_panel` | ric × day | same |
| `refinitiv_fundamental_annual_panel` | ric × fiscal_year | same |
| `refinitiv_entity_market_spine` | ric snapshot | same |

Frozen run ID: **`2026-07-06-complete`**. Promotion script: `scripts/refinitiv_promote_registry.py`. Derived build: `scripts/refinitiv_build_derived_panels.py`.

### 7.2 GDELT / news shock (3)

| dataset_id | Grain | Path |
|------------|-------|------|
| `gdelt_asia_daily_country_panel` | country × day | `data_lake/news_shock_taxonomy/processed/` (CSV; may resolve via bulk root) |
| `gdelt_high_priority_urls` | url event | `data_lake/news_shock_taxonomy/` |
| *(bulk not a card)* | event/GKG | `data_lake/news_shock_taxonomy/normalized/` ~165 GiB |

### 7.3 Asia derived / cross-asset (7 instant)

| dataset_id | Grain | Path |
|------------|-------|------|
| `asia_country_week_news_market_primary` | country × week | `research_panels/asia_news_market/asia_news_market_auto_latest/` |
| `cross_asset_fused_primary_panel` | country × week | `research_panels/cross_asset_fused/fused_20260610_v2/` |
| `daily_ticker_entity_shock_panel` | ticker × day | `research_panels/ticker_news_market/ticker_20260615/` |
| `ticker_week_country_broadcast_panel` | ticker × week | `research_panels/ticker_news_market/ticker_20260610/` |
| `ticker_week_entity_market_panel` | ticker × week | `research_panels/ticker_news_market/ticker_20260611/` |
| `ticker_week_entity_long_panel` | ticker × week | same |
| `ticker_week_entity_residual_panel` | ticker × week | `research_panels/ticker_news_market/ticker_20260610/` |

### 7.4 Indonesia regional (3)

| dataset_id | Grain | Path |
|------------|-------|------|
| `idn_fry_daily_cross_section` | ticker × day | `research_panels/idn_fry_episode/daily_cross_section.parquet` |
| `idn_fry_episode_gdelt_features` | episode | `research_panels/idn_fry_episode/episode_gdelt_features.parquet` |
| `idn_episode_reward_daily` | episode × day | `research_panels/idn_episode_reward/daily_episodes.parquet` |

### 7.5 Cross-lane synthesis panels (2)

Built by merge scripts; same query path as other parquet panels.

| dataset_id | Inputs | Grain | Build | Path |
|------------|--------|-------|-------|------|
| `pit_index_revision_momentum` | PIT all 6 indices + estimate revisions + spine | index × ric × month | `scripts/build_pit_revision_momentum_panel.py` | `research_panels/pit_revision_momentum/pit_index_revision_momentum.parquet` |
| `jkse_pit_idn_microstructure_revisions` | JKSE PIT + IDN FRY monthly + estimates + spine | ric × month | `scripts/build_jkse_pit_idn_microstructure_revisions.py` | `research_panels/jkse_pit_idn/jkse_pit_idn_microstructure_revisions.parquet` |

**`pit_index_revision_momentum` summary:** 548,460 rows · 6 indices (.SPX, .JKSE, .TWII, .N225, .KS11, .STI) · 2010-01 → 2026-06 · estimate match ~0.88% of rows (222 RIC revision history vs 2,770 PIT constituents).

**`jkse_pit_idn_microstructure_revisions` summary:** 180,774 rows · JKSE only · IDN feature match ~29% · estimate match ~2.1%.

### 7.6 Ops / investment / misc instant (14)

Platform JSON snapshots: `investment_*`, `collection_queue_status`, `datacite_local_harvest_status`, `sec_company_tickers`, `spk_v1_*`, etc. Paths under `data_lake/` per registry `local_root`.

---

## 8. Live desk connectors (14)

Authority: `config/desk_sources.json`

| ID | Role |
|----|------|
| `gdelt` | GDELT remote / bulk hydration |
| `sec_edgar` | US filings index |
| `twse` | Taiwan exchange |
| `mops` | Taiwan MOPS disclosures |
| `yfinance` | Public OHLCV |
| `macro_public` | Macro baselines |
| `coingecko` | Crypto prices/metadata |
| `bigquery` | USDT / on-chain catalogues (ADC) |
| `datacite` | DOI metadata + harvest |
| `huggingface` | Dataset/model cards |
| `open_research` | Academic open repos |
| `reddit` | Social ingest |
| `web_generic` | Generic probe/collect |
| `gdrive_vault` | Vault read/write |

---

## 9. Synthesis profiles (multi-source merge recipes)

Authority: `config/synthesis_profiles.json`  
Run: MCP `research_synthesis_run(profile_id=...)` or HTTP `POST /library/synthesis/run`

| Profile ID | Type | Sources (peer) | Output area |
|------------|------|----------------|-------------|
| `jkse_pit_idn_microstructure_revisions` | `jkse_pit_idn` | PIT + IDN FRY + estimates + spine | `data_lake/research_panels/jkse_pit_idn/` |
| `skynet_etherscan_stablecoin` | `skynet_etherscan` | CertiK Skynet + Etherscan scrapes | `data_lake/synthesis/skynet_etherscan_stablecoin/` |
| `stablecoin_trust_engagement` | `trust_engagement` | Skynet + Etherscan + DeFiLlama + GDELT crypto overlay + Wikipedia + GitHub + incidents | `data_lake/synthesis/stablecoin_trust_engagement/` |

Synthesis is **optional merge tooling** — not a replacement for the registry cards above.

---

## 10. Research coverage axes (how good is coverage?)

Neutral scoring — no lane is the reference standard. Regenerate: `python3 scripts/databank_research_coverage.py`

### 10.1 Capability × geography matrix

Scores per cell: **—** absent · **thin** · **partial** · **strong**

| Geography | Prices | Cty news | Entity news | Fund | Est/rev | PIT | Risk | Entity join | Gov | Social | On-chain |
|-----------|--------|----------|-------------|------|---------|-----|------|-------------|-----|--------|----------|
| US | partial | thin | thin | partial | strong | strong | partial | thin | partial | thin | partial |
| Taiwan | partial | partial | thin | thin | partial | strong | thin | thin | partial | thin | thin |
| Indonesia | strong | partial | partial | partial | partial | strong | partial | partial | partial | partial | thin |
| Japan | partial | partial | thin | thin | partial | strong | thin | thin | thin | thin | thin |
| Korea | partial | partial | thin | thin | partial | strong | thin | thin | thin | thin | thin |
| HK/SG/ASEAN | partial | partial | thin | thin | partial | partial | thin | thin | thin | thin | thin |
| Asia (13-country) | partial | strong | partial | thin | thin | partial | partial | partial | thin | thin | partial |
| Crypto global | partial | partial | partial | — | — | — | partial | partial | thin | partial | strong |
| Macro global | partial | partial | thin | — | — | — | thin | — | — | — | thin |

### 10.2 Time depth (longitudinal spans)

| Source family | Span | Scale |
|---------------|------|-------|
| Refinitiv PIT | 2010 → 2026-06 | 548k rows · 6 indices |
| Refinitiv estimate revisions | 2017-10 → 2026-07 | 99k rows · 222 RICs |
| IDN FRY daily | 2019-07 → 2026-05 | 1.04M rows · 635 tickers |
| Asia / cross-asset country-week | 2018-01 → 2026-05 | 13 countries · 438 weeks |
| GDELT normalized bulk | ~2015 → 2026 | ~165 GiB |
| Ticker entity shock (current run) | 2026-05 slice | 25 trading days |

### 10.3 Join quality (applies to all event↔market work)

| Join | Coverage | Notes |
|------|----------|-------|
| GDELT entity → RIC (spine) | 62 / 570 (10.9%) | Binding constraint for **entity-level** cross-source studies |
| PIT constituent → ric | Full per index | Use for survivorship-correct universes |
| yahoo_symbol ↔ .JK RIC | 634 / 913 JKSE PIT names | Direct suffix match |
| Estimate panel → PIT | 222 RICs globally | Sparse vs 2,770 PIT constituents |

---

## 11. Enabled collection queue (ETL scripts)

Authority: `config/data_collection_queue.json` (enabled tasks only):

- `public_macro_market_baseline`
- `sec_company_tickers`
- `coingecko_daily`
- `reddit_ingest_daily`
- `stablecoin_skynet_harvest`
- `opensea_metadata_sidecar`
- `entity_mapping_asia`
- `refinitiv_backfill` *(frozen — disabled in production)*

---

## 12. Key config files (index)

| File | Question it answers |
|------|---------------------|
| `config/research_query_registry.json` | What datasets exist? Instant or metadata? Query backend? |
| `config/collection_partitions.json` | How is GDrive `collection/` organized? |
| `config/desk_sources.json` | What live connectors exist? |
| `config/synthesis_profiles.json` | What multi-source merge recipes exist? |
| `config/data_collection_queue.json` | What ETL can jobs run? |
| `config/storage_tiers.json` | GDrive vs NVMe vs USB roles |
| `config/yzu_cluster.json` | Pipelines, worker routing, GDrive roots |
| `config/platform_integration.json` | Alpha/platform cycle wiring (separate from desk) |

---

## 13. Operator commands

| Task | Command |
|------|---------|
| Full partition/registry audit | `python3 scripts/databank_coverage_report.py` |
| Capability matrix + synthesis list | `python3 scripts/databank_research_coverage.py` |
| Wire new panels into registry | `python3 scripts/promote_derived_research_panels.py` |
| Build institutional cross-lane panel | `python3 scripts/build_pit_revision_momentum_panel.py` |
| Build IDN regional cross-lane panel | `python3 scripts/build_jkse_pit_idn_microstructure_revisions.py` |
| Build Refinitiv derived panels | `python3 scripts/refinitiv_build_derived_panels.py` |
| Refinitiv query smoke | `python3 scripts/refinitiv_query_demo.py` |
| Faculty UI + API | `bash scripts/run_yzu_cluster.sh` |
| Query engine only | `bash scripts/run_research_query_engine.sh` |
| MCP for Composer | `bash scripts/run_research_data_mcp.sh` |

---

## 14. Known gaps (honest, lane-neutral)

1. **93 registry IDs** lack a `collection_partitions` mapping — mostly scrape/metadata catalog.
2. **Entity-level joins** (any event source ↔ market RIC) are thin — not unique to GDELT.
3. **Estimate revision history** covers 222 RICs — sparse against full PIT universes.
4. **Some instant panels** have stale `default_run_id` or path resolution via USB symlink — run coverage report `query_path_ok` column.
5. **Live connectors** (BigQuery, HF, DataCite) are not automatically mirrored as instant cards.
6. **Physical GDELT bulk** is large but not fully rolled into instant country CSV panels on all hosts.

---

## Related docs

| Doc | Role |
|-----|------|
| [`DESK_ACTIVATION.md`](DESK_ACTIVATION.md) | Operational backlog (profile-filtered priorities) |
| [`DESK_STATUS.md`](DESK_STATUS.md) | Faculty desk scope and commands |
| `drive/docs/status/generated/platform_progress.json` | Machine-readable progress + incomplete items |

---

*Maintainers: update inventory via audit scripts; do not add ranked recommendations here.*
