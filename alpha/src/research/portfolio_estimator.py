"""
Forward portfolio estimates: expected return, vol, Sharpe, drawdown range, stress.

Honest forecasting — no point estimates pretending to be certainty. Every
number comes with a band:

  - Median 1y return, plus 5th / 95th percentile bracket
  - Annualized volatility (parametric, from the covariance matrix)
  - Expected Sharpe at the median return
  - Monte-Carlo distribution of 252-day max drawdown
  - Stress scenarios: what each named historical regime would have cost

Inputs that matter
------------------
- mu (expected return per ticker) is *shrunk* — equal-weight blend of the
  long-run historical mean and the CAPM-implied mean (β·equity-premium).
  Raw historical means are wildly unstable; shrinking toward a structural
  anchor stops you from extrapolating last year's lucky run into a forever
  forecast.
- Sigma (covariance matrix) uses Ledoit-Wolf-style shrinkage toward a
  diagonal of variances, so unstable off-diagonals don't blow up the vol.
- All annualization uses sqrt(252).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class EstimatorConfig:
    lookback_days: int = 252 * 5  # 5y of daily bars
    risk_free_annual: float = 0.03
    equity_premium_annual: float = 0.05  # CAPM premium assumption
    shrinkage_lambda: float = 0.5  # 0 = pure historical, 1 = pure CAPM
    cov_shrinkage: float = 0.20  # Ledoit-Wolf-style toward diag
    market_proxy: str = "SPY"
    n_simulations: int = 1000
    sim_horizon_days: int = 252
    seed: int = 0


@dataclass
class PortfolioEstimate:
    weights: pd.Series
    per_ticker_exp_return: pd.Series  # annualized
    per_ticker_vol: pd.Series  # annualized
    per_ticker_beta: pd.Series
    portfolio_exp_return: float
    portfolio_vol: float
    portfolio_sharpe: float
    return_p05: float
    return_p50: float
    return_p95: float
    expected_max_dd_p50: float
    expected_max_dd_p05: float
    expected_max_dd_p95: float
    stress: pd.DataFrame  # rows=scenario, cols=portfolio_loss + per-ticker contribution
    config: EstimatorConfig


# ---------------------------------------------------------------------------
# Loaders + per-ticker statistics
# ---------------------------------------------------------------------------


def _wide_returns(panel_csv: Path, lookback_days: int) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    cols = {c.lower(): c for c in df.columns}
    inst = cols.get("instrument") or "Instrument"
    date = cols.get("date") or "Date"
    px = cols.get("price_close") or "Price_Close"
    df[date] = pd.to_datetime(df[date], errors="coerce")
    df = df.dropna(subset=[date]).sort_values(date)
    wide_px = df.pivot_table(index=date, columns=inst, values=px, aggfunc="last").sort_index()
    wide_rets = wide_px.pct_change().dropna(how="all")
    return wide_rets.tail(lookback_days)


def _shrunk_mean_returns(
    rets: pd.DataFrame,
    *,
    market_proxy: str,
    rf: float,
    equity_premium: float,
    lambda_: float,
) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
        historical_mean_ann, beta_to_market, capm_implied_ann, shrunk_mean_ann
    """
    hist_mean_ann = ((1.0 + rets.mean()) ** 252 - 1.0)
    out = pd.DataFrame({"historical_mean_ann": hist_mean_ann})

    if market_proxy not in rets.columns:
        # Fall back: assume β=1 for all (rare; only if market_proxy is missing)
        out["beta_to_market"] = 1.0
    else:
        mkt = rets[market_proxy]
        mkt_var = float(mkt.var(ddof=1))
        if mkt_var <= 0:
            out["beta_to_market"] = 1.0
        else:
            cov_with_mkt = rets.apply(lambda c: float(c.cov(mkt)))
            out["beta_to_market"] = cov_with_mkt / mkt_var

    out["capm_implied_ann"] = rf + out["beta_to_market"] * equity_premium
    out["shrunk_mean_ann"] = (
        (1.0 - lambda_) * out["historical_mean_ann"] + lambda_ * out["capm_implied_ann"]
    )
    return out


