# Sharpe-Renaissance Repo Scope / Status Handoff

Generated: 2026-05-19 23:46 CST  
Workspace: `/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/Sharpe-Renaissance`

## Executive Summary

`Sharpe-Renaissance` is not one clean single-purpose repo. It is a combined financial research cockpit, data lake, professor deliverables workspace, trading/backtesting lab, and ongoing background data collection system.

The repo is locally about **46G**:

- `deliverables/`: **29G**
- `data_lake/`: **17G**
- `.venv/`: **705M**
- `.git/`: **286M**
- `backtests/`: **177M**
- `reports/`: **17M**
- `scripts/`: **3.1M**

The important mental model:

1. The repo is valuable mainly as a **data infrastructure + research cockpit**.
2. It is **not yet a reliable autonomous trading engine**.
3. Current high-value work is Drive-first data collection: crypto landscape history, daily crypto snapshots, Reddit/social, and planned news-shock headline/URL archives.
4. Professor OpenSea image deliverables are considered completed and sensitive; do not modify/delete them unless explicitly asked.
5. Large data should live in Google Drive where possible; local disk still has room but should not be treated as permanent staging for huge jobs.

## Immediate Live State

As of this handoff, active systemd user jobs:

```text
news-shock-headline-backfill.service      waiting
news-shock-url-enrichment.service         waiting
crypto-landscape-history-backfill.service running
portfolio-backup.service                  running
```

The current blocking job is:

```text
crypto-landscape-history-backfill.service
```

Status at last check:

- Current progress: **1,522 / 8,164 tasks**
- Remaining: **6,642 tasks**
- Recent rate: roughly **63-68 tasks/hour**
- Estimated finish: roughly **4.0-4.4 more days**, assuming no API/Drive stalls
- Latest processed item: `defillama_protocol/bifrost-dex`
- Disk: `/` has about **133G free**
- `/tmp`: about **5% used**
- Temporary staging folder: tiny; current workflow uploads each item to Drive immediately

Important command set:

```bash
systemctl --user list-jobs --all --no-pager
systemctl --user status crypto-landscape-history-backfill.service --no-pager
tail -n 50 logs/crypto_landscape_history_backfill/backfill.log
tail -n 20 logs/crypto_landscape_history_backfill/backfill_status.jsonl
df -h / /tmp
du -sh /tmp/sharpe_crypto_landscape_history 2>/dev/null || true
```

Queued behind the crypto backfill:

1. `news-shock-headline-backfill.service`
2. `news-shock-url-enrichment.service`

These wait intentionally so Drive/network/API load stays controlled.

Active timers of interest:

- `alpha-live.timer`
- `alpha-scorecard.timer`
- `reddit-ingest.timer`
- `portfolio-runtime-morning.timer`
- `portfolio-runtime-midday.timer`
- `crypto-landscape-drive-daily.timer`
- `portfolio-backup.timer`

## Google Drive Roots

Important Drive roots used by recent work:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape/historical_backfill
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/social_reddit
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-deliverables/
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-deliverables/opensea_professor_deliverables_20260514/
```

Known web links from previous work:

- Crypto landscape daily Drive folder: `https://drive.google.com/open?id=1iKg87QmwFYftAvyJzNPV0cpfTuSIA7xA`
- OpenSea/NFT landscape viewer sidecar: `https://drive.google.com/open?id=19HPb6SEvF2FfG-LkPuMZ-cUoOriP6NAO`

## Repo Architecture

High-level directories:

- `api/`: FastAPI-style market/intelligence API, vendor sources, auth/billing.
- `src/`: overlapping app/data/research/strategy modules; more current than parts of `api/`.
- `trading/`: backtesting, Bayesian/causal/regime logic, indicators, execution adapters.
- `high_perf/`: Rust/PyO3 modules for indicators, portfolio optimization, microstructure, parallel processing.
- `engine/`: LLM analyst/reporting layer.
- `agents/finrobot/`: finance-agent coursework/research agent material.
- `scripts/`: main operational layer; most real repo activity happens here.
- `systemd/`: user service/timer templates for daily/long-running jobs.
- `data_lake/`: local datasets and working data products.
- `deliverables/`: professor/OpenSea packages and generated visual/data sidecars.
- `backtests/outputs/`: many strategy experiments, scorecards, paper/live artifacts.
- `reports/`: generated research/audit reports.
- `docs/`: handoffs and higher-level project docs.

Dependency footprint from `pyproject.toml`:

