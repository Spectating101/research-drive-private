# Sharpe-Renaissance Dual-Track Edge Blueprint

Generated: 2026-05-20 CST  
Purpose: turn the repo's data assets into (1) academic papers and (2) investment decision modules.

## Core View

The edge is not the size of the dataset. The edge is using the dataset to identify state changes earlier or more cleanly than a plain price model.

The repo should be treated as a layered evidence engine:

1. Price/risk layer: returns, volatility, drawdown, trend, liquidity, market beta.
2. Activity/fundamental layer: real usage, TVL, fees, stablecoin flows, SEC filings, balance/fundamental signals.
3. News-pattern layer: structured signals about policy quality, institutional dysfunction, reform delivery, regulatory pressure, product execution, scandals, apologies, denials, and repeated clarification cycles.
4. Attention/crowding layer: Reddit/news volume/novelty and other public attention proxies.
5. Validation layer: out-of-sample tests, event studies, factor regressions, live/paper scorecards, costs, and turnover.

The same evidence can power papers and investing, but the threshold is different:

- A paper needs a clean research question, transparent measurement, and statistically defensible results.
- An investment module needs repeatable performance after realistic controls, costs, and live/paper validation.

## Track A: Academic Paper Program

### Paper A1: Real Activity and Crypto Asset Prices

Working title:

`Does Real On-Chain Activity Lead Crypto Asset Prices? Evidence from Protocol, Chain, and Stablecoin Flows`

Core question:

Do changes in real crypto activity predict future returns after controlling for momentum, volatility, size, liquidity, and category?

Why this is the strongest first paper:

- The price side already exists locally.
- The DeFiLlama historical activity backfill is running.
- The question is concrete and falsifiable.
- It avoids generic "sentiment predicts returns" claims.

Main datasets:

- `data_lake/crypto_pipeline/exports/price_panel_long.csv`
- `data_lake/crypto_pipeline/exports/mcap_panel_wide.csv`
- `data_lake/crypto_pipeline/exports/volume_panel_wide.csv`
- `data_lake/crypto_pipeline/context/quality_floor_predictive_factor_panel.csv`
- Drive historical backfill:
  - `raw/defillama/protocols/*.json.gz`
  - `normalized/defillama/protocol_tvl/*.csv.gz`
  - chain TVL, stablecoin, fees, DEX, and hacks outputs from daily snapshots/backfill

Main variables:

- protocol TVL growth: 7d, 30d, 90d
- chain TVL share growth
- fee/revenue growth
- DEX volume growth/share growth
- stablecoin supply growth by chain
- activity-price divergence
- liquidity and market-cap controls
- bucket/category fixed effects
- BTC/ETH market beta controls

Baseline specification:

```text
R_i,t+h = alpha + beta * ActivityShock_i,t
          + gamma * PriceControls_i,t
          + category FE + time FE + epsilon_i,t+h
```

Portfolio version:

- Rank assets monthly by activity-price divergence.
- Long top quintile, compare to equal-weight/momentum/category-neutral benchmark.
- Report turnover, drawdowns, cost sensitivity, and subperiod results.

Academic contribution:

- Shows whether crypto "fundamentals" exist in a measurable cross-section.
- Separates real usage from price momentum and narrative.

Investment translation:

- Candidate long/radar signal when activity rises before price.
- Avoid/fade signal when price rises while activity deteriorates.

Readiness:

- Medium now.
- High after DeFiLlama protocol/chain history finishes and mapping tables are built.

Immediate blocker:

- Need `defillama_slug -> coingecko_id` and `chain -> chain_token` mappings.

### Paper A2: Hype, Fundamentals, and Crowding in Crypto

Working title:

`Hype or Usage? Attention, Activity, and Future Crypto Returns`

Core question:

Do attention shocks predict returns only when confirmed by real activity?

Main datasets:

- canonical crypto news archive
- crypto news event/context files
- Reddit/social attention where relevant
- Wikipedia/pageviews from crypto news archives
- DeFiLlama activity panel
- CoinGecko returns

Signal groups:

- attention up, activity up
- attention up, activity down
- activity up, attention quiet
- price up, activity down
- news/event positive, activity confirming
- news/event positive, activity not confirming

Main hypothesis:

Attention without activity is crowding risk. Activity before attention is the better research/investment candidate.

Academic contribution:

- Moves beyond scalar sentiment.
- Tests interaction between narrative and real fundamentals.

Investment translation:

- Use attention as confirmation/crowding filter, not standalone buy signal.

Readiness:

- Medium.
- Needs stronger attention/news classification and source-quality controls.

### Paper A3: News-Pattern Investability Index

Working title:

`Reading Institutional Quality from News Patterns: A Country and Company Investability Index`

Core question:

Do repeated news patterns of dysfunction or improvement predict future country/company asset returns, volatility, or drawdowns?

