# Refinitiv / LSEG Agent Mode Handoff

Date: 2026-05-20
Repo: `/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/Sharpe-Renaissance`

## Purpose

Use ChatGPT Agent Mode to help bring Refinitiv/LSEG access online, run a one-time historical backfill, and compile high-value market datasets for the Sharpe research/investment engine. This is not only for one paper. The goal is a durable research data warehouse usable for:

- Indonesian equity / IHSG / IDX research.
- Cross-country market signal research.
- Investment screening and backtesting.
- News/sentiment/event overlays later.
- Macro/crypto/equity risk mapping.

## Security Boundary

Do not paste university credentials, LSEG passwords, API secrets, or 2FA codes into chat.

The user should log in locally to LSEG Workspace/Eikon or the university portal. Agent Mode can assist after the session is already authenticated, but it should not store or transmit credentials.

Allowed local secret locations:

- `.env` in the repo root.
- `config/lseg-data.config.json`.
- OS keyring.
- Logged-in LSEG Workspace/Eikon desktop session.

Repo `.gitignore` already ignores `.env`, `.env.*`, local DBs, archives, and `data_lake/`.

## Current Repo State

### Refinitiv Python Environment

Use this environment for Refinitiv/LSEG work:

```bash
.venv-refinitiv/bin/python
```

Installed there:

- `lseg-data==2.1.1`
- `refinitiv-data==1.6.2`
- `eikon==1.1.18`
- `keyring`
- `python-dotenv`
- `pandas==2.3.3`
- `pyarrow==24.0.0`

Do not install legacy Refinitiv/Eikon packages into the repo's main `.venv` unless there is a strong reason. The main `.venv` is Python 3.13.5, and the legacy Refinitiv stack tried to compile older NumPy/SciPy from source there. Use `.venv-refinitiv` instead.

### Added Access Files

- `.env.example`
- `config/lseg-data.config.example.json`
- `scripts/refinitiv_access_probe.py`
- `docs/research_handoffs/refinitiv_access_setup_20260520.md`

Smoke test after Workspace/Eikon login and app key setup:

```bash
.venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --ric BBCA.JK --ric .JKSE
```

Legacy Eikon mode, only if needed:

```bash
.venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --mode eikon --ric BBCA.JK --ric .JKSE
```

### Existing Refinitiv Exports

Folder:

```text
From-refinitiv/
```

Important files:

- `RESCUED_Full_Market_Data_20251215.csv` - 31.9 MB, S&P 500 style wide market panel with price, volatility, implied vol/skew, short interest style fields.
- `DATA_2_Global_Crypto_Macro.csv` - global crypto/macro bridge panel.
- `PATCH_Global_2330_TW.csv` - TSMC Taiwan patch.
- `PATCH_Global_NVDA_O.csv` - NVDA patch.
- `PATCH_Global__TWII.csv` - Taiwan index patch.
- `PATCH_Global_BTC_PRICE_ONLY.csv` - BTC spot price-only patch.
- `PATCH_Global_XAU_PRICE_ONLY.csv` - gold spot price-only patch.
- `mass_hoard_sentiment.csv` - analyst/recommendation style fields.
- `mass_hoard_volatility.csv` - volatility snapshot fields.
- `manifest.md` - explains the older Refinitiv pull.

There are existing repo scripts for processing these:

- `scripts/refinitiv_feature_store.py`
- `scripts/refinitiv_build_tidy_factor_panel.py`
- `scripts/refinitiv_cross_sectional_stock_picker.py`
- `scripts/refinitiv_stock_picker_sweep.py`
- `scripts/refinitiv_api.py`

### Recovered IDX Legacy Dataset

Folder:

```text
data_lake/markets/idx_legacy_restore/
```

Files:

- `historical_data.db` - 197,013,504 bytes.
- `processed_tickers.txt` - 1,288 lines.
- `SHA256SUMS.txt`
- `README.md`

Verified SQLite coverage:

