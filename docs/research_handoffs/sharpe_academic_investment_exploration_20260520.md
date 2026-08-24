# Sharpe-Renaissance Academic + Investment Exploration

Generated: 2026-05-20 15:45 CST  
Workspace: `/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/Sharpe-Renaissance`

## Bottom Line

This repo is not yet a trustworthy autonomous investment engine. It is already useful as a research cockpit, data collection stack, and signal-validation harness.

The highest-value direction is not "AI stock picker says buy top 10." That part has weak live evidence. The stronger direction is:

1. Build durable data layers that most students/researchers do not have.
2. Turn those layers into interpretable factors.
3. Test whether they improve returns, risk, drawdowns, or country/company allocation after controlling for normal price momentum and volatility.

The two best current research assets are:

- Crypto market history plus activity fundamentals: CoinGecko + DeFiLlama + CoinMetrics-style/network/context data.
- News-pattern intelligence: GDELT/headline corpus + URL enrichment + LLM taxonomy for both negative and positive investability patterns.

## Current Collection Status

### Active Jobs

The full crypto landscape historical backfill is running through the new protocol-sharded service:

- `crypto-landscape-history-protocol-shards.service`
- 4 parallel protocol workers
- stage roots under `/tmp/sharpe_crypto_landscape_history_shard_*`
- Drive target: `gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/crypto_landscape/historical_backfill`

Latest local status check:

- shard 0: 435 status rows, 9 new ok, 425 skipped-present, 1 timeout error
- shard 1: 441 status rows, 18 new ok, 423 skipped-present
- shard 2: 447 status rows, 24 new ok, 423 skipped-present
- shard 3: 439 status rows, 20 new ok, 419 skipped-present
- known transient error: `sablier-legacy` read timeout
- latest Drive count observed: roughly 1,760 raw/normalized protocol files visible
- disk safe: `/` had about 131G free, `/tmp` about 14G free

The queue is intended to continue after the crypto backfill:

- `news-shock-headline-backfill.service`
- `news-shock-url-enrichment.service`

The news-shock Drive root is not populated yet in the latest Drive listing, which is expected because the crypto backfill is still ahead of it.

### Daily Snapshot Continuity

The installed active daily timer is:

- `crypto-landscape-drive-daily.timer`

It ran on 2026-05-20 and completed all 19 sources:

- DeFiLlama chains, protocols, historical chain TVL, stablecoins, yields, DEXs, fees, open interest, hacks
- CoinGecko global, global DeFi, categories, trending, markets, exchanges

The older `crypto-panel-failover.timer` and `crypto-panel-daily.timer` exist as repo templates but are not currently installed under `~/.config/systemd/user`. However, the exported wide price/mcap/volume panels do include 2026-05-20 rows, and the Drive-first landscape snapshot is active.

## Dataset Inventory

### CoinGecko Archive

`data_lake/coingecko_archive/coingecko_full_active_2009.sqlite3`

- about 1.9G
- `coin_history`: 11,408,416 rows
- 16,429 distinct coins with history
- date range: 2013-04-28 to 2026-04-18
- `coins`: 17,596
- `coin_details`: 17,596
- `coin_markets`: 29,749
- `exchanges`: 1,028
- `exchange_volume_chart`: 339,623

This is the long-tail historical archive. Best use: deep historical coverage, coin metadata, exchange metadata, and survival/backfill analysis.

### Crypto Research DB

`data_lake/crypto_pipeline/research_db.sqlite3`

- about 1.5G
- `coin_history`: 10,954,990 rows
- 16,873 distinct `cg_id`
- date range: 2020-01-01 to 2026-03-19
- `coin_profiles`: 18,070
- `coin_analytics`: 16,873
- `categories`: 678
- `exchange_profiles`: 996

This is the cleaner research database for 2020 onward.

### Exported Crypto Panels

Main files:

- `data_lake/crypto_pipeline/exports/price_panel_clean.csv`
  - 2,330 days, 1,062 assets
  - 2020-01-01 to 2026-05-20
- `data_lake/crypto_pipeline/exports/mcap_panel_wide.csv`
  - 2,303 days, 15,903 assets
  - 2020-01-01 to 2026-05-20
- `data_lake/crypto_pipeline/exports/volume_panel_wide.csv`
  - 2,330 days, 16,873 assets
  - 2020-01-01 to 2026-05-20
- `data_lake/crypto_pipeline/exports/price_panel_long.csv`
  - about 10.95M rows
  - columns: `cg_id`, `symbol`, `name`, `date`, `price_usd`, `market_cap_usd`, `volume_usd`
- `data_lake/crypto_pipeline/exports/category_analytics.csv`
  - 667 categories

