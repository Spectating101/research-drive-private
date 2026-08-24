# Dataset Collection Control

Date: 2026-05-21

This is the control note for turning the 5TB Google Drive into the long-term data archive for Sharpe-Renaissance.

## Operating Rule

Local disk is staging and processing. Google Drive is cold storage.

Use copy-only archive commands by default:

```text
rclone copy local_path gdrive:target_path
```

Avoid destructive remote operations for research data:

```text
rclone sync
```

Only use `sync` for explicitly disposable/mirrored folders where remote deletion is intended.

## Storage Layout

Primary Drive root:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/
```

Recommended subtrees:

```text
crypto_landscape/
news_shock_taxonomy/
official_disclosures/
official_macro_asia/
market_data/
entity_mapping/
social_reddit/
manifests/
```

Professor/archive deliverables remain separate:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-deliverables/
```

## Current Active Collection

### Storage Status

Latest checked:

```text
Google Drive total: 5 TiB
Google Drive used: 166.210 GiB
Google Drive free: 4.832 TiB
Google Drive trash: 42.823 GiB
Local root free: 123 GiB
```

Drive trash still contains old Sharpe-Renaissance paths. Do not purge trash
without a separate explicit instruction because emptying Drive trash is
permanent.

Trash audit:

```text
Sharpe-Renaissance-deliverables trashed: 40.973 GiB / 2,563 objects
Sharpe-Renaissance-data trashed: 0 B / 0 objects
Sharpe-Renaissance-data_lake trashed: 603.116 MiB / 501 objects
Sharpe-Renaissance-raw_archives trashed: 532.260 MiB / 2 objects
```

The largest trashed items are old deliverable package names, especially:

```text
professor_zip_folder_clone_x_250
professor_zip_folder_meebits_250
professor_zip_folder_azuki_250
professor_zip_folder_pudgy_penguins_250
coingecko_professor_ethereum_bundle
coingecko_professor_ethereum_extended_bundle
opensea_bayc_rich_dataset_20260512.zip
```

The current visible archive locations checked clean:

```text
Sharpe-Renaissance-data_lake/coingecko_archive: 3.818 GiB visible, 0 trashed objects
Sharpe-Renaissance-deliverables/deliverables-opensea: 51.936 GiB visible
```

An old active `rclone sync deliverables/` process was found and stopped on
2026-05-21. That sync could trash remote files that were absent from the
local `deliverables/` mirror. Use copy-only commands for archive/data
collection going forward.

Trash rescue action:

```text
script: scripts/rescue_gdrive_trash_copy_only.sh
log: logs/gdrive_rescue/trash_rescue_20260521.log
rescue folder: gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-trash-rescue-20260521
method: rclone copy --drive-trashed-only
behavior: copies trashed backup files into a visible rescue folder; does not purge or untrash in-place
```

Completed rescue verification:

```text
completed_at: 2026-05-20T18:57:03Z
rescued objects: 3,066
rescued size: 42.081 GiB / 45,184,438,917 bytes
rescued subtrees:
  - Sharpe-Renaissance-deliverables
  - Sharpe-Renaissance-data_lake
  - Sharpe-Renaissance-raw_archives
```

The noncritical news raw archive copy was stopped during rescue to reduce
Google Drive API pressure, then resumed after the rescue completed:

```text
resumed_at: 2026-05-21T07:06:24Z
script: scripts/sync_news_shock_taxonomy_drive.sh
log: logs/news_shock_taxonomy/drive_copy_resume_20260521.log
method: rclone copy
```

The old GDELT DOC auto-followup services are gated after the rescue audit.
They will exit without running unless explicitly launched with:

```text
NEWS_SHOCK_DOC_AUTO_ENABLE=1
```

Reason: the earlier GDELT DOC pilot hit 429 rate limits. Use the GKG bulk
pipeline as the safer default news collection route.

Queue note:

```text
gdelt_doc_headline_idn_usa_pilot enabled=false
```

Reason: this was the rate-limited DOC API route. Do not let the queue
restart it automatically.

Always-on backlog added on 2026-05-21:

```text
systemd unit: sharpe-data-backlog-20260521.service
launcher script: scripts/run_always_on_data_backlog_20260521.sh
window pipeline: scripts/run_news_shock_gkg_window_pipeline.sh
log: logs/data_backlog/systemd_backlog_20260521.log
queue id: gdelt_gkg_asia_monthly_backlog_2024_present
```

Backlog plan:

```text
1. finish any existing news raw Drive copy
2. refresh public macro/risk baseline
3. refresh TWSE OpenAPI snapshot
4. refresh Asia yfinance market panel
5. refresh Asia ETF-holdings sourced universe
6. rebuild Asia entity mapping
7. run monthly GDELT GKG Asia windows from 2024-01-01 through 2026-06-01
8. copy each completed monthly normalized/processed window to Drive
9. refresh market/control/entity layers again at the end
```