- `historical_data_daily`: 870,916 rows, 648 symbols, 2019-07-16 to 2025-02-07.
- `historical_data_hourly`: 1,463,065 rows, 645 symbols, 2022-07-18 09:00:00 to 2024-07-15 09:00:00.
- Examples present: `BBCA.JK`, `BBRI.JK`, `BMRI.JK`, `TLKM.JK`.
- Gap: `^JKSE` / IHSG index is not present in this recovered DB.

This means IDX equities are partly recovered, but the market index, sector indices, fundamentals, corporate actions, and metadata still need a proper Refinitiv-quality backfill.

## What Agent Mode Should Do First

1. Open LSEG Workspace/Eikon locally.
2. User logs in manually with university credentials and handles 2FA.
3. Agent searches inside Workspace/Eikon for App Key Generator / developer app key.
4. If app key is available, create/copy a desktop app key into local `.env`:

```bash
LSEG_APP_KEY=...
LSEG_SESSION_NAME=desktop.workspace
EIKON_APP_KEY=...
```

5. Run:

```bash
.venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --ric BBCA.JK --ric .JKSE
```

6. If the probe succeeds, proceed with scripted API backfill.
7. If no app key is available, use LSEG CodeBook or Excel add-in exports, then place raw exports under a versioned local folder for ingestion.

Do not rely on raw browser scraping of Refinitiv pages as the first method. Prefer official API, CodeBook, or Excel export. Browser automation is only acceptable as export assistance after the user is authenticated and the export is allowed by the institutional license.

## Highest-Value Data To Compile

### Priority 1: Indonesia / IDX Core

This is the strongest missing piece and highest personal research value.

Pull:

- Full IDX listed equity universe, including active and delisted names if entitled.
- Daily OHLCV, adjusted close, and total return if available.
- IHSG / JCI index: `.JKSE`.
- IDX sector indices, LQ45, Kompas100, IDX30, Sri-Kehati, and other major Indonesian benchmarks if available.
- Corporate actions: dividends, splits, rights issues, ticker changes, delisting dates.
- Metadata: RIC, ticker, ISIN, exchange, currency, country, company name, TRBC sector/industry, listing status.
- Shares outstanding, free float, market cap, turnover/value traded.
- Fundamentals: revenue, net income, EPS, book value, debt, ROE, ROA, margins, cash flow, dividends.
- Analyst estimates/recommendations/price targets if entitled.

Why this matters:

- Existing recovered IDX data has prices but not IHSG, not complete metadata, and not fundamentals/corporate actions.
- This enables proper Indonesian equity factor research and avoids relying only on Yahoo-style prices.

### Priority 2: Global Cross-Asset Market Backbone

Pull:

- Global equity indices: S&P 500, Nasdaq, Russell, Nikkei, TOPIX, Taiwan, Korea, China, Europe, ASEAN.
- Country ETFs/benchmarks used in the engine: SPY, QQQ, EEM, EIDO, EWY, EWT, EWM, INDA, EWZ, EZA, etc.
- FX: USDIDR, major USD crosses, ASEAN FX.
- Rates: US Treasury tenors, Indonesian sovereign yields if available, policy rate proxies.
- Commodities: Brent/WTI, gold, copper, coal, nickel, CPO/palm oil if available.

Why this matters:

- Gives the investment engine macro context.
- Allows country and sector regime models instead of isolated stock-picking.

### Priority 3: Derivatives / Risk Fields

Pull where entitlement allows:

- Implied volatility 30D/90D/360D.
- Put/call implied vol skew.
- Put/call ratio.
- Short interest / days to cover.
- Option-implied volatility surface fields.

Why this matters:

- Existing Refinitiv export suggests this is where the data has real edge over free sources.
- This supports crash-risk, crowding, and risk-regime research.

### Priority 4: Analyst / Estimates / Sentiment

Pull:

- Analyst recommendation mean.
- Number of analysts.
- Price target mean/high/low.
- EPS/revenue estimate revisions if available.
- Surprise history if available.

Why this matters:

- Useful for stock selection and testing whether the Sharpe engine has incremental value beyond analyst consensus.

### Priority 5: Supply Chain / Ownership / ESG

Pull:

- Supplier/customer relationships.
- TRBC sector graph.
- ESG score and subcomponents.
- Institutional ownership if available.

Why this matters:

