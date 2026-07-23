from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeMetrics:
    """
    Mechanical, trailing-only regime descriptors (no LLMs).
    """

    asof: str
    trend_12m: float
    vol_12m: float
    dd_12m: float
    risk_on: bool
    high_vol: bool


@dataclass(frozen=True)
class StrategyParams:
    """
    Knobs the strategy can adapt.
    Keep this small + interpretable.
    """

    target_vol: float
    top_n: int
    max_weight: float
    regime_off_gross: float
    alpha_tstat_scale: float
    # Optional control-layer knobs (defaults preserve old behavior).
    min_cash_weight: float = 0.05
    max_crypto_gross: float = 0.60
    cb_dd_trigger: float = 0.12
    cb_alpha_trigger: float = -0.02
    cb_alpha_window: int = 3
    cb_cooldown_months: int = 2
    cb_floor_gross: float = 0.35

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _max_drawdown(equity: pd.Series) -> float:
    e = equity.dropna()
    if e.empty:
        return float("nan")
    peak = e.cummax()
    dd = e / peak - 1.0
    return float(dd.min())


def compute_regime_metrics(
    benchmark_returns: pd.Series,
    *,
    asof: pd.Timestamp,
    window_months: int = 12,
) -> Optional[RegimeMetrics]:
    """
    benchmark_returns: month-end returns indexed by month-end timestamp.
    asof: the rebalance timestamp (month-end) at which we decide parameters.
    """
    r = benchmark_returns.copy()
    r.index = pd.to_datetime(r.index, errors="coerce")
    r = r.sort_index()
    r = r.loc[r.index <= pd.Timestamp(asof)].dropna()
    if len(r) < max(6, int(window_months)):
        return None

    win = r.iloc[-int(window_months) :].to_numpy(dtype=float)
    vol = float(np.std(win, ddof=1) * np.sqrt(12.0)) if len(win) >= 3 else float("nan")
    eq = (1.0 + pd.Series(win, index=r.index[-int(window_months) :])).cumprod()
    dd = float(_max_drawdown(eq))
    tr = float(eq.iloc[-1] / eq.iloc[0] - 1.0) if len(eq) >= 2 else float("nan")

    risk_on = bool(np.isfinite(tr) and tr > 0.0)
    high_vol = bool(np.isfinite(vol) and vol >= 0.20)
    return RegimeMetrics(
        asof=str(pd.Timestamp(asof).date()),
        trend_12m=float(tr),
        vol_12m=float(vol),
        dd_12m=float(dd),
        risk_on=risk_on,
        high_vol=high_vol,
    )