These are immediately usable for cross-sectional crypto return studies.

### Crypto Factor / Regime Layers

`data_lake/crypto_pipeline/context/quality_floor_predictive_factor_panel.csv`

- 10,209 rows
- 37 columns
- bucket distribution:
  - meme/speculative: 4,191
  - DeFi: 1,615
  - AI/DePIN: 1,610
  - other: 822
  - smart-contract L1: 579
  - RWA: 568
  - stablecoin: 462

`data_lake/crypto_pipeline/context/mature_quality_predictive_factor_panel.csv`

- 6,336 rows
- more mature subset

`data_lake/crypto_pipeline/context/current_regime_full_universe_panel.csv`

- 10,209 rows
- 44 columns
- direct current-regime annotations are only clearly present for about 918 coins
- the rest are propagated/imputed and should be treated as weaker evidence

Interpretation: this layer is good for hypothesis generation and screening, but it needs refresh and validation before being treated as a live signal.

### Crypto News Archive

`data_lake/crypto_pipeline/news_context/research_dataset/canonical_news_events.csv`

- about 1.4G
- report says 985,614 rows after dedupe
- date range: 2010-01-11 to 2026-05-07
- source families:
  - HuggingFace: 704,536
  - Mendeley: 188,430
  - Kaggle: 57,788
  - GDELT: 22,110
  - Figshare: 12,750

Largest kept datasets:

- Coindesk crypto news 2020-2025: 229,170
- Mendeley crypto dataset: 188,430
- DeepSeek impact labels: 134,364
- Llama impact labels: 132,423
- xesutr crypto news augmented: 93,666
- StephanAkkerman financial crypto tweets: 57,876

Important note: `scripts/consolidate_news_archives.py` now has generic CSV/parquet/jsonl handlers, dataset-specific sentiment normalization, and a custom parser for malformed Gopher-Lab multi-line tweet CSV rows. This is the right direction, but the canonical dataset remains heterogeneous and needs source-quality flags before serious inference.

### Small Crypto News Event Study Layer

`data_lake/crypto_pipeline/news_context/news_events.csv`

- 196 rows
- 2025-05-08 to 2026-05-05
- only 7 coins covered
- tags include factor, direction, source quality, and forward returns

This is too small for strong conclusions. It is useful as a schema prototype only.

### Prediction Markets

`data_lake/prediction_markets/processed/contracts_categorized.parquet`

- 19,784 contracts
- mostly catalogue/metadata

`data_lake/prediction_markets/processed/panel_full.parquet`

- 194 rows
- 2026-02-21 to 2026-05-17

`data_lake/prediction_markets/processed/panel_filtered.parquet`

- 142 rows

Current status: promising concept, but the clean price-history panel is too thin right now. Continue only after better Polymarket/Kalshi history is available.

### Reddit / Social

`data_lake/sentiment/reddit_ingest.sqlite`

- 5,923 submissions
- 15,063 comments
- 7 runs
- 81 threads

`data_lake/sentiment/reddit_daily_signals.parquet`

- 1,489 ticker-day rows
- 85 tickers
- 2024-11-18 to 2026-05-19
- mostly equity/social attention, not crypto-specific yet

Current status: useful for attention/novelty overlays, but not enough by itself for capital allocation.

### SEC / Equity Event Layer

`data_lake/sec/filing_events_nasdaq100.csv`

- 12,932 filing events
- Nasdaq 100-ish universe
- starts 2006-10-05

Existing reports suggest SEC-event alpha is one of the strongest trading-research candidates, but it still needs careful live/paper validation.

### OpenSea / NFT Layer

Professor image deliverables are a separate completed assignment. The NFT metadata sidecars and viewers are useful as a dataset/teaching artifact, but the forward-looking investment edge is weaker than the crypto activity/news layers.

## Existing Research Engine Assessment

`reports/investment_research_engine/latest.md` was refreshed on 2026-05-20.

Current verdict:

- useful as a research cockpit and risk filter
- not a trustworthy autonomous stock-picking engine

Current paper/live signal:

- status: blocked
- strategy: `alpha_eventproxy_cfg12`
- latest equity: about $8,962
- CAGR since start: about -25.8%
- Sharpe: about -0.72
- 30d alpha vs SPY: about -6.8%

Candidate modules:

- multi-asset trend: candidate, useful diversifier/risk-managed allocator
- crypto allocator: candidate, but short/volatile sample
- SP500 selector: candidate, passes first sanity check
- Nasdaq selector: blocked in current artifact
- eventproxy/growth alpha backtests: research-only because live paper evidence is negative

Operating implication: use the engine for ranking, diagnostics, risk sizing, and vetoes. Do not use it as an automatic capital allocator.