- Enables graph-based contagion research and supply-chain shock mapping.
- Better as a research feature than as a direct trading signal.

## Output Structure To Use

Use versioned folders. Do not overwrite old data.

```text
data_lake/refinitiv_backfill/
  2026-05-20/
    raw/
      api/
      codebook/
      excel/
    processed/
      idx_prices_daily.parquet
      idx_indices_daily.parquet
      idx_metadata.parquet
      idx_corporate_actions.parquet
      idx_fundamentals_annual.parquet
      idx_fundamentals_quarterly.parquet
      global_cross_asset_daily.parquet
      derivatives_risk_panel.parquet
      analyst_estimates.parquet
    manifests/
      manifest.csv
      schema.md
      coverage_report.md
      SHA256SUMS.txt
```

After validation, sync to Google Drive under a new clearly named folder. Do not delete remote files to "clean up" unless explicitly instructed.

Suggested Drive target:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/refinitiv_backfill/
```

## Validation Requirements

For every export/backfill:

- Record source method: API, CodeBook, Excel, or manual export.
- Record export timestamp and user/session context, without credentials.
- Check row counts.
- Check unique key constraints: usually `ric + date`.
- Check min/max dates per RIC.
- Check missingness per field.
- Check duplicate dates per RIC.
- Check sample known instruments:
  - `BBCA.JK`
  - `BBRI.JK`
  - `BMRI.JK`
  - `TLKM.JK`
  - `.JKSE`
  - `2330.TW`
  - `NVDA.O`
  - `.SPX`
- Write `coverage_report.md` before treating data as usable.

## What To Avoid

- Do not paste credentials in chat.
- Do not commit `.env`, real config files, DBs, zips, or raw exports.
- Do not overwrite the recovered IDX DB.
- Do not delete any main data folders.
- Do not run uncontrolled UI scraping against Refinitiv.
- Do not trust a downloaded CSV until row counts, date ranges, and sample instruments are checked.
- Do not mix Refinitiv legacy packages into the main Python 3.13 `.venv`.

## If App Key/API Access Fails

Fallback path:

1. Use LSEG CodeBook inside Workspace.
2. Run/refine notebooks there to export CSV/Parquet.
3. Export to local folder:

```text
data_lake/refinitiv_backfill/2026-05-20/raw/codebook/
```

4. Ingest locally with pandas/pyarrow.
5. Build manifest and coverage report.

Second fallback:

1. Use Excel add-in.
2. Pull tables by universe and date range.
3. Save CSV/XLSX exports into:

```text
data_lake/refinitiv_backfill/2026-05-20/raw/excel/
```

4. Convert to parquet and validate.

## Immediate Agent Mode Checklist

- Confirm Workspace/Eikon is installed and opens.
- Let user log in manually.
- Find App Key Generator.
- Put app key in `.env`, not chat.
- Run `scripts/refinitiv_access_probe.py`.
- If probe works, start with IDX metadata and `.JKSE`.
- Then pull IDX daily prices and corporate actions.
- Then pull fundamentals.
- Then pull global macro/cross-asset backbone.
- Then pull options/risk/analyst fields where entitlement allows.
- Write manifests and validation reports after each batch.

## Best First Probe Instruments

Use these to verify entitlement and naming:

```text
BBCA.JK
BBRI.JK
BMRI.JK
TLKM.JK
.JKSE
2330.TW
NVDA.O
.SPX
.VIX
USDIDR=
XAU=
LCOc1
```

## Current Assessment

This backfill is worth doing. The repo already has free/cheap data pipelines and some old Refinitiv output, but the missing high-value layer is an institutional-quality historical backfill with metadata, corporate actions, fundamentals, analyst data, and risk fields.

The most valuable practical result is not "more prices." It is a normalized cross-asset research warehouse where price action, fundamentals, risk, analyst expectations, macro context, and news signals can be tested against each other.

For Agent Mode, the winning workflow is:

1. Authenticate locally and safely.
2. Establish API or export route.
3. Pull narrow probe samples.
4. Scale to versioned batches.
5. Validate aggressively.
6. Sync to Drive.
7. Leave a manifest good enough that another agent can resume without guessing.
