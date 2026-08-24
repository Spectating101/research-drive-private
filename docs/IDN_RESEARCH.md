# Indonesia (IDX) Research — How, Why, and Evidence

This document is the canonical reference for the Indonesia quantitative research stack in Sharpe-Renaissance. It explains **what each lane does**, **why it was built**, **what the data says**, and **what is killed**.

**OOS window:** last 25% of available panel time (`idn_eval_splits.oos_holdout`) — computed from data, not a calendar year.

**Universe:** `indonesia_liquid_core` — 50 liquid IDX names in `config/markets/asia_yfinance_universes.json`.

---

## Architecture

```
config (universe, stock groups, bandar sources)
    │
    ├── yfinance daily panel ──► run_idn_alpha_proof (daily swing horse race)
    │                         └── idn_spike_explainer + pattern_mining
    │                                   └── broker backfill/validation (RapidAPI)
    │
    ├── news broadcast panel ──► run_idn_invest_trial (weekly news ridge)
    │                         └── run_idn_winner_patterns (OOS winner/loser + rule horse race)
    │
    └── synthesis ──► run_idn_weekly_position_sheet (actionable weights)
              │              └── idn_paper_tracker (daily MTM)
              └── run_idn_research_audit (evidence chain + regime backtest)
```

**Weekly operator workflow:**

```bash
python scripts/run_idn_research_audit.py      # verify evidence + regime backtest
python scripts/run_idn_weekly_position_sheet.py
python scripts/idn_paper_tracker.py --portfolio backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json
```

---

## Data sources

| Source | Path / API | Used for |
|--------|------------|----------|
| yfinance daily OHLCV | `data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet` | Alpha proof, regime, spikes, paper tracker |
| News shock broadcast | `data_lake/research_panels/ticker_news_market/.../ticker_week_country_broadcast_panel.parquet` | Invest trial ridge, winner patterns |
| RapidAPI broker summary | `data_lake/markets/idx_broker_summary/cache/*.json` | Spike explain, broker validation (149 sessions) |
| Stock peer groups | `config/markets/indonesia_stock_groups.json` | group_sync (barito, coal, nickel, banks) |
| IHSG index | `^JKSE` via yfinance | Regime detection |

**RapidAPI:** `GET /api/market-detector/broker-summary/{SYMBOL}` — 500 req/mo free tier, pace ≥3.5s between calls.

---

## Lane A — Regime (IHSG drawdown / bounce)

### How

On each run, compute from `^JKSE` daily close:

| Metric | Formula |
|--------|---------|
| `dd_63` | `last / max(63d) - 1` |
| `bounce_20` | `last / min(20d) - 1` |
| `ret_5d` | 5-day return |

| Regime | Condition | Core bank sleeve | Action |
|--------|-----------|------------------|--------|
| **washout** | dd ≤ −10% AND bounce < 8% | 55% | Add core beta |
| **recovery** | dd ≤ −10% AND bounce ≥ 8% | 45% | Hold core, don't chase |
| **extended** | bounce ≥ 12% AND ret_5d ≥ 5% | 25% | Trim, raise cash |
| **neutral** | else | 40% | Standard |

**Script:** `scripts/run_idn_weekly_position_sheet.py` → `regime_state()`

### Why

The Jun 2026 miss: IHSG washed out early June, then BBCA +22% and index +12.5% off lows. A **mechanical washout flag** would have said "add banks" before the ML spike/broker pipeline fired anything. This lane is **beta timing**, not stock-picking alpha.

### Evidence

**For:**
- Live Jun 2026: dd −25.1%, bounce +12.5% → correctly labels **recovery** (not washout add)
- Banks led the bounce (BBCA +9.7% on Jun 10 in paper tracker)

