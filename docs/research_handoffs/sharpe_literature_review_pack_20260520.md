# Sharpe-Renaissance Literature Review Pack

Generated: 2026-05-20 CST  
Purpose: collect the research context needed to decide how this repo's datasets can support academic papers and investment modules.

## Executive Takeaway

The literature does **not** support a generic claim like "more data + AI = investment edge." Most broad versions of these ideas already exist:

- crypto market/size/momentum factors
- on-chain activity and network factors
- DeFi TVL/market-cap valuation ratios
- news-based uncertainty and geopolitical risk indices
- SEC filing drift and investor inattention
- social attention and sentiment effects
- machine-learning return prediction
- prediction-market calibration and macro expectation work

The opportunity is narrower but still real:

1. **Academic angle:** use this repo's unusually broad stitched dataset to test whether cross-chain DeFi fundamentals survive standard crypto factor controls.
2. **Investment angle:** build an evidence cockpit that flags disagreement between price, fundamentals/activity, news-pattern quality, and crowding.
3. **Dataset angle:** preserve raw evidence and normalized panels so negative results are still valuable.

## Literature Map

### 1. Crypto Asset Pricing Baseline

**What the literature says**

Crypto returns are not a blank slate. The core baseline is market beta, size, and momentum.

Key sources:

- Liu, Tsyvinski, and Wu, `Common Risk Factors in Cryptocurrency`  
  Source: https://www.nber.org/papers/w25882
- Broad empirical crypto asset-pricing studies increasingly treat crypto as a noisy factor zoo with size, momentum, reversal, liquidity, volatility, and network-style variables.  
  Source: https://arxiv.org/abs/2405.15716

**Implication for us**

Any crypto paper or investment module must control for:

- crypto market return
- size / market capitalization
- momentum
- liquidity / volume
- volatility
- category / sector

If a signal only works before those controls, it is probably not publishable and not investable.

**How to use our dataset**

Use CoinGecko price, market cap, and volume panels as the base factor-control layer:

- `price_panel_long.csv`
- `mcap_panel_wide.csv`
- `volume_panel_wide.csv`
- `quality_floor_predictive_factor_panel.csv`

### 2. On-Chain Activity and Network Fundamentals

**What the literature says**

On-chain and network variables can matter, but the signal is uneven and depends heavily on measurement.

Key sources:

- Bhambhwani, Delikouras, and Korniotis, `Blockchain Characteristics and Cryptocurrency Returns`: network size and computing power help explain expected cryptocurrency returns.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4474844_code2116659.pdf?abstractid=3342842
- `Bitcoin returns and transaction activity`: uses Bitcoin transactions and unique addresses as microstructure/activity proxies.  
  Source: https://www.sciencedirect.com/science/article/pii/S0165176518301125
- `On-Chain Factors and Cryptocurrency Asset Pricing: Evidence from Ethereum-Based Tokens`: builds many Ethereum on-chain factors but finds only limited robust survival after tests.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/6670521.pdf?abstractid=6670521&mirid=1
- `Does what happens on-chain stays on-chain?`: transaction intensity and exchange-related activity can affect token prices and valuation.  
  Source: https://repositorio.comillas.edu/jspui/retrieve/735173/1-s2.0-S0261560625001433-main.pdf

**Implication for us**

The claim cannot be "on-chain activity matters." That is known. The sharper claim is:

> Which activity variables still matter after standard crypto factor controls, and where do they fail?

**How to use our dataset**

Use DeFiLlama and CoinGecko to compare:

- protocol TVL growth
- protocol fee/revenue growth
- stablecoin supply growth
- DEX volume/share growth
- chain-level activity share
- activity-price divergence

### 3. DeFi Valuation, TVL, Fees, and Revenue

**What the literature says**

TVL is widely used but flawed. DeFi valuation should use more than locked value.

Key sources:

- Soiman and Mourey, `Pricing DeFi tokens with the Fama-French 3 Factor Model`: TVL-to-market ratio as a DeFi value analogue, but traditional factor models explain DeFi weakly.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4801588_code3774969.pdf?abstractid=4762616&mirid=1
- `What drives DeFi market returns?`: DeFi returns relate to crypto market, network variables, and TVL-to-market ratio.  
  Source: https://www.sciencedirect.com/science/article/pii/S1042443123000549