def _shrunk_cov_matrix(rets: pd.DataFrame, *, shrinkage: float) -> pd.DataFrame:
    """Linear shrinkage of sample covariance toward a diagonal of variances."""
    sample = rets.cov()
    diag = pd.DataFrame(np.diag(np.diag(sample)), index=sample.index, columns=sample.columns)
    return (1.0 - shrinkage) * sample + shrinkage * diag


# ---------------------------------------------------------------------------
# Stress scenarios — historical windows projected onto current weights
# ---------------------------------------------------------------------------


# (name, start, end) — well-known regime episodes
DEFAULT_STRESS_WINDOWS = [
    ("2008 GFC peak loss (Sep-Nov 2008)", "2008-09-01", "2008-11-30"),
    ("2020 COVID crash (Feb-Mar 2020)", "2020-02-15", "2020-03-31"),
    ("2022 rates+inflation shock (full year)", "2022-01-01", "2022-12-31"),
    ("2018 Q4 selloff (Oct-Dec 2018)", "2018-10-01", "2018-12-31"),
    ("2015-2016 China devaluation (Aug 2015 - Feb 2016)", "2015-08-01", "2016-02-29"),
]


def _stress_test(
    weights: pd.Series,
    panel_csv: Path,
    windows: Sequence,
) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    cols = {c.lower(): c for c in df.columns}
    inst = cols.get("instrument") or "Instrument"
    date = cols.get("date") or "Date"
    px = cols.get("price_close") or "Price_Close"
    df[date] = pd.to_datetime(df[date], errors="coerce")
    df = df.dropna(subset=[date])
    wide_px = df.pivot_table(index=date, columns=inst, values=px, aggfunc="last").sort_index()

    rows = []
    for name, start, end in windows:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        sl = wide_px.loc[(wide_px.index >= s) & (wide_px.index <= e)]
        if sl.empty:
            rows.append({"scenario": name, "available": False, "portfolio_pnl_est": float("nan")})
            continue
        # Per-ticker total return over the window
        first = sl.iloc[0]
        last = sl.iloc[-1]
        rets = (last / first - 1.0)
        # Restrict to overlap with weights
        common = [t for t in weights.index if t in rets.index and pd.notna(rets[t])]
        if not common:
            rows.append({"scenario": name, "available": False, "portfolio_pnl_est": float("nan")})
            continue
        wsub = weights.loc[common]
        wsub = wsub / wsub.sum() if wsub.sum() != 0 else wsub
        pnl = float((wsub * rets[common]).sum())
        rows.append({
            "scenario": name,
            "available": True,
            "n_tickers_with_data": len(common),
            "portfolio_pnl_est": pnl,
            "window_start": start,
            "window_end": end,
        })
    return pd.DataFrame(rows).set_index("scenario")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def estimate_portfolio(
    *,
    weights: pd.Series,
    panel_csv: Path,
    config: Optional[EstimatorConfig] = None,
    stress_windows=None,
) -> PortfolioEstimate:
    cfg = config or EstimatorConfig()
    windows = stress_windows or DEFAULT_STRESS_WINDOWS

    rets = _wide_returns(panel_csv, cfg.lookback_days)
    # Align to weight tickers present in panel
    w = weights[weights.index.isin(rets.columns)].copy()
    if w.empty:
        raise ValueError("no weighted tickers present in panel")
    if w.sum() == 0:
        raise ValueError("weights sum to zero")
    w = w / w.sum()  # renormalize
    rets = rets[w.index].dropna(how="all")

    means = _shrunk_mean_returns(
        rets,
        market_proxy=cfg.market_proxy,
        rf=cfg.risk_free_annual,
        equity_premium=cfg.equity_premium_annual,
        lambda_=cfg.shrinkage_lambda,
    )
    per_ticker_ann_vol = rets.std(ddof=1) * np.sqrt(252)

    cov_d = _shrunk_cov_matrix(rets, shrinkage=cfg.cov_shrinkage)
    cov_ann = cov_d * 252.0

    mu_vec = means.loc[w.index, "shrunk_mean_ann"].values
    sigma_mat = cov_ann.loc[w.index, w.index].values
    w_vec = w.values

    port_mu = float(w_vec @ mu_vec)
    port_var = float(w_vec @ sigma_mat @ w_vec)
    port_sigma = float(np.sqrt(max(port_var, 0.0)))
    port_sharpe = float((port_mu - cfg.risk_free_annual) / port_sigma) if port_sigma > 0 else float("nan")

    # 1y return distribution (assumes Normal — fine for a portfolio of 10+ assets)
    from scipy.stats import norm
    z05, z50, z95 = norm.ppf([0.05, 0.50, 0.95])
    ret_p05 = port_mu + z05 * port_sigma
    ret_p50 = port_mu + z50 * port_sigma
    ret_p95 = port_mu + z95 * port_sigma

    # Monte Carlo for max drawdown distribution
    rng = np.random.default_rng(cfg.seed)
    daily_mu = (1.0 + port_mu) ** (1.0 / 252) - 1.0
    daily_sigma = port_sigma / np.sqrt(252)
    sims = rng.normal(daily_mu, daily_sigma, size=(cfg.n_simulations, cfg.sim_horizon_days))
    equity_paths = np.cumprod(1.0 + sims, axis=1)
    running_max = np.maximum.accumulate(equity_paths, axis=1)
    drawdowns = equity_paths / running_max - 1.0
    max_dd_per_sim = drawdowns.min(axis=1)
    dd_p05 = float(np.percentile(max_dd_per_sim, 5))
    dd_p50 = float(np.percentile(max_dd_per_sim, 50))
    dd_p95 = float(np.percentile(max_dd_per_sim, 95))

    stress = _stress_test(w, panel_csv, windows)

    return PortfolioEstimate(
        weights=w,
        per_ticker_exp_return=means.loc[w.index, "shrunk_mean_ann"],
        per_ticker_vol=per_ticker_ann_vol.loc[w.index],
        per_ticker_beta=means.loc[w.index, "beta_to_market"],
        portfolio_exp_return=port_mu,
        portfolio_vol=port_sigma,
        portfolio_sharpe=port_sharpe,
        return_p05=float(ret_p05),
        return_p50=float(ret_p50),
        return_p95=float(ret_p95),
        expected_max_dd_p50=dd_p50,
        expected_max_dd_p05=dd_p05,
        expected_max_dd_p95=dd_p95,
        stress=stress,
        config=cfg,
    )


