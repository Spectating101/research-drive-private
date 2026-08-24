# Deep Research Asia Reports: Integration Assessment

Date: 2026-05-25

Scope: assessment of the eight pasted `deep-research-report*.md` files against the current Sharpe-Renaissance data stack.

This note does not externally fact-check the Deep Research citations. The pasted files use ChatGPT `turn...` citation handles that are not reusable from this repo. Treat the reports as thesis drafts until primary-source URLs are reattached.

## Files Reviewed

| File | Topic | Practical Role |
|---|---|---|
| `deep-research-report.md` | Indonesia | Domestic-bank / commodity / FX-sensitive satellite |
| `deep-research-report (1).md` | Vietnam | Satellite growth / China-plus-one / FTSE upgrade optionality |
| `deep-research-report (2).md` | Singapore | Defensive yield / banks / financial hub |
| `deep-research-report (3).md` | Singapore alternate version | Similar to file 2; merge/deduplicate later |
| `deep-research-report (4).md` | South Korea | Macro-to-ticker AI memory / export / Korea discount |
| `deep-research-report (5).md` | Japan | Developed Asia core / banks / trading houses / industrials / semicap |
| `deep-research-report (6).md` | Taiwan | AI hardware core / TSMC-centered concentration risk |
| `deep-research-report (7).md` | Regional Asia synthesis | Cross-country sleeve architecture |

## Main Finding

These reports work best as the **positive thesis and candidate-universe layer**.

The news-shock and market panel works best as the **risk-state, timing, and sizing layer**.

That division is important. The Deep Research reports answer:

> What countries, sectors, and tickers might be worth owning over a multi-year horizon?

The Sharpe data stack answers:

> Is the current information regime becoming risky enough to avoid, delay, hedge, or size down that thesis?

This avoids forcing the news-shock engine to become a magical stock picker. It becomes a risk officer and thesis monitor.

## How It Fits the Current Data

Current panel used for this assessment:

`data_lake/research_panels/asia_news_market/asia_news_market_completed_through_202509_20260525/`

Coverage:

- 13 Asian countries.
- 2024-01-05 to 2025-10-03.
- 1,140 country-week primary proxy rows.
- 36 market proxies across index, ETF, and FX instruments.

Best empirical preview:

- News-shock intensity is more useful for **forward volatility / risk-state prediction** than clean directional return prediction.
- Macro-policy, financial-stress, trade/supply-chain, political-instability, and market-relevant news intensity all correlate with higher 4-week forward volatility.

So the reports should be converted into a two-stage investment architecture:

```text
Deep Research thesis / valuation / sector map
    -> candidate country and ticker universe
Sharpe news-risk engine
    -> veto, size, hedge, or wait signal
Market/momentum layer
    -> entry and rebalancing discipline
```

## Country-by-Country Read

### Indonesia

Deep Research thesis:

- Not a clean growth buy.
- Domestic banks, FX sensitivity, commodity optionality.
- Key risks: rupiah weakness, oil/import pressure, fiscal-policy credibility, low-free-float governance.
- Suggested role: small controlled satellite, not core.

Sharpe panel read:

- This fits our data very well.
- Indonesia is exactly the kind of market where a news-risk veto is useful.
- Latest 4-week risk percentiles are elevated: market-relevant share 76%, financial stress 93%, macro policy 87%, trade 78%, political instability 81%, governance 86%, geopolitical/security 83%.

Integration:

- Indonesia should be a **wait / small-size / risk-gated** sleeve until the risk-state cools.
- Good research test: does elevated Indonesia financial/macro/governance news predict rupiah weakness, EIDO underperformance, or `^JKSE` drawdown risk?

### Vietnam

Deep Research thesis:

- Satellite growth sleeve, not core.
- China-plus-one, industrial parks/logistics, FDI, consumer/credit beta.
- FTSE upgrade optionality.
- Risks: access friction, benchmark concentration, property/credit sensitivity, export/tariff risk.

Sharpe panel read:

- Vietnam has distinct behavior and is not simply Taiwan/Korea tech beta.
- In the current panel, Vietnam has relatively high average forward volatility and high geopolitical/security and political-instability density, but lower market-relevant share than North Asia.
- Current latest 4-week risk state is moderate rather than extreme.

Integration:

- Vietnam is a **satellite growth option**, but signal quality depends on better local market data.
- Use `VNM` ETF for public proxy tests, but eventually add better local Vietnam index and ticker data if accessible.

### Singapore

Deep Research thesis:

- Defensive yield, banks, financial hub, market infrastructure, ASEAN capital-flow monetization.
- Complements Taiwan/Korea tech rather than replacing it.
- Core names: DBS, OCBC, UOB, SGX; satellites include Keppel, Singtel, ST Engineering, Sea.

Sharpe panel read:

- This also fits the data.
- Singapore has among the lowest observed weekly volatility in the panel and a relatively high market-relevant news share.
- Latest 4-week risk percentiles are moderate, not alarming.

Integration:

- Singapore works as the **defensive/quality ballast** in the Asia sleeve.
- The news engine should monitor MAS policy, bank credit-cost language, AML/enforcement events, regional capital-flow stress, and SGX/listing reform narratives.