- `Decentralized Finance Projects: A Study of Key Performance Indicators in Terms of DeFi Protocols' Valuations`: protocol revenue and total revenue have distinct economic meanings for token holders.  
  Source: https://www.mdpi.com/2227-7072/10/4/108
- `Piercing the Veil of TVL`: TVL double-counting and instability are serious measurement problems; TVR is proposed as a refinement.  
  Source: https://arxiv.org/abs/2404.11745
- Bank of Canada, `DeFi Lending: Returns, Leverage, and Liquidation Risk`: transaction-level DeFi lending evidence; revenue and liquidation dynamics are concentrated.  
  Source: https://www.bankofcanada.ca/2026/04/staff-analytical-paper-2026-13/

**Implication for us**

Do not make TVL the hero variable. The better paper tests a bundle:

- TVL growth
- fee growth
- protocol revenue
- token-holder revenue where available
- stablecoin liquidity
- DEX usage
- liquidation/hack risk

And it should ask whether TVL is noisy compared to fee/revenue/flow measures.

**How to use our dataset**

The DeFiLlama backfill is valuable because it includes more than TVL:

- protocol TVL histories
- fees overview
- DEX overview
- stablecoins
- chain-level data
- hacks

This is the best dataset for a defensible academic contribution.

### 4. Investor Attention, Social Data, and Crowding

**What the literature says**

Investor attention often predicts short-term returns, volatility, and trading volume, but attention can also mean crowding and reversal risk.

Key sources:

- Da, Engelberg, and Gao's Google Search Volume Index line of work is the core attention baseline.  
  Related source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4721787_code1239503.pdf?abstractid=3398287&mirid=1
- `Google search and cross-section of cryptocurrency returns and trading activities`: abnormal Google search volume is followed by higher returns, volatility, and trading volume in crypto.  
  Source: https://www.sciencedirect.com/science/article/pii/S2214635024001060
- `Investor attention in cryptocurrency markets`: Google search volume is used as a retail attention proxy in crypto.  
  Source: https://www.sciencedirect.com/science/article/pii/S105752192100288X
- `Investor attention and cryptocurrency: Evidence from the Bitcoin market`: investor attention helps predict Bitcoin return/volatility in nonlinear settings.  
  Source: https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0246331
- `The social signal`: common components of social sentiment and attention can have different return predictions; attention can predict negative next-day returns while sentiment predicts positive returns.  
  Source: https://www.sciencedirect.com/science/article/pii/S0304405X2400093X
- `Sentiment, social media and meme stock return predictability`: Reddit/Bloomberg/Twitter/news sentiment have horizon-dependent effects for meme stocks.  
  Source: https://www.sciencedirect.com/org/science/article/pii/S1940597926000049

**Implication for us**

Social data should not be a standalone buy signal.

Better uses:

- crowding warning
- novelty/attention discovery
- confirmation when real activity also improves
- reversal-risk flag when attention spikes without fundamentals

**How to use our dataset**

Use:

- `reddit_daily_signals.parquet`
- crypto news volume
- Wikipedia/pageviews in raw archives
- canonical crypto news archive

Best interaction:

```text
attention shock x activity shock
```

Not:

```text
mentions -> buy
```

### 5. News, Uncertainty, Political Risk, and Text Indices

**What the literature says**

News-based indices are well established. EPU and GPR are benchmark indices, not novelty by themselves.

Key sources:

- Baker, Bloom, and Davis, `Measuring Economic Policy Uncertainty`: newspaper-based EPU index.  
  Source: https://academic.oup.com/qje/article-pdf/131/4/1593/30636769/qjw024.pdf
- Caldara and Iacoviello, `Measuring Geopolitical Risk`: geopolitical risk measured from newspaper article frequency.  
  Source: https://www.matteoiacoviello.com/gpr.htm
- `The Asset-Pricing Implications of Government Economic Policy Uncertainty`: EPU forecasts excess market returns.  
  Source: https://pubsonline.informs.org/doi/abs/10.1287/mnsc.2014.2044
- `The power of print`: text-based uncertainty shocks affect economic activity, volatility, and market returns.  
  Source: https://www.sciencedirect.com/science/article/abs/pii/S1059056015000246
- CEPR, `Identifying Monetary Policy Shocks in Newspapers using GPT`: LLMs are already being used for newspaper shock classification.  
  Source: https://cepr.org/index.php/publications/dp21390