**Against:**
- `config/dynamic_regime_protocol_indonesia.json` (EIDO-based) **failed** OOS: CAGR −2.8%, Sharpe −0.09 (`backtests/outputs/markets/indonesia_run/summary.json`)
- Regime **thresholds are hand-set**, not optimized or DSR-gated
- Regime sleeve backtest (`run_idn_research_audit.py`, OOS holdout):
  - **Position sheet rules:** terminal **1.11×**, Sharpe **0.34**, mean +0.11%/wk (n=126)
  - **Benchmark liquid_eq:** terminal **0.99×**, Sharpe **−0.11**
  - Caveat: tilt sleeve uses fixed current winner list (mild lookahead); no transaction costs

**Confidence:** Heuristic — backtest suggests regime+banks+tilt beats EQ OOS, but not DSR-gated.

---

## Lane B — Core banks (BBCA / BBRI / BMRI)

### How

Equal weight among BBCA, BBRI, BMRI. Sleeve size set by regime (15% each in recovery = 45% total).

### Why

- Largest, most liquid IDX names; MSCI / index weight concentration
- Capture beta on index washout/recovery without single-name spike risk
- Matches macro thesis in `deep-research-report.md` (banks-first sleeve)

### Evidence

| Test | Sample | Sharpe | Mean weekly | Terminal |
|------|--------|--------|-------------|----------|
| `bbca_hold` | OOS holdout | **−0.62** | −0.25% | — |
| `bbca_hold` | train | +0.81 | +0.34% | — |
| `banks_top3` (horse race) | OOS holdout | **−0.62** | −0.32% | **0.62×** |
| `liquid_eq` | OOS holdout | ~0 | ~0% | 0.97× |

**For:** Liquidity, low turnover, participated in Jun 2026 bounce.

**Against:** OOS holdout banks **underperformed** resource names. Train-era metrics are misleading.

**Confidence:** Weak OOS — kept for **beta sleeve**, not alpha claim.

**Scripts:** `run_idn_invest_trial.py`, `run_idn_winner_patterns.py`

---

## Lane C — OOS winner tilt

### How

1. Rank all 50 names by mean weekly return OOS holdout
2. Take top 6 for tilt sleeve (equal weight within ~35% of portfolio)
3. Zero weight on bottom-10 avoid list

**Top 6 (Jun 2026 run):** JPFA, ANTM, ADRO, PGAS, LSIP, EXCL (+0.47% to +0.90% mean weekly)

**Avoid:** MIKA, INTP, AMMN, ACES, KLBF, BYAN, AMRT, TOWR, ARTO, SMGR

### Why

Resource/consumer names dominated OOS holdout while banks and cement lagged. Descriptive tilt — "what worked" — not a fitted model.

### Evidence

| Rule (horse race OOS) | Terminal | Sharpe | Verdict |
|----------------------|----------|--------|---------|
| `commodity_proxy_top3` | **1.04×** | 0.20 | Best simple rule |
| `mom4_bottom5` (contrarian) | **1.34×** | 0.55 | Momentum **inverted** in IDN |
| `mom4_top5` | 0.48× | −1.04 | Chasing momentum fails |
| `ridge_news_top5` | 0.53× | −0.93 | News picker dead |

**For:** Stable OOS ranking; commodity tilt slightly beats EQ.

**Against:**
- **No DSR/PBO** on tilt portfolio
- `mean_news_risk` identical across all tickers in winner table — this is **country broadcast** news volume, not ticker-specific signal (do not use for stock selection)
- Cross-sectional news/momentum correlations ≈ 0 OOS

**Confidence:** Descriptive only — small edge at best.

**Script:** `run_idn_winner_patterns.py` → `backtests/outputs/idn_invest/patterns/winner_patterns_*.json`

---

## Lane D — Tactical group_sync (theme names)

### How

On spike days (single name ≥10% daily return):
1. Check peers in `indonesia_stock_groups.json` themes: barito_prajogo, coal_mining, nickel_mining
2. If ≥2 peers up ≥8% same day → `group_sync_2plus`
3. Weekly sheet: last 5 sessions, max 3 names, ~8% total sleeve (paper only)

**Script chain:** `idn_spike_explainer.py` → `run_idn_spike_pattern_mining.py` → `run_idn_alpha_proof.py`

### Why