def policy_params(
    base_params: StrategyParams,
    metrics: Optional[RegimeMetrics],
) -> StrategyParams:
    """
    Simple academic-style parameter policy:
    - In risk-off or high-vol, de-risk (lower target vol, diversify, require stronger alpha).
    - In risk-on & low-vol, allow more risk and concentration.

    This is intentionally rule-based and transparent.
    """
    if metrics is None:
        return base_params

    target_vol = float(base_params.target_vol)
    top_n = int(base_params.top_n)
    max_weight = float(base_params.max_weight)
    regime_off_gross = float(base_params.regime_off_gross)
    alpha_tstat_scale = float(base_params.alpha_tstat_scale)
    min_cash_weight = float(base_params.min_cash_weight)
    max_crypto_gross = float(base_params.max_crypto_gross)
    cb_dd_trigger = float(base_params.cb_dd_trigger)
    cb_alpha_trigger = float(base_params.cb_alpha_trigger)
    cb_alpha_window = int(base_params.cb_alpha_window)
    cb_cooldown_months = int(base_params.cb_cooldown_months)
    cb_floor_gross = float(base_params.cb_floor_gross)

    # Hard de-risk triggers
    if (not metrics.risk_on) or (metrics.dd_12m <= -0.15):
        target_vol = float(np.clip(target_vol, 0.08, 0.12))
        top_n = int(max(top_n, 6))
        max_weight = float(min(max_weight, 0.25))
        # Keep some exposure; helps avoid "all cash whipsaw" while still de-risking.
        regime_off_gross = float(max(regime_off_gross, 0.25))
        alpha_tstat_scale = float(max(alpha_tstat_scale, 3.0))
        min_cash_weight = float(np.clip(max(min_cash_weight, 0.10), 0.0, 0.35))
        max_crypto_gross = float(np.clip(min(max_crypto_gross, 0.45), 0.10, 1.0))
        if cb_dd_trigger > 0:
            cb_dd_trigger = float(np.clip(min(cb_dd_trigger, 0.10), 0.03, 0.25))
        cb_alpha_trigger = float(min(cb_alpha_trigger, -0.005))
        cb_alpha_window = int(max(cb_alpha_window, 3))
        cb_cooldown_months = int(max(cb_cooldown_months, 2))
        cb_floor_gross = float(np.clip(min(cb_floor_gross, 0.30), 0.10, 1.0))
        return StrategyParams(
            target_vol=target_vol,
            top_n=top_n,
            max_weight=max_weight,
            regime_off_gross=regime_off_gross,
            alpha_tstat_scale=alpha_tstat_scale,
            min_cash_weight=min_cash_weight,
            max_crypto_gross=max_crypto_gross,
            cb_dd_trigger=cb_dd_trigger,
            cb_alpha_trigger=cb_alpha_trigger,
            cb_alpha_window=cb_alpha_window,
            cb_cooldown_months=cb_cooldown_months,
            cb_floor_gross=cb_floor_gross,
        )

    # High volatility but still positive trend: moderate de-risk
    if metrics.high_vol:
        target_vol = float(np.clip(target_vol, 0.10, 0.14))
        top_n = int(max(top_n, 5))
        max_weight = float(min(max_weight, 0.30))
        alpha_tstat_scale = float(max(alpha_tstat_scale, 2.5))
        min_cash_weight = float(np.clip(max(min_cash_weight, 0.08), 0.0, 0.30))
        max_crypto_gross = float(np.clip(min(max_crypto_gross, 0.60), 0.10, 1.0))
        if cb_dd_trigger > 0:
            cb_dd_trigger = float(np.clip(min(cb_dd_trigger, 0.12), 0.03, 0.30))
        cb_alpha_trigger = float(min(cb_alpha_trigger, -0.01))
        cb_alpha_window = int(max(cb_alpha_window, 3))
        cb_cooldown_months = int(max(cb_cooldown_months, 2))
        cb_floor_gross = float(np.clip(min(cb_floor_gross, 0.40), 0.10, 1.0))
        return StrategyParams(
            target_vol=target_vol,
            top_n=top_n,
            max_weight=max_weight,
            regime_off_gross=float(regime_off_gross),
            alpha_tstat_scale=alpha_tstat_scale,
            min_cash_weight=min_cash_weight,
            max_crypto_gross=max_crypto_gross,
            cb_dd_trigger=cb_dd_trigger,
            cb_alpha_trigger=cb_alpha_trigger,
            cb_alpha_window=cb_alpha_window,
            cb_cooldown_months=cb_cooldown_months,
            cb_floor_gross=cb_floor_gross,
        )

    # Calm, positive trend: allow more risk / concentration
    # If realized vol is very low, allow a bit more risk budget; otherwise keep base.
    if np.isfinite(metrics.vol_12m) and metrics.vol_12m < 0.14:
        target_vol = float(max(target_vol, 0.14))
    target_vol = float(np.clip(target_vol, 0.10, 0.18))
    top_n = int(max(3, min(top_n, 4)))
    max_weight = float(np.clip(max_weight, 0.25, 0.45))
    alpha_tstat_scale = float(np.clip(alpha_tstat_scale, 1.5, 2.5))
    min_cash_weight = float(np.clip(min(min_cash_weight, 0.06), 0.0, 0.20))
    max_crypto_gross = float(np.clip(max(max_crypto_gross, 0.75), 0.10, 1.0))
    if cb_dd_trigger > 0:
        cb_dd_trigger = float(np.clip(max(cb_dd_trigger, 0.12), 0.03, 0.35))
    cb_alpha_trigger = float(np.clip(cb_alpha_trigger, -0.05, -0.01))
    cb_alpha_window = int(max(2, cb_alpha_window))
    cb_cooldown_months = int(max(1, cb_cooldown_months))
    cb_floor_gross = float(np.clip(max(cb_floor_gross, 0.45), 0.10, 1.0))
    return StrategyParams(
        target_vol=target_vol,
        top_n=top_n,
        max_weight=max_weight,
        regime_off_gross=float(regime_off_gross),
        alpha_tstat_scale=alpha_tstat_scale,
        min_cash_weight=min_cash_weight,
        max_crypto_gross=max_crypto_gross,
        cb_dd_trigger=cb_dd_trigger,
        cb_alpha_trigger=cb_alpha_trigger,
        cb_alpha_window=cb_alpha_window,
        cb_cooldown_months=cb_cooldown_months,
        cb_floor_gross=cb_floor_gross,
    )