## Best Academic Angles

### 1. Does Real Crypto Activity Lead Crypto Prices?

This is the strongest near-term paper/data project.

Core idea:

Use DeFiLlama activity variables and CoinGecko returns to test whether real crypto activity predicts future returns.

Data:

- CoinGecko price, market cap, volume
- DeFiLlama protocol TVL history
- DeFiLlama chain TVL history
- DeFiLlama fees/revenue
- DeFiLlama DEX volume
- stablecoin supply by chain
- hacks/security events
- category/bucket mappings from the crypto research DB

Candidate variables:

- 7d/30d/90d TVL growth
- 7d/30d/90d fee growth
- stablecoin supply growth by chain
- DEX volume share growth
- protocol TVL share within category
- activity-price divergence
- hack/security shock indicators
- category and chain fixed effects

Basic test:

```text
future_return_i,t+h =
    alpha + beta * activity_shock_i,t
    + controls(momentum, size, volatility, volume, market beta, category)
    + fixed effects
```

Why it is valuable:

- It is concrete.
- It uses a dataset you are already collecting.
- It is not just sentiment.
- It directly asks whether fundamentals exist in crypto.

Readiness:

- price side is ready
- daily snapshot side is active
- full historical protocol side is still backfilling
- next step is a protocol/chain-to-CoinGecko mapping table

### 2. Hype vs Fundamentals in Crypto

Core idea:

Separate attention/narrative from real activity.

Groups:

- price up, activity up
- price up, activity down
- attention up, activity up
- attention up, activity down
- activity up, no attention

Expected useful finding:

The best risk-adjusted candidates may be "activity up before attention," while the worst may be "attention/price up without activity."

Data:

- CoinGecko returns
- DeFiLlama TVL/fees/stablecoin activity
- crypto news archive
- current regime/narrative flags
- Wikipedia/pageviews and Reddit/attention where available

Readiness:

- medium now
- high after DeFiLlama history and news classification are normalized

### 3. Crypto Ecosystem Rotation

Core idea:

Study chains as ecosystems, not single tokens.

Examples:

- stablecoin supply migration to Base/Solana/Arbitrum/etc.
- DEX volume share migration
- fee/revenue share migration
- chain TVL share migration

Investment version:

Overweight chain tokens/ecosystem assets where real usage share is rising and price has not fully caught up.

Academic version:

Test whether ecosystem share changes predict chain-token returns and category rotation.

Readiness:

- high once chain/protocol history is fully assembled from Drive

### 4. News-Pattern Investability Index

Core idea:

Build a durable country/company/news pattern dataset. Not just negative dysfunction; include positive reform and execution patterns.

Negative patterns:

- apology/clarification cycles
- denial/allegation cycles
- corruption/graft
- policy reversals/confusion
- institutional conflict
- protest/unrest
- investigation/probe
- FX/bond stress

Positive patterns:

- credible reform delivery
- investment inflow
- infrastructure execution
- export/production boom
- policy coordination
- disinflation progress
- rating improvement
- supply-chain relocation

Data:

- GDELT DOC headline/URL backfill
- URL enrichment layer
- LLM classification layer
- country-month and entity-month indices

The sibling Oversight repo is relevant as an architecture reference:

- RSS/source registry
- async collectors
- content extraction
- claim/pattern concepts
- Indonesian named-role attribution heuristics

But it should not be used as a direct runtime dependency for this dataset because it is Redis/Docker/short-retention oriented. The correct implementation is what this repo is already doing: Drive-first, resumable, partitioned, and permanent.

Readiness:

- scripts are written
- services are queued behind crypto backfill
- Drive output has not started yet

### 5. SEC Event Alpha, But With Better Controls

Core idea:

The existing SEC event layer may be the best pure trading-research candidate.

Use:

- filing type
- filing session
- firm identity
- market regime
- volatility/liquidity
- pre/post filing returns

Need:

- robust holdout
- cost model
- paper trading
- benchmark/risk-matched comparison

Readiness:

- medium/high
- already has backtest artifacts, but must not be sold as deployable until live evidence improves

### 6. Prediction Market Asset Pricing

Core idea:

Prediction market probabilities are event-specific expectation measures.

Current blocker:

- clean time-series panel has only 142-194 rows
- catalogue is large but usable histories are thin

Continue if:

- Polymarket/Kalshi history expands into hundreds or thousands of clean contract-days
- asset mapping can be manually audited

Readiness:

- low now
- potentially high later from a different network/machine

## Best Investment Angles

### 1. Activity-Price Divergence

Best practical candidate.

Long/radar candidates:

- activity up
- price flat or weak
- market cap not too tiny
- liquidity acceptable
- no major security/regulatory/supply overhang