### South Korea

Deep Research thesis:

- Clean macro-to-ticker market.
- AI memory, exports, won, and governance/value-up reform transmit quickly into listed equities.
- Concentration in Samsung and SK Hynix is both the opportunity and the risk.

Sharpe panel read:

- Works well with our architecture.
- Korea has high beta and currently elevated market/financial/trade/governance risk percentiles.
- The engine should not tell us "buy Korea" by itself; it should tell us when Korea's semiconductor thesis is occurring in a stress regime.

Integration:

- Candidate alpha comes from combining: semiconductor thesis + export/AI momentum + news-risk cooling/confirmation.
- Risk veto: foreign-flow stress, FX stress, memory-cycle reversal, trade/export-control shock, governance disappointment.

### Japan

Deep Research thesis:

- Developed Asia core.
- Banks, trading houses, selected exporters/industrial champions, insurers, selective semicap equipment.
- Risks: oil, weak yen, JGB-yield volatility, fiscal slippage, tariff/logistics pain.

Sharpe panel read:

- Japan is not low-volatility in the current primary-proxy panel, but latest macro-policy news percentile is low.
- This supports Japan as a structural allocation that still needs risk monitoring around rates, yen, energy, and export/tariff shocks.

Integration:

- Japan belongs in the "core thesis, risk-monitored" bucket.
- Best tests: BOJ/macro-policy shock intensity against `^N225`, yen crosses, banks, exporters, and semicap equipment proxies.

### Taiwan

Deep Research thesis:

- Cleanest AI hardware expression, but extremely concentrated.
- TSMC and semiconductor complex dominate the market.
- Main risks: AI-capex valuation, export controls, China/Taiwan geopolitical risk, foreign-flow sensitivity.

Sharpe panel read:

- Taiwan shows high average political/geopolitical shock density, but latest geopolitical percentile is low in the current 4-week sample.
- Latest financial-stress percentile is high, so current risk is more market/financial than geopolitical in the panel.

Integration:

- Taiwan is a high-conviction structural sleeve only if position size is disciplined.
- Use the news engine to avoid adding during financial-stress spikes, export-control shocks, or geopolitical escalation windows.

### Regional Synthesis

Deep Research thesis:

- East Asia = AI/export complex.
- Southeast Asia = banks, dividends, domestic demand, value, and policy/FX sensitivity.
- Singapore/Malaysia are cleaner defensive financials; Indonesia is cheap but stressed; Vietnam is reform/growth optionality.

Sharpe panel read:

- This is directionally consistent with the data.
- The strongest current empirical result is cross-country risk-state formation: news shocks forecast higher forward volatility.
- This makes the regional sleeve framework useful, but only if paired with a risk overlay.

## What To Build From This

### 1. Thesis Registry

Create a structured table:

```text
country_iso3
thesis_bucket
candidate_instruments
candidate_tickers
structural_positive_drivers
thesis_break_conditions
news_risk_categories_to_monitor
base_weight_range
hard_cap
```

This should be derived from the Deep Research reports.

### 2. Risk-Gated Allocation Engine

Use this rule shape:

```text
target_weight = base_thesis_weight * risk_multiplier * momentum_confirmation
```

Where:

- `base_thesis_weight` comes from Deep Research.
- `risk_multiplier` comes from Sharpe news shock percentiles.
- `momentum_confirmation` comes from price/market panel.

Example:

```text
Indonesia base target = 3%
if financial_stress percentile > 80% or macro_policy percentile > 80%:
    risk_multiplier = 0.25 to 0.50
else:
    risk_multiplier = 1.00
```

### 3. Dashboard

Country cards:

- thesis status,
- current return trend,
- current shock percentiles,
- active risk flags,
- suggested action: add / hold / reduce / avoid / research-only.

### 4. Research Paper Link

The reports provide economically meaningful mechanisms for the paper:

- Taiwan/Korea: AI/export/foreign-flow concentration.
- Japan: monetary normalization and governance reform.
- Singapore: defensive financial hub and market infrastructure.
- Indonesia: FX/policy/commodity risk.
- Vietnam: market-upgrade and China-plus-one.

The academic paper can test whether typed news-shock categories line up with these mechanisms.

## Immediate Action Items

1. Move or archive the root `deep-research-report*.md` files into a proper folder, likely `docs/research_handoffs/deep_research_asia/`.
2. Deduplicate the two Singapore reports.
3. Reattach real URLs or source exports because current `turn...` citations are not reusable.
4. Extract tickers and allocation ranges into a machine-readable CSV.
5. Build a thesis registry config from the reports.
6. Add a risk-gated allocation prototype using the current weekly panel.
7. Keep collecting GDELT windows; October 2025 onward is still in progress.

## Bottom Line

Yes, the Deep Research reports work with the Sharpe stack.

They should not replace the quantitative engine. They should sit above it as the human-readable thesis layer.

The strongest combined architecture is:

```text
Deep Research = what might be worth owning
Sharpe news/market panel = when it is dangerous to own it
Price/momentum/factor engine = how to enter, size, and rebalance
```

This finally gives the project a coherent path from narrative research to measurable investment process.