This is the user's "Person A blunders, apologizes, clarifies, repeats" idea formalized into a research object.

Negative pattern taxonomy:

- apology/clarification cycle
- denial/allegation cycle
- corruption/graft
- policy reversal/confusion
- institutional conflict
- protest/unrest
- investigation/probe
- FX/bond stress
- sanctions/geopolitical stress

Positive pattern taxonomy:

- reform delivery
- credible policy coordination
- investment inflow
- infrastructure execution
- export/production boom
- disinflation progress
- rating/credit improvement
- supply-chain relocation
- regulatory clarity

Main datasets:

- queued Drive-first GDELT headline layer
- queued URL enrichment layer
- optional Oversight-inspired source/RSS extraction concepts
- yfinance country ETF/FX panels
- SEC/equity panels for company-level version

Panel outputs needed:

- `country_month_pattern_index.parquet`
- `entity_month_pattern_index.parquet`
- `source_domain_coverage.parquet`

Baseline specification:

```text
ForwardReturn_c,t+h = alpha_c + gamma_t
                    + beta * NewsPatternIndex_c,t
                    + controls(price momentum, volatility, global risk)
                    + epsilon_c,t+h
```

Risk version:

```text
ForwardDrawdown_c,t+h = alpha + beta * DeteriorationIndex_c,t + controls
```

Academic contribution:

- Turns messy qualitative governance/news signals into auditable monthly indices.
- Can be used for macro, finance, and emerging-market research.

Investment translation:

- Veto or downweight countries/stocks where structural deterioration is rising.
- Confirm concentration only when positive patterns and price strength agree.

Readiness:

- Low/medium.
- Scripts are written and queued; dataset is not populated yet.

### Paper A4: SEC Event Drift and Disclosure Timing

Working title:

`Disclosure Timing, Filing Events, and Post-Filing Return Drift`

Core question:

Which SEC filing events contain actionable information after accounting for filing timing, form type, pre-event momentum, and market regime?

Main datasets:

- `data_lake/sec/filing_events_nasdaq100.csv`
- yfinance/equity panels
- existing SEC event alpha backtest artifacts

Why it matters:

- Existing repo reports mark SEC-event alpha as one of the strongest trading-research leads.
- It is easier to validate than broad news/sentiment because event dates are precise.

Academic version:

- Event study by filing type and session.
- Drift by form type, firm, and pre-event trend.
- Compare next-day, 3d, 5d, 10d windows.

Investment version:

- Paper-traded event sleeve only.
- Must survive costs, turnover, and live scorecard.

Readiness:

- Medium/high.

### Paper A5: Prediction Market Probability Revisions and Asset Prices

Working title:

`When Do Prediction Market Prices Matter for Asset Prices?`

Current reality:

- catalogue is large: 19,784 contracts
- clean price panel is thin: 142-194 rows

Do not lead with this yet.

Use later if:

- Polymarket/Kalshi histories expand into hundreds or thousands of clean contract-days.
- contract-to-asset mapping can be manually audited.
- the design separates event-belief contracts from direct price contracts.

Readiness:

- Low now.

## Track B: Investment Engine Program

The investment system should not try to predict everything. It should create a disciplined decision stack.

Recommended portfolio doctrine:

1. Broad exposure is the default.
2. Tilts require cross-layer confirmation.
3. Deterioration signals can veto price momentum.
4. Crowding signals reduce confidence unless activity confirms.
5. No module gets capital without paper/live validation.

### Module B1: Crypto Activity-Price Divergence

Goal:

Find assets where real usage is improving before the price fully reflects it.

Long/radar condition:

- TVL/fees/stablecoin/DEX activity up over 30d/90d
- price flat/down or lagging the category
- liquidity acceptable
- market cap above minimum threshold
- no major supply/security/regulatory overhang
- category not dominated by one-off noise

Avoid/fade condition:

- price up sharply
- attention/news up
- TVL/fees/stablecoin activity flat/down
- supply unlock, regulatory, or security overhang present

Validation:

- top/bottom quintile forward returns
- 7d/30d/90d forward windows
- category-neutral spread
- cost/turnover sensitivity
- rolling subperiods

Capital status:

- research/radar now
- candidate only after backtest and paper/live evidence

### Module B2: Chain/Ecosystem Rotation

Goal:

Detect where crypto usage and liquidity are migrating.

Signals:

- chain stablecoin supply share change
- chain DEX volume share change
- chain TVL share change
- chain fee/revenue share change
- active protocols per chain, adjusted for TVL and volume

Investment use:

- overweight chain tokens/ecosystem baskets where usage share rises
- underweight chains losing share despite price strength

Important correction to the old NFT map idea:

Counting NFT projects by chain is not enough. The useful version measures capital, usage, fees, and liquidity migration.

### Module B3: News-Pattern Veto and Confirmation

