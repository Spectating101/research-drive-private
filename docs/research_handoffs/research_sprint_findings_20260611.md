# Research Sprint Findings — Asia News-Shock Panels

**Date:** 2026-06-11  
**Scope:** First empirical pass on data available today (no waiting for Tier 3 full history or DataCite).  
**Artifacts:**
- `scripts/run_research_sprint_v1.py`
- `backtests/outputs/research_sprint_v1/20260611T100217Z/`
- `backtests/outputs/asia_news_market_modeling/fused_20260610_v2_trial/`

---

## Executive summary

We ran a full first pass across four panel layers. The headline is **not** “bad news → sell Asia.” The data supports a narrower, more defensible story:

1. **News taxonomy predicts risk (volatility) much better than direction.** Walk-forward ridge IC on 4-week forward vol has t-stat ≈ **20**. This aligns with Manela-Moreira / disaster-concern and EPU-style uncertainty literature — news moves fear and variance, not clean signed returns.

2. **Return predictability exists at 2–4 week horizons, but with the wrong sign for naïve avoidance.** Higher shock intensity weeks/countries are associated with **higher** subsequent returns in panel regressions and in composite-risk event splits. “Avoid scary headlines” **underperforms** equal-weight in backtests.

3. **Shock type matters.** Financial stress, trade/supply-chain, macro policy, and political instability show the strongest 4-week return links at country level. Governance/corruption is weaker at country-week level but shows a **firm-specific** pattern in the thin entity-residual panel.

4. **Cross-sectional signal is weak at ticker level when shocks are country-broadcast.** Within the same country-week, broadcast shock intensity does not rank tickers — as expected. The ticker edge (if any) should live in **entity-residual** news once full history lands.

**Best paper angle today:** *Categorical Asia-Pacific news shocks and forward risk/return dynamics — beyond scalar EPU/GPR.*  
**Best investment framing today:** **Vol targeting / risk budgeting overlay**, not directional country avoidance.

---

## Data used

| Panel | Run ID | Rows | Span | Role in sprint |
|---|---|---:|---|---|
| `cross_asset_fused_primary_panel` | `fused_20260610_v2` | 5,694 | 2018-01 → 2026-05, 13 countries | **Primary** country-week lab |
| `ticker_week_country_broadcast_panel` | `ticker_20260610` | 460,103 | same | Country shock → all tickers |
| `ticker_week_entity_residual_panel` | `ticker_20260610` | 6,199 | 2023-10 → 2025-05 | Firm-specific mention pilot |
| `country_week_crypto_news_panel` + `global_assets_week_panel` | fused v2 | 5,694 / 522 | weekly | Crypto spillover pilot |
| GDELT `sample_high_priority.csv` | processed windows | samples | 2018+ | Qualitative case URLs |

Shock categories tested: political instability, governance/corruption, financial stress, geopolitical security, macro policy, trade/supply chain, health, natural environment.

---

## Track 1 — Country-week fused panel (main result)

### A. Panel regressions (country fixed effects)

Dependent variables: `fwd_return_1w/2w/4w`, `fwd_vol_4w`.  
Regressor: z-scored `*_per_1k_rows` shock intensity.

**4-week forward returns (strongest return horizon):**

| Shock type | β (4w return) | t-stat |
|---|---:|---:|
| financial_stress | +0.0068 | **7.14** |
| trade_supply_chain | +0.0061 | **6.41** |
| political_instability | +0.0053 | **6.02** |
| macro_policy | +0.0057 | **5.65** |
| health | +0.0028 | 4.16 |
| governance_corruption | +0.0003 | 0.33 |

**4-week forward volatility:**

| Shock type | β (4w vol) | t-stat |
|---|---:|---:|
| health | +0.0030 | **17.67** |
| natural_environment | +0.0030 | **16.12** |
| geopolitical_security | −0.0017 | −8.03 |
| governance_corruption | −0.0009 | −4.56 |
| political_instability | −0.0008 | −3.71 |