- `Geopolitics, Geoeconomics and Risk: A Machine Learning Approach`: daily country news/risk indicators can improve market forecasting.  
  Source: https://arxiv.org/abs/2510.12416

**Implication for us**

The news-shock project must not be generic sentiment or generic uncertainty.

The distinctive taxonomy should be:

- institutional dysfunction patterns
- repeated apology/clarification cycles
- denial/allegation cycles
- corruption/probe recurrence
- policy reversal/confusion
- reform delivery
- investment inflow
- regulatory clarity
- execution credibility

**How to use our dataset**

Use GDELT + URL enrichment as an evidence-preserving corpus. Start with ASEAN and build a country-month panel.

This is more defensible as an "investability behavior index" than as another EPU clone.

### 6. SEC Filings, Disclosure Drift, and Investor Inattention

**What the literature says**

SEC filings contain information that investors may underreact to, especially in text and timing.

Key sources:

- NBER digest, `Are Investors Inattentive to SEC-Mandated Corporate Reports?`: textual changes in 10-Q/10-K filings are associated with abnormal returns.  
  Source: https://www.nber.org/digest/nov18/are-investors-inattentive-sec-mandated-corporate-reports
- `Event Day 0? After-Hours Earnings Announcements`: event timing matters for measuring abnormal returns correctly.  
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=747004
- `Investor distraction and multi-dimensional financial narrative`: narrative complexity in 10-K MD&A affects longer-horizon prices.  
  Source: https://link.springer.com/article/10.1007/s11142-026-09950-7
- `Disclosure Drift as a Predictive Signal for Equity Returns`: recent disclosure-drift work reports abnormal returns from changes across SEC filings.  
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6444659

**Implication for us**

SEC filings are not an academic novelty by themselves, but they can be a practical trading-research module.

What may be useful locally:

- strict event timing
- form/session filtering
- event-driven sleeve
- paper-trade scorecard
- later: textual disclosure drift

**How to use our dataset**

Use:

- `data_lake/sec/filing_events_nasdaq100.csv`
- `scripts/sec_event_alpha_backtest.py`
- live/paper scorecard infrastructure

### 7. Prediction Markets

**What the literature says**

Prediction markets are becoming academically credible as real-time expectation measures, but calibration and liquidity vary by domain.

Key sources:

- Wolfers and Zitzewitz, `Prediction Markets`: classic overview.  
  Source: https://www.aeaweb.org/articles?id=10.1257%2F0895330041371321
- Federal Reserve FEDS paper, `Kalshi and the Rise of Prediction Markets`: Kalshi macro markets as real-time macro expectations.  
  Source: https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf
- `Do Prediction Markets Forecast Cryptocurrency Volatility?`: Kalshi macro probability changes forecast crypto realized volatility channels.  
  Source: https://arxiv.org/abs/2604.01431
- `Decomposing Crowd Wisdom`: calibration differs by domain, timing, and participant mix.  
  Source: https://arxiv.org/abs/2602.19520

**Implication for us**

Good concept, but not first priority because local usable panel is thin.

Prediction market prices are best used as:

- event-specific expectations
- macro/regulatory overlay
- hypothesis source

Not yet:

- core investment signal
- flagship paper

### 8. Machine Learning, Factor Zoo, and Overfitting Discipline

**What the literature says**

ML can improve return prediction, but finance is noisy and overfitting is the default failure mode.

Key sources:

- Gu, Kelly, and Xiu, `Empirical Asset Pricing via Machine Learning`: ML can improve risk-premium measurement; nonlinear interactions help, and dominant signals include momentum, liquidity, and volatility.  
  Source: https://www.nber.org/papers/w25398
- Harvey, Liu, and Zhu, `. . . and the Cross-Section of Expected Returns`: factor zoo and higher t-stat standards for new factors.  
  Source: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
- Bailey and Lopez de Prado, `The Deflated Sharpe Ratio`: adjusts for selection bias, backtest overfitting, and non-normality.  
  Source: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

**Implication for us**

The investment engine must be skeptical by design.

Minimum rules:

- chronological split
- no lookahead
- simple benchmark
- risk-matched benchmark
- cost and turnover
- deflated Sharpe or trial-count awareness
- paper/live scorecard before capital