Goal:

Use structured news as a quality filter, not generic sentiment.

Veto examples:

- repeated apology/clarification cycles
- policy reversals
- corruption probes
- denial/allegation spirals
- management/legal instability
- capital flight / FX stress

Confirmation examples:

- credible reform delivery
- product or infrastructure execution
- regulatory clarity
- investment inflows
- improving credit/rating language

Investment use:

- country ETF weights
- stock/sector tilts
- crypto regulatory and institutional-flow screening

Rule:

Do not concentrate when price momentum and news-pattern quality disagree.

### Module B4: SEC Event Sleeve

Goal:

Use precise SEC filing events as short-horizon alpha candidates.

Current evidence:

- historically promising in local artifacts
- live/paper engine is still blocked/negative overall

Use:

- standalone paper-traded sleeve
- strict risk cap
- event type/session filters
- no capital until live/paper evidence improves

### Module B5: Social Attention and Crowding Overlay

Goal:

Detect when public attention confirms real change or creates crowding risk.

Useful cases:

- novelty spike before price move
- attention spike with activity confirmation
- excessive attention without fundamentals as crowding warning

Bad use:

- "Reddit says buy"
- raw mention count as alpha

### Module B6: Prediction Market Overlay

Goal:

Use event-specific probability revisions where market-to-asset mapping is direct.

Good categories:

- macro policy to rates/bonds
- crypto regulation to BTC/ETH/SOL
- tariffs/trade to sectors/FX
- corporate event contracts to single stocks

Current status:

- not enough clean history yet
- keep collecting, but do not build core allocation around it now

## Unified Research-to-Investment Pipeline

Every signal should pass through the same promotion ladder:

### Stage 0: Dataset

Requirements:

- raw source preserved
- normalized table exists
- entity/date keys are clear
- missingness and source coverage measured

### Stage 1: Face Validity

Requirements:

- known events create visible spikes
- signs make economic sense
- source examples are auditable

### Stage 2: Research Test

Requirements:

- benchmark controls
- out-of-sample or chronological split
- category/country/time fixed effects when appropriate
- multiple horizons
- no lookahead

### Stage 3: Portfolio Test

Requirements:

- tradable universe
- liquidity filter
- transaction costs
- turnover
- drawdown
- simple benchmark comparison
- risk-matched benchmark comparison

### Stage 4: Paper Trading

Requirements:

- daily/weekly automated signal artifact
- immutable ledger
- kill switch
- live scorecard
- separate from backtest outputs

### Stage 5: Deployable Sleeve

Requirements:

- live evidence not negative
- size cap
- concentration cap
- written failure mode
- broad portfolio core remains untouched

## What To Build First

### First 48 Hours After Backfill Completes

1. Materialize DeFiLlama Drive files into local parquet/DuckDB:
   - protocol-day TVL
   - chain-day TVL
   - stablecoin chain-day supply
   - fees/revenue
   - DEX volume
   - hacks/security events
2. Build mapping tables:
   - DeFiLlama protocol slug to CoinGecko ID
   - protocol to chain
   - chain to chain token
   - CoinGecko ID to bucket/category
3. Run first factor tests:
   - TVL growth vs 30d/90d forward returns
   - fee growth vs forward returns
   - stablecoin share growth vs chain token returns
   - activity-price divergence vs momentum-only benchmark

### First News-Pattern Smoke Test

Start smaller than the full world:

- Countries: IDN, THA, MYS, PHL, VNM, SGP
- Period: one recent year first
- Patterns: apology/clarification, denial/allegation, corruption, policy reversal, reform delivery, investment inflow

Outputs:

- country-month pattern panel
- example evidence file
- face-validity chart around known events

### First Investment Dashboard Design

Do not make a flashy dashboard first. Start with a decision table:

Columns:

- asset/country
- price trend score
- activity/fundamental score
- news-pattern quality score
- attention/crowding score
- overhang flags
- final status: broad-core, radar, candidate, veto, paper-trade
- evidence links

## Expected Highest-ROI Results

Most likely to become useful:

1. Crypto activity-price divergence.
2. Chain/ecosystem rotation.
3. News-pattern veto for countries/stocks.
4. SEC event sleeve.

Most likely to remain research-only for now:

1. Prediction markets, until history improves.
2. Reddit/social, unless used as crowding/attention overlay.
3. NFT investment mapping, unless marketplace transaction/floor-price data is added.

## Honest Capital View

The repo can help steer capital, but not by producing one magic top-10 list.

The realistic edge is:

- avoid bad momentum
- identify real improvement before it is obvious
- size down structural deterioration
- find ecosystem migration early
- only concentrate when price, activity, and news agree

If those tests fail, the dataset is still academically and commercially useful. If they pass, the repo becomes a real investment cockpit with evidence-backed sleeves.