**Interpretation:** Within-country variation in macro/financial/political shock intensity forecasts **higher** medium-horizon returns — inconsistent with a simple “uncertainty discount” story. Plausible mechanisms: attention/reversal (Tetlock), risk-on episodes bundled with policy news, or shock intensity proxying for **information arrival** rather than pure bad outcomes.

Vol results are mixed by category in FE regressions but **cross-sectional rank IC** (below) shows clearer risk effects.

### B. Cross-sectional rank IC (same week, across countries)

Average Spearman rank correlation between shock rank and outcome rank, week by week:

| Shock | Target | Mean rank IC | t-stat |
|---|---|---:|---:|
| political_instability | fwd_vol_4w | **+0.169** | **12.4** |
| macro_policy | fwd_vol_4w | +0.164 | 11.7 |
| geopolitical_security | fwd_vol_4w | +0.115 | 8.6 |
| governance_corruption | fwd_vol_4w | +0.101 | 7.3 |
| political_instability | fwd_return_4w | +0.049 | 3.3 |

**Interpretation:** In a given week, countries with more intense political/geo shocks tend to have **higher subsequent vol** — the intuitive risk-channel. Return rank IC is weaker but positive at 4w for political shocks.

### C. Composite risk event study

Top decile of summed z-scored shocks vs rest:

| Metric | Top decile | Rest | Diff |
|---|---:|---:|---:|
| fwd_vol_4w | 0.0247 | 0.0201 | **+0.0047** |
| fwd_return_4w | 0.0180 | 0.0035 | **+0.0145** |

High composite shock weeks → **more vol and higher 4w returns**. Again: risk overlay yes, naïve short no.

### D. Walk-forward ridge (multivariate)

From `fused_20260610_v2_trial`:

| Target | Weekly IC mean | IC t-stat |
|---|---:|---:|
| fwd_vol_4w | 0.312 | **19.8** |
| fwd_return_4w | 0.104 | **6.1** |
| fwd_return_2w | 0.066 | 3.7 |
| fwd_return_1w | 0.041 | 2.3 |

**Avoidance backtest (country equal-weight):** `high_risk_tercile` beats `low_risk_tercile` and `avoid_top3_risk` on 1w/2w/4w returns.  
**Prediction strategy:** `top_predicted` countries beat equal-weight on 1w (Sharpe 0.74 vs 0.61) — modest screening edge, not yet validated for live use.

### E. Country heterogeneity (avg 4w forward return)

Highest: **TWN** (+1.37%/week), **KOR** (+1.22%), **JPN** (+1.05%)  
Lowest: **PHL** (−0.23%), **THA** (−0.08%), **MYS** (~0%)

Political/governance shock **levels** are high across CHN/IND (news volume), but average returns are not monotonically lower — country institutions and market structure matter.

---

## Track 2 — Ticker broadcast panel (933 symbols)

- Pooled correlations of country-broadcast shocks with ticker returns are **tiny** (|ρ| < 0.03).
- **Within country-week demeaned** correlations are effectively **zero** — broadcast shocks do not rank tickers inside a country.

**Conclusion:** Country broadcast layer is for **macro/country allocation**, not stock picking. Stock-level work must use **entity-residual** or long panels.

---

## Track 3 — Entity-residual panel (pilot, thin history)

Coverage: Oct 2023 – May 2025, 565 symbols, 6,199 ticker-weeks with entity-specific mentions.

Top-decile entity mention weeks vs rest:

| Feature | Δ fwd_return_1w (hi − lo) | Δ fwd_vol_4w |
|---|---:|---:|
| governance_corruption (entity) | **+0.42%** | +0.20% |
| political_instability (entity) | +0.07% | +0.13% |
| financial_stress (entity) | +0.15% | −0.30% |

**Tentative read:** Firm-level governance/scandal **attention** may coincide with short-term positive drift (volume, retail attention, controversy premium) — **not** tested with significance adjustments yet. This is the user's “governance dysfunction” intuition, but it needs full history + firm FE before claiming an effect.

**Next:** Re-run on `ticker_20260611` when entity overlay completes (~Jun 12).

---

## Track 4 — Crypto spillover (pilot)

