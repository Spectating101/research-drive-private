# Sharpe-Renaissance

## What This Is
Quantitative trading platform with a live alpha signal pipeline. Currently paper-trading a monthly-rebalance multi-asset strategy (SEC event alpha + ridge regression walk-forward).

## Architecture

```
Data (yfinance, SEC EDGAR)
  → Feature Engineering (insights + event-proxy features)
    → Walk-Forward Backtest (ridge regression, monthly)
      → Signal Export (signal.json with weights)
        → Paper Tracker (daily mark-to-market ledger)
          → Scorecard (CAGR, Sharpe, drawdown)
```

### Active Pipeline (what runs daily)
- **`scripts/alpha_live_cycle.py`** — Main entry point. Fetches prices, builds features, runs walk-forward, exports signal, marks-to-market.
- **`scripts/alpha_paper_tracker.py`** — Simulates holding signal weights, writes daily equity to ledger.csv.
- **`scripts/alpha_daily_scorecard.py`** — Reads ledger + signal, computes performance metrics + benchmark comparison.
- **`scripts/alpha_insights_walkforward_runner.py`** — Walk-forward backtest engine (ridge regression, ic_tstat alpha mode).

### Supporting Infrastructure
- **`src/strategy/regime_policy.py`** — Mechanical regime detection (trend/vol/drawdown → parameter adjustment).
- **`src/strategy/regime_hmm.py`** — Probabilistic 2-/3-state Gaussian HMM regime model with posterior-blended params (alternative to the binary mechanical layer).
- **`src/intelligence/`** — Technical indicators, insights engine. Insight features (ins_bull/bear/warn/avg_conf/risk/anom/trend/momo) ARE fused into the alpha ridge via `build_feature_panel(use_insights=True)` — not a separate pipeline.
- **`src/research/`** — Research-integrity toolkit: `fingerprint.py`, `deflated_sharpe.py` (DSR + PBO), `attribution.py` (position-level + Brinson), `transaction_costs.py`, `factor_attribution.py` (FF5+Mom), `purged_kfold.py`, `bootstrap.py`. See `docs/RESEARCH_INTEGRITY.md`.
- **`engine/`** — Trading engine (Refinitiv analyst, LLM service, embeddings, research dispatcher). Undocumented previously.
- **`api/`** — FastAPI "FinSight" product layer: auth, billing (Stripe), SEC EDGAR data source, prometheus, structlog. `src/api/*.py` are 1-line re-export shims pointing at `api/api/*.py` — intentional indirection, not divergence.
- **`high_perf/`** — Rust extension (`sharpe_rust`): microstructure (Kyle λ, Amihud), portfolio optimization, technical indicators, parallel processing. Built with maturin. Root `main.py` falls back to a Python implementation if the wheel isn't built.
- **`trading/`** — Execution layer. `trading/execution/`: `broker_base`, `file_broker`, `alpaca_broker`, and a safety-gated `live_signal_executor` (allowed symbols, turnover cap, gross/short limits, stale-signal cutoff, limit-vs-market routing). `trading/data/providers/`: `yfinance_provider` behind a `BarsRequest` abstraction. NOT active in paper mode.
- **`agents/finrobot/`** — Git submodule (external FinRobot dependency).

### Directory Layout
```
scripts/            # ~180 Python scripts (alpha pipeline, backtests, analytics, sec/reddit/x ingest)
src/                # Core Python package (strategy, intelligence, research, models, data_sources, api shim, auth, billing, middleware)
high_perf/          # Rust extension (sharpe_rust) — microstructure, portfolio, indicators
engine/             # Refinitiv + LLM + research services
api/                # FinSight FastAPI (api/api routes, api/main.py entrypoint)
trading/            # Execution layer (broker abstractions + live executor)
systemd/            # User-unit timers (alpha-live.service + .timer)
backtests/outputs/  # Backtest results, signals, paper trading ledger
data_lake/          # Price panels, analytics packs, feature caches (gitignored — 17GB)
config/             # YAML configs, ticker lists, regime/strategy protocols
```

## Running Things

### Daily Paper Trading Cycle
```bash
python3 Sharpe-Renaissance/scripts/alpha_live_cycle.py
```

### Paper Tracker Only (mark-to-market with existing signal)
```bash
python3 Sharpe-Renaissance/scripts/alpha_paper_tracker.py \
  --signal Sharpe-Renaissance/backtests/outputs/signals/alpha_live_signal.json \
  --panel Sharpe-Renaissance/data_lake/daily_alpha_panel.csv
```

### Scorecard Only
```bash
python3 Sharpe-Renaissance/scripts/alpha_daily_scorecard.py
```

