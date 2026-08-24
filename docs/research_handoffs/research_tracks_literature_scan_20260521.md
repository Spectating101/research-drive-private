# Research Tracks Literature Scan

Date: 2026-05-21

Purpose: map the current Sharpe-Renaissance data inventory to research and
investment tracks that are actually testable.

## Current Data Base

Local data already supports pilots before the full GDELT backlog finishes:

- Asia markets: yfinance Asia panels, IDX restored SQLite history, TWSE official OpenAPI snapshot.
- Entity map: Asia entity/ticker master linking TWSE, yfinance, ETF holdings, and IDX.
- Macro controls: FRED, World Bank/WGI, EPU, WUI, GPR, VIX, French factors.
- Crypto: CoinGecko archive, DeFiLlama historical backfill, crypto news/context.
- News shocks: GDELT Asia monthly backlog running; January 2024 processed locally and archive/copy completed.
- Prediction markets: local prediction market collection exists, but this is secondary until panel quality is audited.

## Literature Anchors

### News, Sentiment, and Asset Prices

Core result: media tone can matter, but simple sentiment alone is usually weak,
noisy, and easy to overfit. The more defensible angle is topic-specific news
shocks and lead/lag response.

Key papers:

- Tetlock (2007), "Giving Content to Investor Sentiment": WSJ media pessimism predicts short-run downward market pressure and high volume, followed by reversion.
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=685145
- Manela and Moreira, "News Implied Volatility and Disaster Concerns": news text can be transformed into a forward-looking disaster concern proxy.
  Source: https://conference.nber.org/confer/2014/BEs14/Manela_Moreira.pdf
- BBVA/GDELT news-media sentiment work uses GDELT as a broad news source for market sentiment, especially relevant to emerging-market extension.
  Source: https://www.bbvaresearch.com/wp-content/uploads/2022/07/News-Media-Sentiments-from-Big-Data-with-author-info.pdf

Implication for us:

Do not pitch this as generic sentiment. Pitch it as Asia-specific, category-level
news shocks: political instability, macro policy, trade/supply chain, financial
stress, geopolitical risk, commodity/energy, health/disaster.

### Policy Uncertainty, Geopolitical Risk, and Country Risk

Core result: news-based uncertainty/risk measures are established, but existing
indices are usually aggregate, low-frequency, or narrow in taxonomy.

Key papers/data:

- Baker, Bloom, and Davis (2016), "Measuring Economic Policy Uncertainty": newspaper-count EPU predicts volatility, investment/employment declines, and macro weakness.
  Source: https://www.nber.org/papers/w21633
- Caldara and Iacoviello (2022), "Measuring Geopolitical Risk": GPR predicts lower investment/employment and downside risk.
  Source: https://www.aeaweb.org/articles?id=10.1257/aer.20191823
- Ahir, Bloom, and Furceri, World Uncertainty Index: quarterly cross-country uncertainty from Economist Intelligence Unit reports.
  Source: https://www.nber.org/papers/w29763.pdf
- Hassan et al. (2019), "Firm-Level Political Risk": firm-specific political-risk language in calls links to volatility, lower investment/hiring, and lobbying.
  Source: https://ideas.repec.org/p/nbr/nberwo/24029.html

Implication for us:

The paper angle is strongest if we beat scalar EPU/GPR/WUI by separating shocks
by type and country at daily/weekly/monthly frequency. The investment angle is
country-risk rotation and drawdown avoidance.

### Emerging Markets and Asia

Core result: emerging-market returns are more exposed to local information, global
risk, flows, FX, and political uncertainty than developed markets.

Key papers:

- Harvey (1994), "Predictable Risk and Returns in Emerging Markets": emerging market returns are more likely than developed market returns to be influenced by local information.
  Source: https://www.nber.org/papers/w4621
- Geopolitical-risk cross-section in emerging markets: high geopolitical uncertainty changes can produce nontrivial cross-sectional return effects, including possible overreaction/reversal.
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3728341
- US/global uncertainty spillovers affect emerging equity volatility.
  Source: https://link.springer.com/article/10.1007/s10479-021-04042-y

Implication for us:

Asia is not a cosmetic focus. It is a defensible identification environment:
local shocks, local currencies, ETF/index proxies, and varying institutions.

### Crypto and DeFi Fundamentals

Core result: crypto returns are not well explained by classic equity factors,
but momentum/attention/network activity can matter. TVL is useful but dangerous
because it mixes adoption with token-price revaluation and leverage/rehypothecation.

Key papers:

- Liu and Tsyvinski, "Risks and Returns of Cryptocurrency": crypto has weak exposure to traditional asset classes, with momentum/attention effects.
  Source: https://www.nber.org/system/files/working_papers/w24877/w24877.pdf
- Schar, "Decentralized Finance": foundational DeFi market structure overview.
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3571335
- Harvey, Ramachandran, and Santoro, "DeFi and the Future of Finance": institutional overview of DeFi primitives and market design.
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3711777
- Active addresses / network value can form a crypto value-type signal.
  Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3718684
- Recent TVL papers question whether TVL reliably predicts returns.
  Sources:
  https://arxiv.org/abs/2506.03287
  https://arxiv.org/abs/2404.11745

Implication for us:

Best crypto track is not "TVL up, buy token." Better tests:

- TVL growth adjusted for token price.
- fees/revenue growth versus market cap.
- category-level fundamentals versus token returns.
- DeFi fundamentals as regime filters rather than direct return predictors.

### Prediction Markets