Asia-aggregated weekly crypto news days vs global BTC/ETH 1w forward return:

| Feature | BTC 1w fwd | ETH 1w fwd |
|---|---:|---:|
| crypto_news_days | ρ = −0.077 | ρ = −0.114 |

Weak negative — more Asia crypto news weeks slightly precede lower crypto returns. **Exploratory only**; needs crypto factor controls (Liu-Tsyvinski) and proper panel spec.

---

## Literature mapping

| Our finding | Literature anchor | Implication |
|---|---|---|
| Vol IC ≫ return IC | Manela-Moreira; Baker-Bloom-Davis EPU | Lead with **risk forecasting**, not alpha |
| Positive return coef on shocks | Tetlock pessimism + reversal; attention | Avoid “sell bad news” strategies |
| Type-specific coefficients | vs scalar GPR/EPU/WUI | Taxonomy is the contribution |
| Asia country panel | Harvey (1994) EM local info | Geographic focus is justified |
| Entity governance pilot | Hassan et al. firm political risk | Firm-level track after Tier 3 |
| Broadcast ≠ stock picker | — | Don’t overclaim ticker broadcast |

---

## Hypotheses status

| Hypothesis | Verdict (v1) |
|---|---|
| H1: Higher news shocks → lower next-month country returns | **Rejected** (opposite sign in FE and events) |
| H2: Higher shocks → higher forward vol | **Supported** (rank IC, composite risk, ridge vol IC) |
| H3: Shock **type** matters beyond aggregate tone | **Supported** |
| H4: Governance stories → firm underperformance | **Inconclusive** (pilot shows positive 1w drift) |
| H5: Country-broadcast shocks pick stocks | **Rejected** |
| H6: Asia crypto news predicts global crypto returns | **Weak negative** — needs more work |

---

## Qualitative examples (high-priority URLs)

Illustrative governance/policy co-occurrence articles from GDELT samples:

1. **IND 2019-09-19** — Election Commission observers (governance + political instability)  
   https://indiatoday.in/india/story/ec-appoints-110-irs-officers-as-expenditure-observers-for-maharash...

2. **IND 2023-02-18** — Market regulation explainer (governance + macro policy)  
   https://thehindu.com/business/markets/explained-how-is-the-stock-market-regulated-in-india/article66...

3. **CHN 2023-11-09** — Oil demand/market macro (trade + geopolitical + macro policy)  
   https://moneycontrol.com/news/business/markets/oil-slides-over-2-on-demand-worries-lowest-settlement-in-3-months-11701841.html

Use these for professor-facing “what the taxonomy captures” — not as proof of causality.

---

## Recommended next steps (research, not infra)

1. **Formal paper spec** — Track 1 with country + week FE, clustered SE, FDR across shock types, compare to downloaded EPU/GPR baselines already in `macro_vix_week_panel`.
2. **Vol overlay backtest** — Scale country/ETF exposure by predicted `fwd_vol_4w` (not sign forecast).
3. **Re-test entity governance** on `ticker_20260611` with firm + industry FE.
4. **Purged CV + DSR** on walk-forward predictions before any strategy claim.
5. **Case-study deck** — 10 dated events (Taiwan election, Korea policy, India regulation) with shock spikes + realized market path.

---

## Caveats

- Sprint regressions use **country FE only** (not week FE) for speed; week FE may absorb macro episodes.
- Positive return coefficients may reflect **information/attention**, not mispricing.
- GDELT taxonomy is **derived metadata**, not verified article semantics.
- Entity panel history is **18 months** — governance results are illustrative.
- No multiple-testing correction applied in this sprint.
- Walk-forward results are **in-sample engineering sanity checks**, not OOS product validation.

---

## One-line pitch

> We built a weekly Asia-Pacific panel of **eight news-shock categories** fused to country markets (2018–2026). The data strongly forecast **forward volatility** and weakly forecast **4-week returns**, but the return channel looks like **attention/risk-on**, not “avoid bad news.” Firm-level governance effects need the entity panel completion; country-level work is already paper-grade with proper inference.