- Python 3.11+
- `pandas`, `numpy`, `scipy`, `statsmodels`, `scikit-learn`
- `fastapi`, `uvicorn`
- `openai`, `pydantic`, `pyyaml`
- `networkx`, `pyarrow`
- `yfinance`
- `redis`, `asyncpg`, `stripe`, etc.
- Rust build via `maturin` for `high_perf/`

## Core Data Assets

### 1. CoinGecko Historical Archive

Path:

```text
data_lake/coingecko_archive/coingecko_full_active_2009.sqlite3
```

Size: about **1.9G SQLite**, folder about **3.9G**.

Current DB table counts:

- `coins`: **17,596**
- `coin_details`: **17,596**
- `coin_history`: **11,408,416**
- `coin_history_ranges`: **316,760**
- `coin_markets`: **29,749**
- `exchanges`: **1,028**
- `exchange_details`: **1,028**
- `exchange_volume_chart`: **339,623**
- `failures`: **2**
- `ingest_runs`: **5**

Known coverage from earlier checks:

- Price/history date range approximately **2013-04-28 to 2026-04-18 UTC**
- About **16,429 coins** have history
- Daily continuity is separately supported by existing CoinGecko updater/failover jobs and the newer crypto landscape snapshot flow.

Assessment:

This is one of the most valuable local datasets. Do not delete or mutate it casually. Backfill outputs should go to Drive, not pile up locally.

### 2. Crypto Landscape Drive-First Archive

Scripts:

```text
scripts/fetch_crypto_landscape_drive.py
scripts/run_crypto_landscape_drive_snapshot.sh
scripts/backfill_crypto_landscape_history_drive.py
scripts/run_crypto_landscape_history_backfill_drive.sh
```

Systemd:

```text
systemd/crypto-landscape-drive-daily.service
systemd/crypto-landscape-drive-daily.timer
systemd/crypto-landscape-history-backfill.service
```

Daily snapshot target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape
```

Historical backfill target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape/historical_backfill
```

Daily snapshots collect:

- DeFiLlama chains
- DeFiLlama protocols
- stablecoins
- yields
- fees
- DEXs
- open interest
- hacks
- CoinGecko global/categories/top markets/exchanges/trending
- raw gzip JSON
- normalized CSV
- SQLite snapshot
- manifest/run summary

Historical backfill selected:

- **7,514** DeFiLlama protocol histories
- **446** chains
- **199** stablecoin chains
- plus overview endpoints and local CoinGecko archive upload

Assessment:

This is the right direction: Drive-first, resumable, evidence-preserving, low local disk risk. The weakness is speed; it uploads per item, so the full backfill takes days. That is acceptable unless the goal changes to speed over safety.

### 3. Crypto Pipeline / News Context

Path:

```text
data_lake/crypto_pipeline
```

Size: about **12G**.

Notable subfolders:

- `exports/`: about **2.0G**
- `news_context/`: about **8.4G**
- `news_context/raw_archives/`: about **7.0G**, **253 files**

Raw archive sources include:

- GDELT
- GDELT DOC
- Hugging Face datasets
- Common Crawl
- GitHub activity
- Wikimedia pageviews
- SEC EDGAR
- DeFiLlama
- CoinMetrics community
- exchange announcements
- Cryptopanic live
- Internet Archive
- Kaggle/Mendeley/Figshare sources

Assessment:

This is messy but potentially high-value as a secondary crypto/news research layer. It still needs robust parser consolidation and quality checks; previous work identified parser gaps and sentiment normalization issues. Treat it as a raw archive + exploratory research dataset, not clean final panel yet.

### 4. OpenSea / NFT Professor Deliverables

