# Research Integrity Toolkit

`src/research/` adds the analytical layer that turns the Sharpe-Renaissance
alpha pipeline into a real investment research platform: every claim is
reproducible, every Sharpe is overfit-corrected, every loss is attributed,
and every backtest can be priced against realistic execution.

## Modules

### `src/research/fingerprint.py`
**Reproducibility stamping.** `make_fingerprint()` / `stamp()` attach a
`{git_commit, git_dirty, panel_sha256, config_sha256, timestamp_utc,
python_version, platform, hostname, user}` block to any output dict.

Wired into:
- `scripts/alpha_live_cycle.py` — every exported `alpha_live_signal.json`
- `scripts/alpha_daily_scorecard.py` — every `scorecard_latest.json`

Two backtests "from the same config" are now actually verifiable.

### `src/research/deflated_sharpe.py`
**Multiple-testing correction for Sharpe ratios.** Bailey & López de Prado
(2014).

- `psr()` — Probabilistic Sharpe (P(SR_true > SR* | observed))
- `deflated_sharpe()` — corrects for grid-search inflation using the
  expected max Sharpe under the null with N trials and SR variance V
- `probability_of_backtest_overfitting()` — Combinatorially-Symmetric CV
  PBO (Bailey/Borwein/LdP/Zhu 2014). Fraction of (IS/OOS) splits where the
  IS winner underperforms the OOS median.

```bash
python -m src.research.deflated_sharpe \
  --outputs-dir backtests/outputs \
  --pattern "alpha_cached_*/equity_curve.csv" \
  --pbo-splits 8
```

Real finding on the 13 `alpha_cached_tv*` configs (70 months):
- Winner Sharpe (monthly): 0.284
- DSR: 0.998 (multiple-testing-survived)
- **PBO: 64.3%** — IS-best underperforms OOS median 2/3 of the time

### `src/research/attribution.py`
**Position-level performance attribution.** Decomposes daily ledger return
into `Σ_i w_i(t) · r_i(t)` per holding, picking the active signal by
`as_of_month`. Reports per-ticker contribution (summed + log-compounded),
explained R², top/bottom-5 contributors. Includes single-period
Brinson-Fachler allocation/selection/interaction vs a benchmark.

```bash
python -m src.research.attribution \
  --ledger backtests/outputs/alpha_paper/ledger.csv \
  --panel data_lake/daily_alpha_panel.csv \
  --signal backtests/outputs/signals/*.json \
  --start 2026-01-01
```

### `src/research/transaction_costs.py`
**Realistic execution costs.** Per-asset spread+commission bps (configurable
table, defaults for cash/ETF/crypto) + square-root market impact (Almgren
et al. 2005) using Kyle-lambda-style σ·√participation.

Rebalances are detected from `as_of` transitions in the ledger; turnover is
recovered from active-vs-previous signal weights; cost is charged per leg
and a gross-vs-net daily ledger is reconstructed.

```bash
python -m src.research.transaction_costs \
  --ledger backtests/outputs/alpha_paper/ledger.csv \
  --panel data_lake/daily_alpha_panel.csv \
  --signal backtests/outputs/signals/*.json
```

Real finding: 15 bps total cost drag on the live ledger. Costs are **not**
the cause of the -9.6% bleed; it's genuine alpha loss.

### `src/research/factor_attribution.py`
**Fama-French 5 + Momentum decomposition.** Direct download + parse of
Ken French monthly CSV ZIPs (bypasses pandas-datareader, which is broken
on Python 3.13). Regresses excess strategy returns on Mkt-RF, SMB, HML,
RMW, CMA, Mom with Newey-West HAC standard errors (3-lag default).

```bash
python -m src.research.factor_attribution \
  --equity-curve backtests/outputs/alpha_cached_tv10/equity_curve.csv
```

Real finding on `alpha_cached_tv10` (70 months):
- Annualized α: 22.9%
- **α t-stat HAC: 1.50 (p=0.13) — not significant at 5%**
- Mkt-RF β: 1.39, SMB β: 1.02
- R²: 0.51

Translation: the headline CAGR is partly compensation for leveraged-equity
+ small-cap factor exposure.

### `src/research/purged_kfold.py`
**Purged k-fold CV for ridge λ selection.** López de Prado (AFML 2018). Drops
training observations whose label-horizon overlaps the test fold + applies
an embargo window after each test fold. Drop-in alternative to the
chronological 75/25 CV in `_cv_select_lambda` — provided as opt-in to
avoid disrupting the live signal mid-month.

### `src/research/bootstrap.py`
**Block-bootstrap CIs for ridge coefficients.** Block bootstrap (Politis &
Romano 1994) over periods preserves cross-section within a period and
short-run autocorrelation within blocks. Reports per-feature
`{point_estimate, bootstrap_se, ci_lo, ci_median, ci_hi, significant_5pct}`.

Tells you which `ins_*` / `mom_*` / `vol_*` features the ridge actually
trusts and which are noise that happen to fit in-sample.

## `src/strategy/regime_hmm.py`
**Gaussian HMM regime model** as a probabilistic alternative to the binary
`regime_policy.py`. 2- or 3-state HMM on monthly benchmark returns
(optionally + rolling vol). Posterior is exposed so callers can **blend**
parameters across regimes instead of flipping at the boundary.

Auto-orders states bear→bull by expected return regardless of EM init.

## Standing operating instructions

- **Every new backtest output should carry a fingerprint.** If it doesn't,
  the result isn't reproducible and shouldn't be cited.
- **No claim about strategy quality without DSR + PBO** if multiple configs
  were searched.
- **Quote net-of-cost Sharpe**, not gross, in any external context.
- **Quote alpha t-stat HAC**, not raw α, when describing factor-adjusted
  performance.

## Running the test suite

```bash
.venv/bin/pytest tests/ -q
# 128 tests, ~10s
```

All research-integrity modules are tested independently (synthetic data
with known answers); no external network needed unless explicitly fetching
Ken French factors.