The monthly GDELT backlog uses `KEEP_RAW=0`, so old raw GKG zip files are
downloaded, parsed, then removed locally. The retained research asset is the
filtered/scored country-news panel plus URL-enrichment outputs. The existing
7-day raw pilot remains archived separately.

Archive speedup applied after the January 2024 window:

```text
script patched: scripts/sync_news_shock_taxonomy_drive.sh
behavior when INCLUDE_RAW=0: copy only the latest normalized GDELT run folder and latest processed run folder
rclone copy settings: --transfers 8 --checkers 16 --fast-list
reason: avoid rechecking/reuploading the full normalized/processed archive tree after every monthly window
```

Manual full-tree archive remains possible by running:

```bash
COPY_SCOPE=all INCLUDE_RAW=0 scripts/sync_news_shock_taxonomy_drive.sh
```

### Taiwan TWSE Official Market Layer

Chosen next build on 2026-05-21 because it is official, Asia-relevant,
credential-free, and directly useful for entity mapping.

Run id:

```text
20260521T071150Z
```

Local output:

```text
data_lake/official_disclosures/taiwan_twse/20260521T071150Z
```

Drive output:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/official_disclosures/taiwan_twse/runs/20260521T071150Z
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/official_disclosures/taiwan_twse/latest
```

Verified summary:

```text
32 / 32 TWSE OpenAPI endpoints ok
1,363 security-master rows
136 Drive objects
10.578 MiB on Drive
```

Key slices:

```text
company profiles: 1,088
daily all securities: 1,361
monthly revenue: 1,078
dividend distribution: 1,131
valuation ratios: 1,076
current-month TAIEX history rows: 13
TWSE news: 305
TWSE events: 46
regulator penalty cases: 20
ESG board/climate/committee rows: 1,041 each
```

Script:

```text
scripts/fetch_twse_openapi_taiwan_market_layer.py
```

Source catalog:

```text
https://openapi.twse.com.tw/v1/swagger.json
```

### Asia Entity Mapping Layer

This is the derived join layer for news/disclosure/market-data work. It does
not collect new vendor data. It links TWSE official securities, yfinance Asia
universes, ETF-holdings proxies, and the restored IDX SQLite database into one
entity master.

Run id:

```text
20260521T072629Z
```

Local output:

```text
data_lake/entity_mapping/asia/20260521T072629Z
```

Drive output:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/entity_mapping/asia/runs/20260521T072629Z
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/entity_mapping/asia/latest
```

Verified local summary:

```text
2,795 entity rows
2,304 instrument coverage rows
791 ETF-holdings entity links
```

Verified Drive summary:

```text
10 objects
2.566 MiB
```

Main country coverage:

```text
TWN 1,373
IDN   665
JPN   181
IND   169
THA   104
KOR    89
HKG    52
```

Inputs:

```text
TWSE official security master: 1,363 rows
yfinance Asia config rows: 1,014
yfinance coverage rows: 1,011
IDX restored DB coverage rows: 1,293
ETF holdings links: 791
```

Script:

```text
scripts/build_asia_entity_mapping_layer.py
```

Queue note:

```text
asia_entity_ticker_mapping_layer enabled=true
```

### Public Macro/Risk Baseline Refresh

Fresh run for the public baseline was completed locally on 2026-05-21:

```text
script: scripts/download_public_macro_market_baseline.py
log: logs/official_macro_asia/public_macro_market_baseline_20260521.log
local output: data_lake/public_macro_market_baseline/2026-05-21
```

The script fetched all 51 planned public files:

```text
Kenneth French factors
CBOE VIX
EPU
GPR
FRED macro/rates/FX/commodities
World Bank macro and WGI governance indicators
World Uncertainty Index files
```

Drive copy target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/official_macro_asia/public_macro_market_baseline
```

Verified Drive summary:

```text
111 objects
22.794 MiB
```

### Asia News/Market Research Panel Pilot

First usable bridge panel built on 2026-05-22 from the completed January 2024
GDELT Asia window and the latest Asia yfinance market run.

Scripts:

```text
scripts/build_asia_news_market_panel.py
scripts/analyze_asia_news_market_panel.py
```

Input news run:

```text
asia_gkg_window_20240101_20240201_20260521T074828Z
```

Input market run:

```text
data_lake/markets/yfinance_asia/asia_phl_proxy_patch_20260522
```

Local output:

```text
data_lake/research_panels/asia_news_market/asia_news_market_202401_pilot_20260522
```

Drive output:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/research_panels/asia_news_market/asia_news_market_202401_pilot_20260522
```

Verified Drive summary:

```text
13 objects
4.638 MiB
rclone check --one-way --size-only: 0 differences, 13 matching files
```