Professor-facing consolidated Drive folder:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-deliverables/opensea_professor_deliverables_20260514/
```

Local docs:

```text
deliverables/opensea_professor_deliverables_20260514_README.md
deliverables/deliverables_opensea_README.md
deliverables/opensea_collection_enrichment_20260514/README_ENRICHMENT_COLLECTIONS.md
```

Drive consolidated package status from local README:

- **840 objects**
- **51.223 GiB**
- rclone checksum checks completed with **0 differences**
- 14 collection folders

Professor-facing simple folders:

- `opensea_zip_azuki`
- `opensea_zip_bayc`
- `opensea_zip_clone_x`
- `opensea_zip_cool_cats`
- `opensea_zip_cryptopunks`
- `opensea_zip_cryptoskulls`
- `opensea_zip_doodles`
- `opensea_zip_mayc`
- `opensea_zip_meebits`
- `opensea_zip_moonbirds`
- `opensea_zip_mooncats`
- `opensea_zip_pudgy_penguins`
- `opensea_zip_supducks`
- `opensea_zip_world_of_women`

Verified image coverage from local README:

| Collection | Images / rows | ID coverage |
|---|---:|---|
| Azuki | 10,000 | 0-9999 |
| BAYC | 10,000 | 0-9999 |
| CLONE X | 19,764 | 1-19764 |
| Cool Cats | 9,968 | 0-9967 |
| CryptoPunks | 10,000 images + rich dataset | 0-9999 |
| CryptoSkulls | 10,000 | 0-9999 |
| Doodles | 10,000 | 0-9999 |
| MAYC | 19,567 | sparse valid IDs 0-30006 |
| Meebits | 20,000 | 1-20000 |
| Moonbirds | 10,000 | 0-9999 |
| MoonCats | 20,880 | sparse valid IDs, min 0 max 25439 |
| Pudgy Penguins | 8,888 | 0-8887 |
| SupDucks | 10,001 | 0-10000 |
| World of Women | 10,000 | 0-9999 |

Important nuance:

- OpenSea **image deliverables** are considered complete and professor-ready.
- OpenSea **metadata sidecar/enrichment** is separate. The full metadata package exists locally, but not every collection has complete rich metadata. Some collections are manifest-only or image-source-audit-only.
- All 14 known NFT collections in this professor package are Ethereum collections.

Metadata package:

```text
deliverables/opensea_metadata_full_package_20260518
```

Size: about **373M**.

Metadata summary file:

```text
deliverables/opensea_metadata_full_package_20260518/collection_metadata_summary.csv
```

Notable metadata status:

- Most collections have complete token rows in the metadata index.
- MAYC metadata package has **19,567** token rows, matching image package contract-totalSupply coverage.
- SupDucks metadata package is not fully rich-metadata-complete in the later sidecar package; the image deliverable itself is still documented as complete.
- CryptoPunks trait rows are zero because classic CryptoPunks metadata structure is different.

Strict instruction:

Do not delete, reorganize, or “clean” OpenSea professor files unless explicitly asked. Past mistakes around deleting local/main folders made this area sensitive. If anything must be touched, verify Drive first and work from a manifest/checksum.

### 5. Prediction Market Research Dataset

Docs:

```text
handoff.md
handoff2.md
docs/PREDICTION_MARKET_RESEARCH_STARTER.md
```

Current local data:

```text
data_lake/prediction_markets
```

Size: about **26M**.

Manifest summary:

- Platform currently collected locally: **Kalshi**
- Contracts: **19,784**
- Categorized contracts:
  - `OTHER`: 19,289
  - `CRYPTO_PRICE`: 272
  - `MACRO_CPI`: 103
  - `POL_US`: 94
  - `POL_GEO`: 16
  - `MACRO_GDP`: 10
- Contracts with prices: **97**
- Price rows: **194**
- Price date range: **2026-02-21 to 2026-05-17**
- Current panel assets: `CL=F`, `GLD`, `^GSPC`

Known limitation:

- Polymarket public endpoints were blocked from the current network during earlier tests. Retry from another machine/network, such as `spectator`, when available.
- This dataset is pre-analysis. It is not yet enough to support paper claims.

Assessment:

The idea is strong as research infrastructure, but the current local panel is still too thin. The right next step is broader collection and better contract-to-asset mapping, not econometrics yet.

### 6. News Shock / Pattern Dataset

Docs:

```text
docs/research_handoffs/news_shock_taxonomy_pipeline.md
```

Scripts:

```text
scripts/news_shock_taxonomy/backfill_gdelt_doc_headlines_drive.py
scripts/news_shock_taxonomy/enrich_gdelt_doc_urls_drive.py
scripts/run_news_shock_headline_backfill_after_crypto.sh
scripts/run_news_shock_url_enrichment_after_headlines.sh
```

Systemd:

```text
systemd/news-shock-headline-backfill.service
systemd/news-shock-url-enrichment.service
```

Drive target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy/
```

Planned layers:

1. Raw headline/URL layer from GDELT DOC 2.0.
2. URL enrichment layer: canonical title, OG title, meta description, H1, source class, final URL, text excerpt, hashes/status.
3. AI classification layer: positive and negative country/company patterns.
4. Panel/index layer: country-month, entity-month, source coverage, pattern index.

Conceptual target:

This is not only “bad news” or governance dysfunction. The valuable dataset is a broad AI-classified pattern map:

- negative: apology/clarification loops, denial/allegation cycles, corruption probes, policy reversal, institutional conflict, protests, FX stress, sanctions, capital flight
- positive: reform delivery, credible policy coordination, investment inflow, infrastructure execution, export momentum, disinflation progress, rating improvement, supply-chain relocation