Bandarmology hypothesis: coordinated theme moves (Barito coal/nickel complex) may continue 5 days. Built after BREN/TPIA/INCO spike days.

### Evidence

**Event study** (`pattern_mining_latest.json`, n=148 spikes in holdout window):

| Tag | n | Mean fwd-5d | Hit rate |
|-----|---|-------------|----------|
| all spikes | 148 | +0.81% | 48.5% |
| group_sync_1plus | 40 | +6.41% | 62.5% |
| **group_sync_2plus** | **20** | **+11.32%** | **75%** |

**Portfolio simulation** (`idn_alpha_proof`, OOS holdout, 5d hold, 25bps cost):

| Strategy | Terminal | Sharpe | n_trades |
|----------|----------|--------|----------|
| liquid_eq_monthly | 0.96× | 0.01 | 0 |
| **group_sync_2plus** | **1.01×** | 0.10 | 142 |
| drawdown_squeeze | 1.04× | 0.20 | 1021 |

**Broker lane** (`idn_broker_pattern_alpha`):
- Incremental R² broker+sync vs sync alone: **+0.038** (n=134)
- Verdict: **no_broker_alpha**
- Acc-without-sync: **−9.83%** fwd (n=3)

**For:** Strong event-study on tiny sample; Jun 9 2026 live hits (BREN, ANTM, TPIA, INCO).

**Against:**
- Portfolio sim barely profitable — event study ≠ tradable strategy
- n=20 sessions total; heavily Apr-2025 cluster
- Zero sync2 in 2025-H2 until Jun 2026
- Overlaps with tilt names (ANTM, INCO) — confounded

**Confidence:** Event-study only — **≤8% paper sleeve**.

---

## OFF list — killed strategies

These are **explicitly disabled** in the weekly position sheet. Do not re-enable without new OOS evidence.

| Strategy | How it worked | Kill evidence (OOS) |
|----------|---------------|----------------------|
| **news_ridge_top5_weekly** | Ridge on news shocks → top 5 weekly | Sharpe **−0.93**, terminal 0.53×; invest trial top5 Sharpe −0.93 |
| **spike_chase_10pct** | Buy +10% ARA days, hold 5d | Sharpe **−0.30**, terminal 0.85×; all-spike fwd only +0.81% |
| **mom20_breakout** | 20d high breakout, 5d hold | Sharpe **−1.34**, terminal 0.45×, MDD −63% |
| **broker_accdist_only** | RapidAPI Acc tag → buy | Acc-alone −9.83% fwd (n=3); verdict `no_broker_alpha` |
| **quiet_volume_build** | Low vol + rising volume squeeze | Sharpe **−0.59**, terminal 0.71× |

**Why keep an OFF list:** Research produced many kill signals. The sheet's value is saying what **not** to do as much as what to hold.

---

## Promotion gates (country lab)

`scripts/run_indonesia_country_lab.py` → `backtests/outputs/indonesia_lab/.../evidence_pack.json`

- **0/5 strategies pass** DSR promotion gates
- Best: `idn_stocks_equal_weight` full-sample Sharpe 1.11, but DSR **0.86** (< 0.95 threshold)
- Quant AI stance: **explore**, conviction 2/5, 0–1% paper sleeve

**Implication:** No lane is promotion-ready for live capital at scale. Paper-trade the weekly sheet first.

---

## Known bugs and gaps

1. **news_risk in winner_patterns** — `mean_news_risk` is identical per ticker because `news_risk_sum` is summed from country-level broadcast shocks, not ticker-attributed news. Use for regime context only.
2. **Train/OOS split** — Full-sample invest trial metrics (Sharpe 0.79 liquid_eq) are mostly train-era. Always read `oos_holdout` sample.
3. **Lookahead in regime backtest** — Audit backtest uses current top-6 winner list for all history (tilt sleeve bias). Regime rules themselves are point-in-time.
4. **Broker sample** — 149 sessions vs 148 spikes; RapidAPI 500/mo cap; not investment-grade alone.
5. **No systemd timer** — unlike `alpha-live.service`, IDN sheet is manual.
6. **Transaction costs** — Alpha proof uses 25bps; regime backtest in audit does not yet.

