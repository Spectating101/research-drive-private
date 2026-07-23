"""
Composite asset screening for personal allocation decisions.

Not an alpha model. Doesn't try to predict the future. Just systematizes
the squint-at-the-chart-and-pick reasoning into a per-ticker score
constructed from observable factors:

  - Momentum (12m, 3m)
  - Trend strength (smoothed slope of log price)
  - Realized Sharpe (trailing 252d)
  - Low-volatility tilt (penalize high vol)
  - Drawdown control (penalize deep recent drawdowns)

Each factor is converted to a cross-sectional percentile within the
universe and averaged into a composite. Output is a ranked DataFrame
with the inputs visible so you can override on judgment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class ScreenConfig:
    lookback_days: int = 252 * 3  # 3 years of daily bars
    mom_long_days: int = 252
    mom_short_days: int = 63
    trend_window: int = 126
    vol_window: int = 252
    dd_window: int = 252
    risk_free_annual: float = 0.03
    factor_weights: Optional[Dict[str, float]] = None  # default equal


_DEFAULT_FACTOR_WEIGHTS = {
    "mom_12m": 1.0,
    "mom_3m": 0.5,
    "trend_strength": 1.0,
    "sharpe_252": 1.0,
    "low_vol": 0.5,
    "shallow_dd": 0.5,
}


# ---------------------------------------------------------------------------
# Per-ticker factor computation
# ---------------------------------------------------------------------------


def _factor_metrics_for_ticker(prices: pd.Series, cfg: ScreenConfig) -> Dict[str, float]:
    """Compute raw (un-percentiled) factor values from a daily price series."""
    p = prices.dropna()
    if len(p) < max(cfg.mom_long_days, cfg.trend_window, cfg.vol_window) + 5:
        return {k: float("nan") for k in _DEFAULT_FACTOR_WEIGHTS}

    # Momentum: total return over the lookback
    mom_12m = float(p.iloc[-1] / p.iloc[-cfg.mom_long_days] - 1.0)
    mom_3m = float(p.iloc[-1] / p.iloc[-cfg.mom_short_days] - 1.0)

    # Trend strength: t-stat of log-price regression slope (annualized)
    last = p.iloc[-cfg.trend_window:]
    logp = np.log(last.values)
    x = np.arange(len(logp))
    slope, intercept = np.polyfit(x, logp, 1)
    pred = slope * x + intercept
    resid = logp - pred
    se = float(np.sqrt((resid ** 2).sum() / (len(logp) - 2)) / np.sqrt(((x - x.mean()) ** 2).sum()))
    trend_tstat = float(slope / se) if se > 0 else 0.0
    # Scale up for readability (per-day slope * 252)
    trend_strength = trend_tstat * np.sign(slope)

    # Realized Sharpe
    rets = p.pct_change().dropna().iloc[-cfg.vol_window:]
    mean_d = float(rets.mean())
    std_d = float(rets.std(ddof=1))
    ann_ret = (1.0 + mean_d) ** 252 - 1.0
    ann_vol = std_d * np.sqrt(252)
    sharpe_252 = float((ann_ret - cfg.risk_free_annual) / ann_vol) if ann_vol > 0 else 0.0

    # Drawdown over window
    eq = p.iloc[-cfg.dd_window:]
    dd = float((eq / eq.cummax() - 1.0).min())

    # Low-vol score: simply -vol; we'll percentile in the caller
    low_vol = -ann_vol
    shallow_dd = dd  # higher (closer to zero) is better

    return {
        "mom_12m": mom_12m,
        "mom_3m": mom_3m,
        "trend_strength": trend_strength,
        "sharpe_252": sharpe_252,
        "low_vol": low_vol,
        "shallow_dd": shallow_dd,
        "ann_return_realized": ann_ret,
        "ann_vol_realized": ann_vol,
        "max_dd_window": dd,
        "n_obs": int(len(p)),
        "last_price": float(p.iloc[-1]),
    }


def _percentile_within(series: pd.Series) -> pd.Series:
    """Return cross-sectional percentile rank in [0, 1]."""
    return series.rank(method="average", pct=True)


# ---------------------------------------------------------------------------
# Universe-level screening
# ---------------------------------------------------------------------------


@dataclass
class ScreenResult:
    table: pd.DataFrame  # rows=ticker, cols=raw factors + percentiles + composite + flags
    as_of: pd.Timestamp
    config: ScreenConfig
    universe: List[str]


def screen_universe(
    *,
    panel_csv: Path,
    universe: Optional[Sequence[str]] = None,
    config: Optional[ScreenConfig] = None,
) -> ScreenResult:
    """
    Score every ticker in `universe` (or all tickers in the panel) by the
    composite factor model. Returns a ranked table.
    """
    cfg = config or ScreenConfig()
    fw = cfg.factor_weights or _DEFAULT_FACTOR_WEIGHTS

    df = pd.read_csv(panel_csv)
    cols = {c.lower(): c for c in df.columns}
    inst = cols.get("instrument") or "Instrument"
    date = cols.get("date") or "Date"
    px = cols.get("price_close") or "Price_Close"
    df[date] = pd.to_datetime(df[date], errors="coerce")
    df = df.dropna(subset=[date]).sort_values(date)

    available = sorted(df[inst].unique().tolist())
    if universe is None:
        universe = available
    universe = [t for t in universe if t in available]
    if not universe:
        raise ValueError("no tickers in universe match the panel")

    rows = []
    for t in universe:
        sub = df[df[inst] == t].set_index(date)[px].astype(float)
        rows.append({"ticker": t, **_factor_metrics_for_ticker(sub, cfg)})

    table = pd.DataFrame(rows).set_index("ticker")

    # Percentile-rank each factor within the universe
    for f in fw:
        table[f"{f}_pct"] = _percentile_within(table[f])

    # Composite: weighted average of factor percentiles
    weight_sum = sum(fw.values())
    pct_cols = [f"{f}_pct" for f in fw]
    weights = np.array([fw[f] for f in fw], dtype=float) / weight_sum
    table["composite_score"] = table[pct_cols].fillna(0.5).to_numpy().dot(weights)

    # Convenience flags
    table["trend_up"] = table["trend_strength"] > 0
    table["positive_mom_12m"] = table["mom_12m"] > 0
    table["below_universe_median_vol"] = table["ann_vol_realized"] < table["ann_vol_realized"].median()

    # Sort high-to-low
    table = table.sort_values("composite_score", ascending=False)

    as_of = pd.Timestamp(df[date].max())
    return ScreenResult(table=table, as_of=as_of, config=cfg, universe=list(universe))


# ---------------------------------------------------------------------------
# Allocation suggestion
# ---------------------------------------------------------------------------


def suggest_allocation(
    screen: ScreenResult,
    *,
    top_n: int = 10,
    profile: str = "balanced",
    max_single_weight: float = 0.20,
    cash_floor: float = 0.05,
    cash_ticker: str = "BIL",
) -> pd.Series:
    """
    Turn a screen into a suggested long-only allocation.

    profile:
      - "defensive": equal-weight top_n, risk-parity-tilted (1/vol)
      - "balanced":  equal-weight top_n
      - "growth":    composite-score-weighted top_n

    Always enforces cash floor + per-name cap.
    """
    if profile not in ("defensive", "balanced", "growth"):
        raise ValueError(f"unknown profile {profile!r}")

    top = screen.table.head(top_n).copy()

    if profile == "defensive":
        inv_vol = 1.0 / top["ann_vol_realized"].clip(lower=0.01)
        raw = inv_vol / inv_vol.sum()
    elif profile == "balanced":
        raw = pd.Series(1.0 / len(top), index=top.index)
    else:  # growth
        s = top["composite_score"].clip(lower=0)
        raw = s / s.sum() if s.sum() > 0 else pd.Series(1.0 / len(top), index=top.index)

    # Drop the cash ticker from the risky sleeve so we don't double-count it.
    if cash_ticker in raw.index:
        raw = raw.drop(cash_ticker)
        if raw.sum() > 0:
            raw = raw / raw.sum()

    # Scale risky sleeve to (1 - cash_floor), then iteratively cap any name
    # exceeding max_single_weight and redistribute excess to under-cap names.
    available = 1.0 - cash_floor
    weights = raw * available
    for _ in range(len(weights)):
        over = weights > max_single_weight + 1e-12
        if not over.any():
            break
        excess = (weights[over] - max_single_weight).sum()
        weights.loc[over] = max_single_weight
        under = ~over & (weights > 0)
        if under.any():
            # Redistribute proportional to current weight among under-cap names
            scale = (weights[under].sum() + excess) / weights[under].sum()
            weights.loc[under] = weights.loc[under] * scale
        else:
            # Nothing to give the excess to → it goes to cash
            break

    # Whatever didn't fit (because every name is at cap) → cash absorbs it
    cash_alloc = 1.0 - weights.sum()
    weights[cash_ticker] = cash_alloc
    return weights.sort_values(ascending=False)
