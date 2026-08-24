# Literature + Novelty Sanity Check

Generated: 2026-05-20 CST  
Purpose: stress-test the academic and investment ideas against existing literature and make the edge concrete.

## Honest Verdict

The broad paper titles are not novel enough by themselves.

Weak framing:

- "On-chain activity predicts crypto returns."
- "News sentiment predicts asset returns."
- "Prediction markets predict assets."
- "SEC filings contain alpha."

All of those are already active literatures.

The defensible version is narrower:

- cross-chain DeFi fundamentals, not generic on-chain metrics
- activity-price divergence, not raw TVL growth
- ecosystem migration, not NFT/project counts
- structured news-pattern taxonomy, not sentiment/EPU clone
- news/activity as veto and confirmation layers, not direct magic alpha
- strict out-of-sample investment translation, not just in-sample significance

## Existing Literature Touchpoints

### Crypto Factors and On-Chain Activity

Existing work already covers common crypto risk factors and on-chain metrics.

Important anchors:

- Liu, Tsyvinski, and Wu, `Common Risk Factors in Cryptocurrency`: market, size, and momentum capture major cross-sectional expected returns.  
  Source: https://www.nber.org/papers/w25882
- Bhambhwani, Delikouras, and Korniotis, `Blockchain Characteristics and Cryptocurrency Returns`: network size and computing power help explain expected crypto returns.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4474844_code2116659.pdf?abstractid=3342842
- `Bitcoin returns and transaction activity`: Bitcoin transaction count and unique addresses are used as activity proxies.  
  Source: https://www.sciencedirect.com/science/article/pii/S0165176518301125
- `On-Chain Factors and Cryptocurrency Asset Pricing: Evidence from Ethereum-Based Tokens`: recent paper using 27 Ethereum on-chain factors and benchmark factors; reports only limited factors survive robust tests.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/6670521.pdf?abstractid=6670521&mirid=1
- `Does what happens on-chain stays on-chain?`: token transaction activity and exchange-related flows affect market valuation.  
  Source: https://repositorio.comillas.edu/jspui/retrieve/735173/1-s2.0-S0261560625001433-main.pdf
- `Pricing DeFi tokens with the Fama-French 3 Factor Model`: proposes TVL-to-market as a DeFi analogue to book-to-market.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4801588_code3774969.pdf?abstractid=4762616&mirid=1
- `Magical Internet Money? On-Chain Cashflows and the Cross-Section of Cryptocurrency Returns`: DeFi/on-chain cashflow framing.  
  Source: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4540433_code2819446.pdf?abstractid=4540433&mirid=1
- `Piercing the Veil of TVL`: TVL can double-count and be unstable, so raw TVL is a flawed fundamental measure.  
  Source: https://arxiv.org/abs/2404.11745

Implication:

The generic A1 paper is not enough. It must be sharpened to cross-chain DeFi activity quality and ecosystem migration, with factor controls and TVL caveats.

### News, Uncertainty, and Asset Returns

Existing work already covers newspaper-based uncertainty and geopolitical risk indices.

Important anchors:

- Baker, Bloom, and Davis, `Measuring Economic Policy Uncertainty`: newspaper frequency-based EPU index.  
  Source: https://academic.oup.com/qje/article-pdf/131/4/1593/30636769/qjw024.pdf
- Caldara and Iacoviello, `Measuring Geopolitical Risk`: news-based geopolitical risk index.  
  Source: https://www.matteoiacoviello.com/gpr.htm
- `The Asset-Pricing Implications of Government Economic Policy Uncertainty`: EPU forecasts excess market returns.  
  Source: https://pubsonline.informs.org/doi/abs/10.1287/mnsc.2014.2044
- `The power of print`: text-based uncertainty shocks affect economic activity, volatility, and market returns.  
  Source: https://www.sciencedirect.com/science/article/abs/pii/S1059056015000246
- `Identifying Monetary Policy Shocks in Newspapers using GPT`: LLMs are now being used to classify policy shocks from newspapers.  
  Source: https://cepr.org/index.php/publications/dp21390