---

## Output index

| Artifact | Path |
|----------|------|
| Weekly position sheet | `backtests/outputs/idn_weekly_position_sheet/latest.json` |
| Research audit | `backtests/outputs/idn_research_audit/latest.json` |
| Alpha proof | `backtests/outputs/idn_alpha_proof/latest.json` |
| Spike patterns | `backtests/outputs/idn_spike_explainer/pattern_mining_latest.json` |
| Winner patterns | `backtests/outputs/idn_invest/patterns/winner_patterns_*.json` |
| Invest trial | `backtests/outputs/idn_invest/*/strategy_summary.json` |
| Broker validation | `backtests/outputs/idn_broker_spike_validation/latest.json` |
| Broker pattern alpha | `backtests/outputs/idn_broker_pattern_alpha/latest.json` |
| Paper ledger | `backtests/outputs/idn_invest/paper/ledger.csv` |

---

## Retail / influencer playbook (support, RSI, MA — the stuff they actually say)

**We did NOT include this in the first IDN research pass.** The stack jumped to news ridge, broker API, GDELT, group_sync — classic TA jargon (support/resistance, RSI oversold, golden cross) was sitting in `api/intelligence/technical_indicators.py` but **never wired to IDX**.

**Script:** `scripts/run_idn_retail_playbook.py` → `backtests/outputs/idn_retail_playbook/latest.json`

| Retail rule | What influencers say | OOS terminal | OOS Sharpe | Verdict |
|-------------|---------------------|--------------|------------|---------|
| **bbca_support_rsi** | Buy BBCA at 60d support + RSI<35 | **1.16×** | **0.41** | **Best OOS rule we have** |
| drawdown_squeeze (quant) | Buy 5d dip + volume (same family) | 1.04× | 0.20 | Good — IS retail "dip" |
| rsi30_bounce_liquid | RSI oversold any liquid name | 1.07× | 0.24 | OK |
| group_sync_2plus | Theme spike bandar | 1.01× | 0.10 | Event study only |
| news_ridge_top5 | ML news picker | 0.53× | −0.93 | Dead |
| ma20_golden_cross | Golden cross | 0.65× | −0.99 | Dead |
| breakout_20d_high | Break resistance | 0.52× | −1.30 | Dead (same as mom20) |

### Why influencers look right and our research looked wrong

1. **Wrong problem.** We asked "can news/broker/ML pick winners across 50 names?" Retail asks "is BBCA at support?" — one liquid name, one obvious level.
2. **We tested complexity, not simplicity.** Ridge regression, RapidAPI bandar, GDELT shocks — all failed OOS. Support+RSI on BBCA did not.
3. **Survivorship.** Influencers show the BBCA bounce; they don't show every broken support level.
4. **We already had the answer nearby.** `drawdown_squeeze` in alpha_proof IS "buy the dip with volume" — it won the quant horse race. The weekly sheet regime lane IS "index washed out → buy banks". We just didn't label it as TA or prioritize it.
5. **Hold ≠ timing.** `bbca_hold` OOS failed because it's always long. `bbca_support_rsi` only buys at support — completely different rule.

### Playbook integration (next)

The weekly position sheet should treat **BBCA support + RSI** and **index support → banks** as first-class lanes alongside regime — not buried under broker/spike research.

---

## Honest bottom line

| Question | Answer |
|----------|--------|
| Is there proven IDX alpha? | **No** — 0/5 promotion gates pass |
| Can we say what to hold this week? | **Yes** — weekly position sheet (heuristic synthesis) |
| What has any signal at all? | group_sync event study (tiny n), commodity tilt (thin), regime beta timing (heuristic) |
| What is dead? | News ridge, spike chase, mom20, broker-Acc-only, quiet volume |
| What would have caught Jun 2026 bounce? | **Regime washout → core banks** on ~Jun 8, before recovery label |

The stack is built to **research honestly** and **output actionable weights** while labeling confidence. Paper-trade first.