This repo already has some of the right ingredients, but the live/paper alpha scorecard is negative, so the current engine remains a cockpit, not an allocator.

## Revised Paper Ideas

### Paper 1: Cross-Chain DeFi Fundamentals and Token Returns

Most defensible first paper.

Contribution:

- Tests activity fundamentals beyond crypto market/size/momentum.
- Uses cross-chain protocol, fee, stablecoin, DEX, and hack data.
- Explicitly handles TVL's weaknesses by comparing it to fee/revenue/liquidity variables.

Dataset:

- CoinGecko returns, market cap, volume
- DeFiLlama historical backfill
- category/bucket labels

Tests:

- panel regressions
- Fama-MacBeth style cross-sectional tests if feasible
- portfolio sorts
- category-neutral long-short spreads
- out-of-sample monthly walk-forward

Kill condition:

- activity variables do not survive market/size/momentum/liquidity/category controls.

### Paper 2: Hype or Usage? Attention and Activity in Crypto Markets

Contribution:

- Tests whether attention is useful only when confirmed by real usage.
- Turns social/news data into a crowding-vs-confirmation framework.

Dataset:

- crypto activity panel
- canonical crypto news archive
- Reddit/social and pageview attention

Tests:

- attention up/activity up vs attention up/activity down
- future return and future drawdown
- category/market controls

Kill condition:

- attention interaction adds no incremental value beyond momentum and volume.

### Paper 3: Structured News-Pattern Investability Index

Contribution:

- Moves beyond sentiment/EPU/GPR by classifying behavioral/institutional patterns.

Best first scope:

- ASEAN-6 country-month panel.

Tests:

- face-validity event spikes
- forward ETF/FX/drawdown prediction
- comparison to EPU/GPR/VIX where available

Kill condition:

- taxonomy collapses into generic negative sentiment or fails face validity.

### Paper 4: SEC Filing Timing and Event Drift

Contribution:

- Less novel academically, but practical and testable.

Use:

- research note or investment-method appendix.

Kill condition:

- event drift fails strict timing/cost/paper-trade validation.

### Paper 5: Prediction Market Asset Pricing

Not first.

Condition to revive:

- several hundred/thousand clean contract-days with audited mappings.

## Investment Interpretation

The investment system should not be a prediction oracle.

It should answer:

```text
Should this asset/country be core, radar, candidate, veto, or avoid?
```

### Useful Module 1: Activity-Price Divergence

Good signal:

- real activity improves
- price has not caught up
- liquidity is sufficient
- no major overhang

Bad signal:

- price and attention run ahead
- TVL/fees/stablecoin/DEX activity deteriorate
- unlock/security/regulatory overhang exists

### Useful Module 2: Ecosystem Rotation

Good signal:

- chain gains stablecoin share
- chain gains DEX volume share
- chain gains fees/revenue share
- chain token has not fully repriced

This is more useful than counting NFT projects.

### Useful Module 3: News-Pattern Veto

Good use:

- veto buys when price momentum conflicts with institutional deterioration
- reduce country/stock exposure when repeated dysfunction patterns rise

Bad use:

- generic sentiment score as direct buy/sell signal

### Useful Module 4: SEC Event Sleeve

Good use:

- small paper-traded event sleeve with strict timing

Bad use:

- treating historical backtest alone as capital-ready

### Useful Module 5: Social/Crowding Overlay

Good use:

- attention confirms real activity
- or warns of crowding when activity is absent

Bad use:

- raw Reddit mentions as buy list

## Practical Next Build

The most useful next dataset is:

`processed/crypto_activity_price_divergence_panel.parquet`

Required columns:

- date
- coingecko_id
- symbol
- category
- market_cap_usd
- volume_usd
- price_return_30d
- price_return_90d
- tvl_growth_30d
- fee_growth_30d
- stablecoin_chain_share_growth_30d
- dex_share_growth_30d
- activity_score
- attention_score
- activity_price_divergence_score
- overhang_flags
- forward_return_30d
- forward_return_90d

First result table:

- top vs bottom quintile forward returns
- category-neutral spread
- regression with market/size/momentum/liquidity controls
- turnover and cost sensitivity

If that table is dead, the investment edge is mostly dashboard/risk management. If it works, the repo has both a paper and a practical signal.