Market proxy patch Drive summary:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/market_data/yfinance_asia/asia_phl_proxy_patch_20260522
6 objects
24.992 MiB
rclone check --one-way --size-only: 0 differences, 6 matching files
```

Panel contents:

```text
country_week_news_panel: 65 rows, 13 countries, 2024-01-05 to 2024-02-02
market_country_week_panel: 18,765 rows, 36 country market proxies
asia_country_week_news_market_panel: 180 rows, all ETF/index/FX proxy joins
asia_country_week_news_market_primary_panel: 65 rows, 13 primary country proxies
diagnostics: coverage, signal correlations, tercile spreads
```

Coverage note:

```text
PHL coverage was patched with PSEI.PS, EPHE, and USDPHP=X.
The pilot sample is only five weeks; use it to validate the pipeline, not to
claim an investment edge.
```

### Asia News Shock GDELT GKG 7-Day Pilot

Run id:

```text
asia_gkg_7d_pilot_20260520T162450Z
```

Log:

```text
logs/news_shock_taxonomy/asia_gkg_7d_pilot_20260520T162450Z.pipeline.log
```

Latest checked progress:

```text
670 / 670 GDELT files
fetch phase complete
740,276 raw rows scanned
195,214 filtered rows kept
142,436 unique URLs
475 strict high-priority URLs selected for enrichment
206 / 475 high-priority URL enrichment records logged at latest check
```

Pipeline:

```text
fetch GDELT GKG -> score rows -> enrich strict high-priority URLs
```

After completion, archive with:

```bash
scripts/sync_news_shock_taxonomy_drive.sh
```

This script uses `rclone copy`, not `sync`.

An after-completion archive watcher is active:

```text
watcher PID: 2038294
watcher script: scripts/archive_news_shock_after_pid.sh
watcher log: logs/news_shock_taxonomy/asia_gkg_7d_pilot_20260520T162450Z.drive_copy_after_complete.log
```

### Crypto Landscape Historical Backfill

Completed on 2026-05-21:

```text
4 / 4 shards finished
7,532 protocols processed
5,833 ok
1,697 skipped
2 errors
finished_at: 2026-05-21 12:47:33 CST
```

Drive archive:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape/historical_backfill
```

Verified Drive summary:

```text
16,372 objects
2.645 GiB
```

## Existing Ammunition

### Strong / Already Useful

- Crypto market history and CoinGecko archive.
- Crypto news/sentiment/news-event archives.
- Asia yfinance stock/ETF/FX/commodity panels.
- IDX restored daily/hourly individual-stock database.
- Public macro/risk controls: FRED, World Bank, EPU/WUI/GPR, VIX, Kenneth French factors.
- OpenSea/NFT professor archive and metadata sidecars.
- Taiwan TWSE official OpenAPI snapshots and security master.
- Asia entity/ticker mapping layer linking TWSE, yfinance, ETF holdings, and IDX restored data.

### Promising / Early

- Asia GDELT news-shock dataset.
- Prediction market event/asset panel.
- Reddit/social sentiment.

### Blocked / Needs Access

- Refinitiv/LSEG full historical backfill.
- WRDS/CRSP/Compustat/CCM.
- Korea OpenDART full API pull until API key is available.

## Next Highest-Value Collections

### 1. Official Asia Disclosures

Purpose:

```text
company event timing -> ticker/entity mapping -> post-event drift/drawdown tests
```

Targets:

- Korea OpenDART disclosures.
- Taiwan TWSE/OpenAPI data.
- HKEX listed-company announcements.
- SGX listed-company announcements.
- IDX/OJK/BI disclosures and official publications where accessible.

### 2. Official Asia Macro / Financial Conditions

Purpose:

```text
country-level macro controls -> news shock robustness -> regime filters
```

Targets:

- ADB data.
- IMF DataMapper/SDMX.
- BIS credit/banking/liquidity statistics.
- More World Bank indicators.
- Central bank/statistics-agency series for IDN/TWN/KOR/JPN/ASEAN.

### 3. Corporate Actions / Fundamentals

Purpose:

```text
clean investable panel -> factor tests -> event-adjusted backtests
```

Targets:

- dividends, splits, rights issues
- earnings dates
- financial statement basics
- sector/industry classification
- shares outstanding/free float/market cap

### 4. Entity Mapping

Purpose:

```text
news/disclosure entity -> company/ticker/country/sector/security
```

This is the bridge layer that turns collected text into quantitative signals.

## Queue Status

The queue file is:

```text
config/data_collection_queue.json
```

Tasks that are safe/free but not yet implemented are cataloged there with `enabled=false`.

Only tasks with:

```json
"enabled": true,
"credential_required": false
```

are allowed to run automatically.

## Summer Research Direction

The practical edge path is:

```text
prices + macro controls + news shocks + official disclosures + entity mapping
```

Then test:

```text
price-only baseline
vs price + macro
vs price + news shock
vs price + news shock + official disclosures
```

The goal is not to assume alpha. The goal is to make it cheap to discover, reject, and monitor candidate edges.