Avoid/fade candidates:

- price up
- attention up
- activity down or stagnant
- weak liquidity
- supply/regulatory/security overhang

Why this is credible:

It is not trying to predict everything. It is finding mismatch between real usage and market pricing.

### 2. Chain Rotation

Use rising chain share in:

- stablecoin supply
- DEX volume
- protocol fees
- TVL

Then map to:

- chain token
- major ecosystem protocols
- category baskets

This is a better version of the NFT/crypto "map" idea: not visualizing project counts, but measuring where capital and usage are migrating.

### 3. News-Pattern Veto

Use the news layer as a veto or risk overlay:

- do not buy price momentum into deterioration patterns
- size down countries/companies with recurring policy/institutional dysfunction
- require positive news-pattern confirmation before concentrated discretionary tilts

This is more believable than "news sentiment predicts returns directly."

### 4. SEC Event Sleeve

This is the most concrete non-crypto trading candidate.

Use as:

- paper-traded sleeve
- small research allocation only after live scorecard improves
- not a full portfolio replacement

### 5. Social Attention as a Risk Filter

Reddit/social data should not be used as "Reddit says buy."

Better use:

- crowding detector
- novelty spike detector
- liquidity/attention confirmation
- risk-off warning when attention is extreme but fundamentals are absent

## Non-Starters / Weak Areas

NFT forward alpha:

- useful dataset and professor deliverable
- weak as a main investment strategy in current market unless paired with marketplace sales/floor data

Raw top-10 stock ranking:

- useful radar
- not enough evidence to beat equal weight
- should not drive concentrated capital by itself

Prediction-market paper right now:

- conceptually good
- current clean history too thin

Generic ML return prediction:

- too crowded
- likely to overfit unless tied to unique dataset layers and strict out-of-sample testing

## Recommended Build Order

1. Let the crypto historical backfill finish.
2. Convert Drive DeFiLlama historical files into local research parquet/DuckDB tables:
   - protocol-day TVL
   - chain-day TVL
   - stablecoin chain-day supply
   - fees/revenue
   - DEX volume
3. Build mapping tables:
   - DeFiLlama protocol slug to CoinGecko ID/token
   - protocol to chain(s)
   - chain to chain token
   - category/bucket mapping
4. Run first activity-price tests:
   - 7d, 30d, 90d forward returns
   - controls for momentum, volatility, size, volume, BTC/ETH beta, category
   - top/bottom quintile portfolio spread
   - time splits, not just full-sample fit
5. Start news-shock headline and URL enrichment after crypto job finishes.
6. Build first country-month news-pattern index.
7. Test news-pattern value:
   - country ETF returns
   - FX returns
   - sovereign/risk proxy where available
   - incremental value over momentum/volatility/VIX/global risk
8. Add dashboard only after the evidence tables are stable.

## Immediate Experiments Worth Running Next

### Experiment A: Crypto Activity Factor Prototype

Build a small local sample using 100-300 high-TVL protocols already present on Drive.

Outputs:

- `processed/defillama_protocol_tvl_panel.parquet`
- `processed/crypto_activity_factor_panel.parquet`
- first backtest report

Questions:

- Does TVL/fee growth predict 30d token returns?
- Does activity-price divergence beat momentum alone?
- Are effects stronger for DeFi than memes/stablecoins?

### Experiment B: Chain Share Rotation

Outputs:

- chain-day TVL share
- chain-day stablecoin share
- chain-day DEX volume share
- chain token forward returns

Questions:

- Do rising ecosystem shares lead chain-token returns?
- Does stablecoin migration predict activity before price?

### Experiment C: News-Pattern Smoke Test

Start with 6 countries:

- IDN, THA, MYS, PHL, VNM, SGP

Classify one year first.

Questions:

- Does the index spike on known political/economic events?
- Are headlines deduping correctly?
- Does URL enrichment produce usable evidence text?

### Experiment D: Investment Cockpit Promotion Gate

Keep the current doctrine:

- broad/default allocation first
- price engine gives radar
- news/activity layers act as confirmation/veto
- no strategy gets capital without paper/live evidence

## Honest Assessment

This is worth building because the data asset is real and uncommon. Most people can run a momentum backtest. Fewer people have a stitched, evidence-preserving crypto activity/news/regime archive with enough infrastructure to keep updating it.

The investment edge is not guaranteed. The likely edge, if any, is narrow:

- activity before price
- deterioration vetoes
- ecosystem rotation
- event-specific signals

The academic edge is stronger than the immediate trading edge because the dataset itself can support defensible papers even if raw trading alpha is weak.

The right mindset:

- dataset first
- factors second
- out-of-sample tests third
- capital last