Assessment:

This is probably the highest-upside new dataset idea in the repo. The durable asset is the evidence-preserving raw headline/URL/article layer, not the final index alone. It can feed both academic papers and investment risk filters. It is still pre-data/queued; no classification results should be assumed yet.

### 7. Reddit / Social Signal Dataset

Docs:

```text
REDDIT_SIGNALS.md
```

Scripts:

```text
scripts/reddit_ingest_daily.py
scripts/reddit_fetch_listing_jsonl.py
scripts/reddit_fetch_comments_jsonl.py
scripts/reddit_daily_signals.py
scripts/reddit_data_health.py
scripts/reddit_research_loop.py
scripts/walkforward_reddit_overlay.py
scripts/sync_reddit_sentiment_drive.sh
```

Systemd:

```text
systemd/reddit-ingest.service
systemd/reddit-ingest.timer
```

Drive target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/social_reddit
```

Current local DB:

```text
data_lake/sentiment/reddit_ingest.sqlite
```

DB counts:

- `submissions`: **1,410**
- `comments`: **3,292**
- `runs`: **6**
- `threads`: **13**

Known panel:

```text
data_lake/sentiment/reddit_daily_signals.parquet
```

Earlier health:

- 676 panel rows
- 180 dates
- 58 tickers
- panel max date was 2026-01-22 before the new timer restarted collection
- latest smoke test pulled recent WSB posts but did not rebuild the panel

Assessment:

This is useful as a slow-building alternative-data layer, but current history is short and not statistically strong. Treat Reddit as a dataset and feature source, not a trade instruction feed. Also respect Reddit API/data terms for any serious/commercial usage.

### 8. SEC / Refinitiv / Traditional Market Data

SEC local data:

```text
data_lake/sec
```

Size: about **29M**.

Relevant scripts:

```text
scripts/sec_fetch_company_tickers.py
scripts/sec_fetch_submissions.py
scripts/sec_extract_filing_events.py
scripts/sec_to_intelligence.py
scripts/sec_event_alpha_backtest.py
scripts/sec_event_walkforward.py
scripts/sec_edge_cycle.py
```

Refinitiv source folder:

```text
From-refinitiv
```

Size: about **32M**.

Relevant scripts:

```text
scripts/refinitiv_feature_store.py
scripts/refinitiv_build_tidy_factor_panel.py
scripts/refinitiv_cross_sectional_stock_picker.py
scripts/refinitiv_stock_picker_sweep.py
scripts/refinitiv_api.py
```

Assessment:

These are useful but secondary compared to the crypto/news/social archives. The SEC layer is closer to event studies and alpha gates; Refinitiv is more traditional factor/fundamental infrastructure.

## Investment Research Engine Assessment

Existing audit:

```text
reports/investment_research_engine/latest.md
docs/investment_research_engine_roadmap.md
scripts/investment_research_engine_audit.py
```

Verdict from latest audit:

```text
research_cockpit
```

Meaning:

The repo is useful as an investment research cockpit and risk filter. It is **not yet** a trustworthy autonomous stock-picking engine.

Current paper/live signal:

- Status: **blocked**
- Strategy: `alpha_eventproxy_cfg12`
- Latest paper/live equity: about **$8,969** from $10,000
- CAGR since start: **-25.8%**
- Sharpe: **-0.71**
- Latest drawdown: **-4.1%**
- 30d return / alpha vs SPY: **-2.7% / -6.8%**

Strategy module summary from latest audit:

- `multi_asset_trend`: candidate; good as diversifier/risk-managed allocator, not a clean SPY-beater.
- `crypto_allocator`: candidate; positive holdout but short/volatile crypto regime sample.
- `sp500_equity_selector`: candidate; passes first sanity check, still needs robustness.
- `nasdaq_equity_selector`: blocked; holdout materially negative.
- `alpha_eventproxy_backtest`: research-only; strong backtest, weak live paper.
- `alpha_growth_controls`: research-only; strong backtest, weak live paper.

My assessment:

This repo can help prevent dumb decisions and structure discretionary investing, but it should not be allowed to directly decide real capital yet. The strongest near-term use is:

1. broad default portfolio core,
2. small tilt candidates from price/factor strength,
3. veto/confirmation from news-pattern quality,
4. live/paper scorecard as the promotion gate.

The “top 10” ranking idea by itself has already shown weak edge versus equal-weight in at least one recent test. That means the value is not raw ranking. The value is combining ranking, thesis, risk controls, and news-pattern evidence.

## Important Generated Docs

Useful docs to read:

```text
README.md
SIGNAL_READINESS.md
RESEARCH_LOOP_STATUS.md
REDDIT_SIGNALS.md
docs/investment_research_engine_roadmap.md
docs/research_handoffs/news_shock_taxonomy_pipeline.md
docs/PREDICTION_MARKET_RESEARCH_STARTER.md
deliverables/deliverables_opensea_README.md
deliverables/opensea_professor_deliverables_20260514_README.md
```

## Git Status / Dirty Worktree

The worktree is dirty. Do not assume untracked files are junk.

Known modified/untracked items at this handoff included:

```text
M REDDIT_SIGNALS.md
M agents/finrobot
M scripts/opensea_metadata_sidecar_collector.py
M scripts/run_reddit_ingest_daily.sh
?? Coin_Beg_Date (Ethereum).txt
?? backtests/inputs/
?? docs/investment_research_engine_roadmap.md
?? docs/research_handoffs/
?? scripts/backfill_crypto_landscape_history_drive.py
?? scripts/build_crypto_nft_landscape_viewer.py
?? scripts/build_opensea_graph_viewer.py
?? scripts/build_token_uri_cache.py
?? scripts/fetch_crypto_landscape_drive.py
?? scripts/investment_research_engine_audit.py
?? scripts/news_shock_taxonomy/
?? scripts/run_crypto_landscape_drive_snapshot.sh
?? scripts/run_crypto_landscape_history_backfill_drive.sh
?? scripts/run_news_shock_headline_backfill_after_crypto.sh
?? scripts/run_news_shock_url_enrichment_after_headlines.sh
?? scripts/sync_reddit_sentiment_drive.sh
?? systemd/crypto-landscape-drive-daily.service
?? systemd/crypto-landscape-drive-daily.timer
?? systemd/crypto-landscape-history-backfill.service
?? systemd/news-shock-headline-backfill.service
?? systemd/news-shock-url-enrichment.service
```

Interpretation:

- Some untracked files are intentional new infrastructure.
- Some existing modifications are from prior agents/users.
- Do not clean this aggressively.
- Before any commit, inspect file-level ownership and avoid reverting unrelated user work.

## Operational Rules For The Next Agent

1. Do not stop the active crypto historical backfill unless explicitly asked.
2. Do not delete data folders without a manifest and explicit confirmation.
3. Do not touch professor OpenSea image deliverables unless explicitly asked.
4. Treat Google Drive as the safer large-data destination.
5. For large jobs, prefer resumable Drive-first pipelines over local staging.
6. If asked to “clean up,” produce an audit list first. Never jump to `rm -rf`.
7. For investment conclusions, separate:
   - data availability,
   - backtest evidence,
   - live/paper evidence,
   - subjective thesis.
8. Do not claim a strategy is deployable unless it passes live/paper and robustness gates.

## Best Next Steps

If the next agent is continuing the current data work:

1. Monitor `crypto-landscape-history-backfill.service` until completion.
2. Confirm Drive output manifests/checks once it finishes.
3. Let `news-shock-headline-backfill.service` start automatically.
4. Watch for GDELT 429/rate-limit behavior.
5. Let URL enrichment run after headline backfill.
6. Only after raw/enriched evidence exists, design the AI classification layer.

If the next agent is continuing investment-engine work:

1. Run or inspect `scripts/investment_research_engine_audit.py`.
2. Treat `reports/investment_research_engine/latest.md` as the current sober baseline.
3. Do not optimize around one good backtest.
4. Build the news-pattern layer as a veto/quality feature, then test incremental value versus price-only models.

If the next agent is continuing professor/OpenSea work:

1. Read `deliverables/opensea_professor_deliverables_20260514_README.md`.
2. Verify Drive folder, not just local folders.
3. Do not delete duplicate-looking CLONE X tail split files unless rebuilding and revalidating token coverage.
4. Remember image deliverables and metadata sidecars are different deliverables.

## Bottom Line

This repo is big, uneven, and messy, but it has real accumulated value:

- a large CoinGecko archive,
- a running Drive-first crypto landscape backfill,
- professor-ready NFT image deliverables,
- a growing social/Reddit layer,
- a queued news-pattern dataset pipeline,
- a prediction-market research skeleton,
- many backtest and signal-generation tools.

The key judgment is that the **data infrastructure is more valuable than the current trading alpha**. The trading engine is useful as a research cockpit and capital-discipline tool; the real edge, if it emerges, will probably come from combining price/factor signals with the new news-pattern dataset, not from generic top-ranked stock picking.