Core result: prediction markets are credible probability aggregators in many
settings, but calibration, liquidity, contract wording, and platform differences
matter. This is promising but should be treated as a separate module.

Key papers:

- Snowberg, Wolfers, and Zitzewitz, "Prediction Markets for Economic Forecasting": overview and evidence on forecasting use.
  Source: https://www.nber.org/papers/w18222
- Wolfers and Zitzewitz, "Interpreting Prediction Market Prices as Probabilities": theory/conditions for using prices as probabilities.
  Source: https://users.nber.org/~jwolfers/papers/InterpretingPredictionMarketPrices.pdf
- Recent Kalshi/Polymarket crypto-volatility paper: macro prediction-market probability changes forecast crypto realized volatility.
  Source: https://arxiv.org/abs/2604.01431
- Recent prediction-market accuracy/earnings papers are emerging but need careful validation.
  Sources:
  https://papers.ssrn.com/sol3/Delivery.cfm/6617059.pdf?abstractid=6617059&mirid=1
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6477080

Implication for us:

Prediction markets are a good second paper/strategy module, but only after
contract mapping and liquidity filters are audited. Do not mix this into the
first Asia news-shock panel.

### Official Disclosures and Monthly Revenue

Core result: post-announcement drift and limited attention are well-studied.
Asian markets still have plausible frictions, especially around local-language,
monthly, and disclosure-timing effects.

Key references:

- PEAD in China: limited attention and market movement effects.
  Source: https://www.econjournals.org.tr/index.php/ijefi/article/view/10817
- PEAD in Korea: market sentiment trend and investor inertia.
  Source: https://www.mdpi.com/2071-1050/11/18/5137
- Taiwan-related PEAD and institutional abnormal trading work exists, but the monthly revenue layer is still a practical low-cost test.
  Source: https://ethesys.lis.nsysu.edu.tw/ETD-db/ETD-search-c/view_etd?URN=etd-0707119-195724

Implication for us:

TWSE official data gives a clean Taiwan pilot:

- monthly revenue surprise
- material information daily announcements
- valuation ratios
- dividend/ex-right schedule
- forward returns and volume

This is likely a practical investment signal lab, even if the academic novelty is weaker than the news-shock angle.

## Ranked Research Tracks

### Track 1: Asia News-Shock Asset Pricing

Question:
Do country-level news shocks predict forward ETF/index/FX returns or volatility?

Data:
GDELT Asia country-day shocks, yfinance ETF/index/FX, macro controls.

Best outcomes:
EWT, EWY, EIDO, THD, EWM, EWS, MCHI/FXI, country FX crosses, local indices.

Specification:

```text
ForwardReturn_{country,t+h} =
  alpha_country + gamma_week
  + beta_k ShockType_{country,t}^k
  + controls_t
  + error
```

Why it is strong:
This directly combines our newest data with a clear literature gap: high-frequency,
type-specific Asian news shocks instead of scalar uncertainty indices.

### Track 2: Governance Dysfunction / Political Friction Index

Question:
Do repeated governance, scandal, apology, policy-reversal, corruption, and
institutional-confusion stories predict capital-market weakness?

Data:
GDELT article categories, persons/organizations, country panels, ETF/FX/index returns.

Why it is interesting:
This is the user's original intuition. It is not just "bad sentiment"; it is a
repeated institutional-quality signal.

Risk:
Needs LLM/taxonomy refinement. Keyword-only version may be noisy.

### Track 3: Crypto Fundamentals vs Price

Question:
Do DeFi fundamentals lead token returns, or do they mostly follow token prices?

Data:
CoinGecko, DeFiLlama, protocol categories, TVL, volume, fees/revenue where present.

Tests:

- TVL/market cap
- fees/market cap
- revenue growth
- protocol activity shocks
- category rotation
- price-adjusted TVL growth

Why it is strong:
Data is structured and already deep. This may produce the cleanest investment
engine even if it is less novel academically.

### Track 4: TWSE Disclosure Signal Lab

Question:
Do TWSE monthly revenue/material-information/disclosure signals produce drift
or volume/volatility response in Taiwan names?

Data:
TWSE official OpenAPI, yfinance Taiwan equities, entity mapping.

Why it is useful:
Clean, local, directly tradable, and low friction. Academic novelty is moderate,
but investment usefulness is high.

### Track 5: Prediction-Market Macro/Crypto Shock Panel

Question:
Do prediction-market probability changes add incremental information for crypto
and macro-sensitive assets beyond futures/VIX/news?

Data:
Prediction market local collection, crypto prices, macro controls.

Why not first:
Contract mapping/liquidity/resolution quality must be audited first.

## First Things To Build

1. `panel_asia_country_week_news_market.parquet`
   - country-week shock intensities
   - ETF/index/FX forward returns
   - macro controls

2. `panel_crypto_protocol_week_fundamentals_returns.parquet`
   - protocol/category fundamentals
   - token returns where mapped
   - market beta controls

3. `panel_twse_monthly_revenue_returns.parquet`
   - monthly revenue surprise
   - stock forward returns
   - industry controls

## Honest Assessment

The best academic prospect is Track 1 plus Track 2:

```text
Asia news-shock taxonomy as a country-risk and asset-pricing signal.
```

The best investment prospect is Track 3 plus Track 4:

```text
crypto fundamentals and Taiwan disclosure drift as systematic signal labs.
```

The most important near-term task is not another scrape. It is panel construction.
Once the panels exist, dozens of papers/strategies become cheap to test.