def estimate_summary(est: PortfolioEstimate) -> Dict:
    return {
        "portfolio": {
            "expected_annual_return": est.portfolio_exp_return,
            "annual_vol": est.portfolio_vol,
            "expected_sharpe": est.portfolio_sharpe,
            "return_p05_1y": est.return_p05,
            "return_p50_1y": est.return_p50,
            "return_p95_1y": est.return_p95,
            "expected_max_drawdown_252d_p50": est.expected_max_dd_p50,
            "expected_max_drawdown_252d_p05": est.expected_max_dd_p05,
            "expected_max_drawdown_252d_p95": est.expected_max_dd_p95,
        },
        "weights": {k: float(v) for k, v in est.weights.items()},
        "per_ticker": {
            t: {
                "weight": float(est.weights[t]),
                "expected_annual_return": float(est.per_ticker_exp_return[t]),
                "annual_vol": float(est.per_ticker_vol[t]),
                "beta_to_market": float(est.per_ticker_beta[t]),
            }
            for t in est.weights.index
        },
        "stress": est.stress.reset_index().to_dict(orient="records"),
        "config": {
            "lookback_days": est.config.lookback_days,
            "risk_free_annual": est.config.risk_free_annual,
            "equity_premium_annual": est.config.equity_premium_annual,
            "shrinkage_lambda": est.config.shrinkage_lambda,
            "cov_shrinkage": est.config.cov_shrinkage,
            "market_proxy": est.config.market_proxy,
            "n_simulations": est.config.n_simulations,
        },
        "caveats": [
            "Expected returns are SHRUNK toward CAPM (β·equity_premium + rf), not raw historical means.",
            "1y return percentiles assume Normal distribution at the portfolio level; tails are systematically underestimated for crash-prone books.",
            "Drawdown estimate is Monte Carlo on a Geometric Brownian Motion approximation — it understates regime-change risk.",
            "Stress scenarios show what HISTORICAL episodes would have cost the CURRENT weights; they don't predict the next crash, only quantify exposure to past ones.",
            "Risk-free rate assumed flat at config.risk_free_annual — adjust for current 3-month T-bill if you want a precise Sharpe.",
            "Past returns do not predict future returns. This is decision support, not advice.",
        ],
    }