### Full Ledger Regeneration (both signals)
```bash
# 1. Delete existing ledger
rm Sharpe-Renaissance/backtests/outputs/alpha_paper/ledger.csv

# 2. Run old signal (Dec 2025)
python3 Sharpe-Renaissance/scripts/alpha_paper_tracker.py \
  --signal Sharpe-Renaissance/backtests/outputs/signals/alpha_eventproxy_cfg12.json \
  --panel Sharpe-Renaissance/data_lake/daily_alpha_panel.csv

# 3. Run new signal (Jan 2026) — overwrites overlapping dates
python3 Sharpe-Renaissance/scripts/alpha_paper_tracker.py \
  --signal Sharpe-Renaissance/backtests/outputs/signals/alpha_live_signal.json \
  --panel Sharpe-Renaissance/data_lake/daily_alpha_panel.csv

# 4. Regenerate scorecard
python3 Sharpe-Renaissance/scripts/alpha_daily_scorecard.py
```

## Tests
```bash
.venv/bin/pytest tests/ -q
# 128 tests, ~10s — covers paper tracker, scorecard metrics, regime policy,
# regime HMM, fingerprint, DSR/PBO, attribution, transaction costs, factor
# attribution, purged k-fold CV, bootstrap CIs, sec edge cycle, coingecko
# and crypto scripts. Use the venv: requires structlog/asyncpg/redis/
# fastapi/hmmlearn/statsmodels/aiohttp/tabulate (see pyproject.toml).
```

## Research Integrity Toolkit
See `docs/RESEARCH_INTEGRITY.md`. Every backtest output should carry a
fingerprint, every reported Sharpe should be deflated, every drawdown should
have a position-level attribution. CLIs:
- `python -m src.research.deflated_sharpe --outputs-dir backtests/outputs --pattern "alpha_cached_*/equity_curve.csv"`
- `python -m src.research.attribution --ledger ... --panel ... --signal ...`
- `python -m src.research.transaction_costs --ledger ... --panel ... --signal ...`
- `python -m src.research.factor_attribution --equity-curve ...`

## Current Live Signal
- **Strategy**: `alpha_eventproxy_cfg12` (ridge regression, IC t-stat alpha mode)
- **As-of**: 2026-04-30 (monthly rebalance)
- **Holdings (as of 2026-05-18)**: ETH-USD 25%, BTC-USD 24%, DBC 20%, IWM 15%, BIL 9%, GLD 3%, EFA 2.5%, EEM 2%
- **Paper trading since**: 2026-01-01; equity $9,043 (down 9.6% YTD)
- **Live signal now self-documents**: feature_cols + feature_importance (β excluding intercept) are emitted in the signal JSON.

## Key Files
| File | Purpose |
|------|---------|
| `backtests/outputs/signals/alpha_live_signal.json` | Current signal weights |
| `backtests/outputs/signals/alpha_eventproxy_cfg12.json` | Previous signal weights |
| `backtests/outputs/alpha_paper/ledger.csv` | Daily equity ledger |
| `backtests/outputs/alpha_paper/scorecard_latest.json` | Latest scorecard |
| `data_lake/daily_alpha_panel.csv` | Price panel (13 instruments, 10y) |
| `config/tickers_multi_asset_core.txt` | Ticker universe |

## Known Issues
- `datetime.utcnow()` deprecated — used in 30+ places in engine/api layer (not in active pipeline)
- `finrobot` submodule has bare `except:` clauses (external code, don't modify)
- Best backtest: CAGR 35.1%, Sharpe 1.44 (run6, 3.5yr) — but on the 13 `alpha_cached_tv*` grid, **PBO = 64.3%** and the factor-attribution α t-stat = 1.50 (not significant at 5%). The grid is largely fitting noise.
- `pandas-datareader` is broken on Python 3.13 (missing `distutils`). `factor_attribution.py` bypasses it with a direct Ken French ZIP fetcher.
- The systemd unit was running `alpha_live_cycle.py` with no flags — `--auto-params` defaulted False so the regime policy never fired in production. Fixed in `systemd/alpha-live.service`; rerun `scripts/install_alpha_live_cycle_systemd_user.sh` to pick up.

## Design Decisions
- **Monthly rebalance only** — signal weights held constant within each month
- **Paper tracker overwrites**: When signal transitions, new signal rows replace old signal rows for overlapping dates via explicit date-match removal in `_append_row`
- **Equity continuity**: New signal inherits prior signal's terminal equity at the transition date (not the last row, but equity at or before `as_of`)
- **Regime policy**: Rule-based, no LLMs — de-risks on negative trend or deep drawdown