- `Geopolitics, Geoeconomics and Risk: A Machine Learning Approach`: recent daily country panel of news-based risk indicators with market forecasting tests.  
  Source: https://arxiv.org/abs/2510.12416

Implication:

The news-pattern paper cannot just be "LLM news index beats EPU." That is crowded. It becomes more interesting if it measures specific institutional behavior patterns:

- apology/clarification repetition
- denial/allegation cycles
- policy reversal/confusion
- corruption/probe recurrence
- reform delivery
- investment execution
- regulatory clarity

This is closer to an "investability behavior index" than a generic uncertainty index.

### SEC Filing Events

Existing work already studies disclosure text, filing changes, and delayed assimilation.

Important anchors:

- NBER digest on investor inattention to SEC-mandated corporate reports: textual changes in filings have abnormal return implications and EDGAR downloads matter.  
  Source: https://www.nber.org/digest/nov18/are-investors-inattentive-sec-mandated-corporate-reports
- `Event Day 0? After-Hours Earnings Announcements`: event timing matters for measuring abnormal returns and drift.  
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=747004
- `Investor distraction and multi-dimensional financial narrative`: narrative complexity in 10-K MD&A affects longer-horizon prices.  
  Source: https://link.springer.com/article/10.1007/s11142-026-09950-7
- `Disclosure Drift as a Predictive Signal for Equity Returns`: very recent disclosure-drift paper reports abnormal returns from changes across SEC filings.  
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6444659

Implication:

The SEC paper is not novel if it simply says filings matter. The useful version must exploit this repo's event-timing discipline, form/session filtering, and live/paper trading validation.

### Prediction Markets

Existing and emerging work already supports the idea that prediction market probabilities can be meaningful, but there are calibration/liquidity caveats.

Important anchors:

- Wolfers and Zitzewitz, `Prediction Markets`: classic overview of prediction-market contracts and market-design issues.  
  Source: https://www.aeaweb.org/articles?id=10.1257%2F0895330041371321
- Federal Reserve/FEDS paper on Kalshi macro markets: prediction markets as real-time macro expectations.  
  Source: https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf
- `Do Prediction Markets Forecast Cryptocurrency Volatility?`: Kalshi macro probability changes forecast crypto volatility channels.  
  Source: https://arxiv.org/abs/2604.01431
- `Decomposing Crowd Wisdom`: calibration differs by domain, timing, and participants across Kalshi/Polymarket.  
  Source: https://arxiv.org/abs/2602.19520

Implication:

Prediction markets are promising but not ready locally because the current clean panel is too thin. Use them later as an event-probability overlay, not the flagship paper today.

## Revised Academic Ranking

### Rank 1: Cross-Chain DeFi Fundamentals and Token Returns

Better title:

`Cross-Chain DeFi Fundamentals and Token Returns: Activity, Fees, Stablecoins, and Ecosystem Migration`

Why it can still work:

- Existing papers study crypto factors, Bitcoin/on-chain activity, Ethereum tokens, and DeFi valuation.
- Fewer papers combine broad cross-chain DeFiLlama protocol data, fees, DEX volume, stablecoin migration, hacks, and CoinGecko long-tail returns in one out-of-sample panel.
- The novelty is not "TVL predicts returns"; it is "which activity fundamentals survive after crypto factor controls and TVL double-counting concerns?"

Must include:

- market/size/momentum controls
- category and time fixed effects
- liquidity/volume filters
- TVL caveat and alternative variables like fees, revenue, stablecoin supply, and DEX share
- out-of-sample portfolio sorts

Novelty score: medium-high if implemented well.

### Rank 2: Activity-Price Divergence and Crypto Crowding

Better title:

`Hype or Usage? Activity-Price Divergence and Crowding in Crypto Markets`

Why it can work:

- Investor attention papers exist.
- Crypto on-chain papers exist.
- The edge is combining them to identify mismatch states:
  - attention up, activity down
  - activity up, attention quiet
  - price up, fees/TVL down

Novelty score: medium.

### Rank 3: Structured News-Pattern Investability Index

Better title:

`Beyond Uncertainty: Structured News Patterns and Country/Company Investability`

Why it can work:

- EPU/GPR are crowded.
- LLM news classification is becoming crowded.
- The potential novelty is behavioral pattern taxonomy: repeated apology/clarification, denial/allegation, policy reversal, reform delivery, execution credibility.

Best scope:

- ASEAN first, not global first.
- Country ETF/FX/sovereign-risk outcomes.
- Keep full article evidence for audit.

Novelty score: medium if taxonomy is distinctive; low if it becomes generic sentiment.

### Rank 4: SEC Event Sleeve / Filing Timing

Better title:

`Disclosure Timing and Event Drift: A Reproducible SEC Filing Strategy Test`

Why it can work:

- Not very novel academically.
- Potentially useful as a trading-research note because the repo already has an event engine.

Novelty score: low-medium academically, medium for practical investing.

### Rank 5: Prediction Market Asset Pricing

Why not first:

- Literature is moving fast.
- Local panel is too thin.

Novelty score: medium later, low now due to data readiness.

## What The Investment Engine Actually Does

The investment system should produce decisions, not essays.

### Output 1: Candidate / Veto Table

For each asset/country:

```text
asset
price_trend_score
activity_score
news_quality_score
attention_crowding_score
overhang_flags
liquidity_status
final_status
evidence_links
```

Final statuses:

- `core`: broad/default exposure only
- `radar`: worth watching
- `candidate`: passes enough layers for paper-trade
- `veto`: price looks good but evidence quality is bad
- `avoid`: structural risk or failed evidence

### Output 2: Concrete Examples

Crypto candidate:

```text
SOL ecosystem:
price trend: positive
stablecoin share: rising
DEX volume share: rising
fees: rising
news: product/regulatory constructive
crowding: moderate
decision: candidate/radar
```

Crypto veto:

```text
Small DeFi token:
price trend: strong
attention: spiking
TVL: falling
fees: flat
supply unlock: present
decision: veto/fade, not buy
```

Country ETF veto:

```text
Country ETF:
price trend: strong
FX stress: rising
news pattern: policy reversal + corruption + protests
decision: downweight despite momentum
```

Stock candidate:

```text
Semiconductor stock:
price trend: strong
filings: no negative disclosure drift
sector/country news: constructive capex/export cycle
crowding: not extreme
decision: candidate tilt
```

SEC event:

```text
Ticker files eligible 8-K/10-Q after close.
Prior momentum positive.
Form/session historically favorable.
Trade next eligible session in paper sleeve only.
```

### Output 3: Strategy Modules

Each module must answer a narrow question:

- `B1 activity_price_divergence`: Is real usage improving before price?
- `B2 ecosystem_rotation`: Is capital/usage migrating to this chain or sector?
- `B3 news_veto`: Is structural news quality bad enough to override price?
- `B4 sec_event_sleeve`: Does a filing event justify a small paper-trade?
- `B5 crowding_overlay`: Is the move becoming crowded without fundamentals?

### Output 4: Promotion Rules

No signal is "useful" until it passes:

1. Face validity.
2. No-lookahead research test.
3. Benchmark comparison.
4. Cost/turnover test.
5. Paper trading.

## The Actual Edge Claim

Defensible edge claim:

> We are not trying to forecast all returns. We are building an evidence engine that detects when price, activity, news quality, and attention disagree. That disagreement can prevent bad buys, surface underpriced real improvement, and size risk more intelligently.

This is realistic.

Overclaim to avoid:

> We built a superior AI stock picker.

That is not supported.

## Practical Next Step

The next implementation should not be another broad report.

Build this first:

`processed/crypto_activity_price_divergence_panel.parquet`

Required columns:

- `date`
- `coingecko_id`
- `symbol`
- `category`
- `price_return_30d`
- `price_return_90d`
- `market_cap_usd`
- `volume_usd`
- `tvl_growth_30d`
- `fee_growth_30d`
- `stablecoin_chain_share_growth_30d`
- `dex_share_growth_30d`
- `activity_score`
- `activity_price_divergence_score`
- `forward_return_30d`
- `forward_return_90d`

Then run:

- top/bottom quintile return spread
- category-neutral spread
- market/size/momentum regression
- simple walk-forward monthly portfolio

That one panel tells us whether the most important investment idea has teeth.

