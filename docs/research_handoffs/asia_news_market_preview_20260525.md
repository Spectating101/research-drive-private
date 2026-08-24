# Asia News Shock x Market Panel Preview

Date: 2026-05-25

Status: starter memo from completed GDELT Asia windows through September 2025. This is a preview, not a final paper result or trading signal.

## Current Data Position

The news shock pipeline is now large enough to move from "dataset build" to first-pass research diagnostics.

Completed weekly bridge panel:

- Output root: `data_lake/research_panels/asia_news_market/asia_news_market_completed_through_202509_20260525/`
- Weekly country-news panel: 1,144 country-week rows.
- Primary news-market panel: 1,140 country-week rows.
- Full proxy news-market panel: 3,164 country-week/instrument rows.
- Countries: AUS, CHN, HKG, IDN, IND, JPN, KOR, MYS, PHL, SGP, THA, TWN, VNM.
- Date coverage: 2024-01-05 to 2025-10-03.
- Market proxies: 36 ETF/index/FX instruments from the local yfinance Asia layer.

Scoring summaries currently present account for:

- 16,686,233 scored news rows.
- 12,164,191 month-summed unique URLs.
- 23,903 strict `enrich_high_priority` URL candidates.
- 1,185,204 `keep_medium_priority` article-country rows.
- 2,308,331 `keep_context` article-country rows.

Known coverage caveats:

- 2024-03 has normalized/scored/daily panel locally, but enrichment is missing.
- 2025-04 has a scored file but is missing the daily/enrichment layer and is not part of the current weekly market bridge.
- October 2025 onward is still being collected.

## Core Research Claim

The strongest version of the project is not "news sentiment predicts markets." That framing is too generic and too easy to reject.

The stronger claim is:

> A country-specific news shock taxonomy captures investability risk states in Asian markets. The most robust first-pass signal is not return direction, but forward volatility and risk-regime formation.

That is a better academic and investment framing because it matches what the diagnostics currently show.

## First-Pass Empirical Preview

The current diagnostics use the primary country proxy for each market and test weekly news signals against forward 1-week, 2-week, 4-week returns and 4-week forward volatility.

Important warning: this is pooled and simple. It does not yet include country fixed effects, week fixed effects, out-of-sample testing, winsorization, or transaction costs. Treat it as signal triage.

### Strongest Result: Forward Volatility

The cleanest pattern is that news shock intensity predicts higher forward volatility.

Top Spearman correlations with 4-week forward volatility:

| Signal | Spearman | t-stat |
|---|---:|---:|
| Macro policy shock intensity | 0.196 | 6.74 |
| Political instability intensity | 0.193 | 6.62 |
| Trade/supply-chain shock intensity | 0.185 | 6.36 |
| Market-relevant news share | 0.176 | 6.04 |
| Broad-context news share | 0.166 | 5.67 |
| Financial-stress shock intensity | 0.156 | 5.34 |

Top-minus-bottom tercile spreads for 4-week forward volatility:

| Signal | Top-bottom spread | t-stat |
|---|---:|---:|
| Macro policy shock intensity | +0.00578 | 7.22 |
| Financial-stress shock intensity | +0.00495 | 6.36 |
| Trade/supply-chain shock intensity | +0.00520 | 5.59 |
| Market-relevant news share | +0.00528 | 5.33 |
| Political-instability shock intensity | +0.00322 | 4.76 |
| Broad-context news share | +0.00418 | 4.73 |

Interpretation:

This is the early useful finding. When the news environment becomes more macro-policy, financial-stress, trade, or political-shock dense, the market tends to enter a more volatile state over the next month.

This is directly useful for:

- risk budgeting,
- position sizing,
- country ETF timing,
- FX risk monitoring,
- volatility warning dashboards,
- academic asset-pricing tests around information arrival and uncertainty.

### Return Direction: Interesting, But Less Trustworthy Yet

There is also a positive pooled relationship between some shock/attention measures and future returns.

Top-minus-bottom tercile spreads for 4-week forward returns:

| Signal | Top-bottom spread | t-stat |
|---|---:|---:|
| Market-relevant news share | +0.01399 | 3.86 |
| Broad-context news share | +0.01350 | 3.63 |
| Macro policy shock intensity | +0.01154 | 3.44 |
| Political-instability shock intensity | +0.01044 | 3.33 |
| Financial-stress shock intensity | +0.01133 | 3.24 |
| Trade/supply-chain shock intensity | +0.01141 | 3.12 |

Interpretation:

This should not be read yet as "bad news is bullish." The likely explanations are:

- pooled country differences,
- rebound effects after stress,
- attention/liquidity effects,
- global risk-on weeks that create both news volume and returns,
- broad GDELT shock hints still mixing positive and negative narratives.

This return-side finding is worth testing, but the volatility-side result is more credible at this stage.

## Academic Angle

Best paper framing:

> News Shock Taxonomy and Investability Risk in Asian Markets

Better subtitle:

> Evidence from country-week GDELT news shocks, ETF/index returns, FX proxies, and forward volatility

Likely contribution:

1. Move beyond scalar tone/sentiment into typed shock families.
2. Show that macro-policy, financial-stress, trade, and political shock intensity forecast market risk states.
3. Compare whether taxonomy signals add information beyond raw tone, generic market relevance, VIX/global controls, and country momentum.
4. Use Asia as the setting because country-level institutional, trade, and FX channels are much cleaner than a US-only stock panel.

Initial hypotheses:

1. Typed shock intensity predicts forward volatility more reliably than forward returns.
2. Macro-policy and financial-stress shocks are broad market-risk signals.
3. Trade/supply-chain shocks are strongest for export-sensitive markets.
4. Political/governance shocks matter more for FX and country ETF drawdown risk than for same-week equity returns.
5. Raw tone is weaker than the taxonomy because tone alone cannot separate policy, trade, governance, financial, and disaster mechanisms.

## Investment Angle

The realistic investment use is not "buy the highest shock country."

The realistic use is:

1. A country risk overlay.
2. A volatility warning layer.
3. A position-sizing input.
4. A confirmation layer for existing country/sector theses.
5. A watchlist tool for when a country moves into a stress or reform narrative regime.

Near-term product idea:

- Country heatmap by week.
- Columns: macro policy, trade, financial stress, political instability, governance, geopolitical, health/disaster.
- Overlay: 1w/4w return, 4w realized/forward vol, FX move, local index/ETF.
- Output: "where risk is clustering" and "which countries have news stress but price has not moved yet."

The most promising trading use is volatility/risk control first, return alpha second.

## Immediate Next Tests

1. Rebuild after October and the remaining 2025-2026 windows finish.
2. Patch the 2024-03 enrichment gap and 2025-04 daily/enrichment gap.
3. Run country-demeaned and z-scored signals, not raw pooled levels.
4. Add country and week fixed effects.
5. Split by asset type: local index, US ETF, FX.
6. Run rolling out-of-sample tests.
7. Winsorize extreme news weeks and major global event weeks.
8. Add VIX, DXY, global equities, oil, gold, US rates, and China/Taiwan/Korea tech-cycle controls.
9. Separate positive reform/investment-flow signals from negative dysfunction/stress signals.
10. Build a first dashboard from the weekly panel.

## Gun-To-Head Assessment

Academic prospect: good enough to pursue.

Investment prospect: useful as a risk and attention engine first. Not enough yet to claim directional alpha.

Most defensible current result:

> Asia country-news shock intensity appears to forecast forward volatility/risk states. The signal is stronger and more coherent for volatility than for raw return direction.

That is already a meaningful research asset. The next job is to make it harder to fool ourselves.
