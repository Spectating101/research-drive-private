#!/usr/bin/env python3
from __future__ import annotations

"""
Walk-forward "alpha + risk" runner (no lookahead).

Goal:
- Learn a simple expected-return model from past data (ridge regression)
- Use it to allocate across a universe each rebalance date
- Keep risk overlays optional (cash fallback, max weight, turnover costs)

This is an *alpha* layer (predict next-period returns), not just a risk overlay.

Input panel format:
  Instrument, Date, Price_Close, Volume(optional)
"""

import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.intelligence.insights_engine import InsightsEngine  # noqa: E402
from src.strategy.control_profiles import apply_profile_to_namespace, profiles_json  # noqa: E402
from src.strategy.regime_policy import StrategyParams, compute_regime_metrics, policy_params  # noqa: E402


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _jsonable_args(ns: argparse.Namespace) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in vars(ns).items():
        if isinstance(v, Path):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [str(x) if isinstance(x, Path) else x for x in v]
        else:
            out[k] = v
    return out


def _to_month_end_index(d: pd.Series) -> pd.DatetimeIndex:
    return pd.to_datetime(d, errors="coerce").dt.to_period("M").dt.to_timestamp("M")


def _cagr(equity: pd.Series) -> float:
    equity = equity.dropna()
    if len(equity) < 2:
        return float("nan")
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def _sharpe(returns: pd.Series, periods_per_year: float = 12.0) -> float:
    r = returns.dropna()
    if len(r) < 3:
        return float("nan")
    mu = float(r.mean())
    sd = float(r.std(ddof=1))
    if sd <= 0:
        return float("nan")
    return float((mu / sd) * math.sqrt(periods_per_year))


def _max_drawdown(equity: pd.Series) -> float:
    e = equity.dropna()
    if e.empty:
        return float("nan")
    peak = e.cummax()
    dd = e / peak - 1.0
    return float(dd.min())


def _turnover(prev_w: pd.Series, w: pd.Series) -> float:
    prev = prev_w.reindex(w.index).fillna(0.0)
    cur = w.fillna(0.0)
    return float(0.5 * np.abs(cur.values - prev.values).sum())


def _corr_filter_select(
    candidates: pd.DataFrame,
    *,
    already: List[str],
    want: int,
    trailing_returns: pd.DataFrame,
    corr_threshold: float,
) -> List[str]:
    """
    Greedy diversification: take highest-ranked candidates while limiting max pairwise corr.
    """
    picks: List[str] = []
    for inst in candidates["instrument"].astype(str).tolist():
        if inst in already or inst in picks:
            continue
        if not picks:
            picks.append(inst)
            if len(picks) >= want:
                break
            continue

        cols = [c for c in picks + [inst] if c in trailing_returns.columns]
        if len(cols) < 2:
            picks.append(inst)
            if len(picks) >= want:
                break
            continue

        sub = trailing_returns[cols].dropna(axis=0, how="any")
        if len(sub) < 6:
            picks.append(inst)
            if len(picks) >= want:
                break
            continue

        corr = sub.corr()
        mx = float(np.abs(corr.loc[inst, picks]).max())
        if mx <= float(corr_threshold):
            picks.append(inst)
            if len(picks) >= want:
                break
    return picks


def _risk_budget_weights(
    picks: pd.DataFrame,
    *,
    pred_col: str,
    trailing_returns: pd.DataFrame,
    vol_lookback: int,
) -> pd.Series:
    """
    Long-only weights proportional to signal / trailing vol.
    """
    insts = picks["instrument"].astype(str).tolist()
    preds = pd.to_numeric(picks[pred_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    preds = np.clip(preds, 0.0, np.inf)
    if preds.sum() <= 0:
        return pd.Series(0.0, index=insts, dtype=float)

    tr = trailing_returns.reindex(columns=insts)
    vol = tr.rolling(int(vol_lookback)).std(ddof=1).iloc[-1]
    vol = pd.to_numeric(vol, errors="coerce").fillna(np.nan)
    vol = vol.replace([0.0, -0.0], np.nan).fillna(vol.dropna().median() if vol.notna().any() else 1.0)
    inv_risk = 1.0 / vol.to_numpy(dtype=float)
    score = preds * inv_risk
    score = np.clip(score, 0.0, np.inf)
    denom = float(score.sum()) or 1.0
    return pd.Series(score / denom, index=insts, dtype=float)


def _apply_sleeve_controls(
    w: pd.Series,
    *,
    cash_ticker: Optional[str],
    min_cash_weight: float,
    max_crypto_gross: float,
) -> pd.Series:
    """
    Apply deterministic sleeve controls:
    - minimum cash weight floor
    - maximum aggregate crypto gross (tickers ending with -USD)
    """
    out = w.copy().fillna(0.0).astype(float)
    out = out.clip(lower=0.0)
    if out.sum() > 0:
        out = out / out.sum()

    crypto_cols = [c for c in out.index if str(c).endswith("-USD") and (cash_ticker is None or str(c) != str(cash_ticker))]
    cap_crypto = float(_clamp(float(max_crypto_gross), 0.0, 1.0))
    if crypto_cols and cap_crypto < 1.0:
        csum = float(out.loc[crypto_cols].sum())
        if csum > cap_crypto + 1e-12:
            out.loc[crypto_cols] = out.loc[crypto_cols] * float(cap_crypto / csum)

    min_cash = float(_clamp(float(min_cash_weight), 0.0, 1.0))
    if cash_ticker and cash_ticker in out.index and min_cash > 0.0:
        risky_cols = [c for c in out.index if c != cash_ticker]
        risky_sum = float(out.loc[risky_cols].sum()) if risky_cols else 0.0
        max_risky = float(max(0.0, 1.0 - min_cash))
        if risky_sum > max_risky + 1e-12 and risky_sum > 0:
            out.loc[risky_cols] = out.loc[risky_cols] * float(max_risky / risky_sum)
        out.loc[cash_ticker] = float(1.0 - out.drop(labels=[cash_ticker]).sum())

    out = out.clip(lower=0.0)
    if out.sum() > 0:
        out = out / out.sum()
    return out


def _ridge_fit(X: np.ndarray, y: np.ndarray, lam: float, w: Optional[np.ndarray] = None) -> np.ndarray:
    # Closed-form weighted ridge: (X'WX + lam I)^-1 X'Wy
    if w is not None:
        W = np.diag(w)
        XtWX = X.T @ W @ X
        XtWy = X.T @ (w * y)
    else:
        XtWX = X.T @ X
        XtWy = X.T @ y
    k = XtWX.shape[0]
    return np.linalg.solve(XtWX + float(lam) * np.eye(k), XtWy)


def _spearman_ic(a: np.ndarray, b: np.ndarray) -> float:
    # Minimal spearman correlation without scipy: rank then pearson.
    if len(a) < 3:
        return float("nan")
    ra = pd.Series(a).rank(method="average").to_numpy()
    rb = pd.Series(b).rank(method="average").to_numpy()
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = float(np.sqrt((ra**2).sum()) * np.sqrt((rb**2).sum()))
    if denom <= 0:
        return float("nan")
    return float((ra * rb).sum() / denom)


def _cv_select_lambda(
    train: pd.DataFrame,
    feature_cols: List[str],
    lam_grid: List[float],
    min_assets: int,
) -> float:
    """Pick regularisation lambda via chronological CV on the training window.

    Splits training data 75/25 chronologically (sub-train / sub-val),
    fits ridge for each lambda on sub-train, scores mean Spearman IC on
    sub-val months, returns the lambda with the highest IC.
    Falls back to the middle of the grid if all ICs <= 0.
    """
    train = _with_date_column(train)
    if "date" not in train.columns:
        return float(lam_grid[len(lam_grid) // 2])

    if len(lam_grid) == 1:
        return float(lam_grid[0])

    dates = sorted(train["date"].unique())
    split = int(len(dates) * 0.75)
    if split < 2 or split >= len(dates) - 1:
        return float(lam_grid[len(lam_grid) // 2])

    sub_train = train[train["date"].isin(dates[:split])].copy()
    sub_val = train[train["date"].isin(dates[split:])].copy()

    sub_train = sub_train.dropna(subset=feature_cols + ["ret_fwd_1m"])
    sub_val = sub_val.dropna(subset=feature_cols + ["ret_fwd_1m"])
    if sub_train.empty or sub_val.empty:
        return float(lam_grid[len(lam_grid) // 2])

    X_tr = np.column_stack([np.ones(len(sub_train)), sub_train[feature_cols].to_numpy(dtype=float)])
    y_tr = sub_train["ret_fwd_1m"].to_numpy(dtype=float)
    X_val = np.column_stack([np.ones(len(sub_val)), sub_val[feature_cols].to_numpy(dtype=float)])

    best_ic = -np.inf
    best_lam = float(lam_grid[len(lam_grid) // 2])
    for lam in lam_grid:
        beta = _ridge_fit(X_tr, y_tr, lam=float(lam))
        pred = X_val @ beta
        ics: List[float] = []
        sv = sub_val.assign(pred=pred)
        for _, g in sv.groupby("date"):
            g = g.dropna(subset=["pred", "ret_fwd_1m"])
            if g["instrument"].nunique() < min_assets:
                continue
            ic = _spearman_ic(g["pred"].to_numpy(dtype=float), g["ret_fwd_1m"].to_numpy(dtype=float))
            if np.isfinite(ic):
                ics.append(float(ic))
        mean_ic = float(np.mean(ics)) if ics else -np.inf
        if mean_ic > best_ic:
            best_ic = mean_ic
            best_lam = float(lam)

    if best_ic <= 0:
        return float(lam_grid[len(lam_grid) // 2])
    return best_lam


def _cv_ensemble_predict(
    X: np.ndarray,
    y: np.ndarray,
    Xt: np.ndarray,
    lam_grid: List[float],
    cv_train: pd.DataFrame,
    cv_val: pd.DataFrame,
    feature_cols: List[str],
    min_assets: int,
    w: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Blend predictions from multiple lambdas, weighted by CV IC.

    Instead of picking a single best lambda, computes IC-weighted average
    of predictions from all lambdas with positive IC.  Falls back to
    the single best lambda if only one has positive IC.
    """
    if len(lam_grid) <= 1:
        beta = _ridge_fit(X, y, lam=float(lam_grid[0]), w=w)
        return Xt @ beta

    X_tr = np.column_stack([np.ones(len(cv_train)), cv_train[feature_cols].to_numpy(dtype=float)])
    y_tr = cv_train["ret_fwd_1m"].to_numpy(dtype=float)
    X_val = np.column_stack([np.ones(len(cv_val)), cv_val[feature_cols].to_numpy(dtype=float)])

    lam_ics: List[Tuple[float, float]] = []
    for lam in lam_grid:
        beta = _ridge_fit(X_tr, y_tr, lam=float(lam))
        pred = X_val @ beta
        ics: List[float] = []
        sv = cv_val.assign(pred=pred)
        for _, g in sv.groupby("date"):
            g = g.dropna(subset=["pred", "ret_fwd_1m"])
            if g["instrument"].nunique() < min_assets:
                continue
            ic = _spearman_ic(g["pred"].to_numpy(dtype=float), g["ret_fwd_1m"].to_numpy(dtype=float))
            if np.isfinite(ic):
                ics.append(float(ic))
        mean_ic = float(np.mean(ics)) if ics else -1.0
        lam_ics.append((lam, mean_ic))

    # Filter to positive-IC lambdas.
    positive = [(lam, ic) for lam, ic in lam_ics if ic > 0]
    if not positive:
        # Fallback: use middle lambda.
        beta = _ridge_fit(X, y, lam=float(lam_grid[len(lam_grid) // 2]), w=w)
        return Xt @ beta
    if len(positive) == 1:
        beta = _ridge_fit(X, y, lam=float(positive[0][0]), w=w)
        return Xt @ beta

    # IC-weighted blend.
    total_ic = sum(ic for _, ic in positive)
    pred = np.zeros(Xt.shape[0])
    for lam, ic in positive:
        beta = _ridge_fit(X, y, lam=float(lam), w=w)
        pred += (ic / total_ic) * (Xt @ beta)
    return pred


def _screen_features_by_ic(
    train: pd.DataFrame,
    feature_cols: List[str],
    min_assets: int,
    ic_months: int = 12,
) -> List[str]:
    """Keep only features with positive trailing cross-sectional IC.

    For each feature, compute Spearman IC vs forward returns across
    the most recent ic_months of training data.  Only keep features
    with mean IC > 0.
    """
    train = _with_date_column(train)
    if "date" not in train.columns or not feature_cols:
        return feature_cols

    dates = sorted(train["date"].unique())
    recent = dates[-ic_months:] if len(dates) >= ic_months else dates
    sub = train[train["date"].isin(recent)].copy()

    keep: List[str] = []
    for fc in feature_cols:
        ics: List[float] = []
        for _, g in sub.groupby("date"):
            g = g.dropna(subset=[fc, "ret_fwd_1m"])
            if g["instrument"].nunique() < min_assets:
                continue
            ic = _spearman_ic(g[fc].to_numpy(dtype=float), g["ret_fwd_1m"].to_numpy(dtype=float))
            if np.isfinite(ic):
                ics.append(float(ic))
        if ics and float(np.mean(ics)) > 0:
            keep.append(fc)

    # Always keep at least 3 features (don't over-prune).
    if len(keep) < 3:
        return feature_cols
    return keep


def _exp_decay_weights(n: int, half_life_months: float) -> np.ndarray:
    """Exponential decay weights: most recent observation = 1.0, decaying backwards."""
    if half_life_months <= 0 or n <= 1:
        return np.ones(n, dtype=float)
    lam = math.log(2.0) / float(half_life_months)
    t = np.arange(n, dtype=float)[::-1]  # n-1, n-2, ..., 0
    w = np.exp(-lam * t)
    return w / w.sum() * n  # normalize so sum = n (preserves effective sample size scaling)


def _with_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a pandas DataFrame has a concrete `date` column.
    Compatible with newer pandas groupby/apply behaviors where grouping keys may be excluded.
    """
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        return out

    if isinstance(out.index, pd.MultiIndex):
        names = list(out.index.names)
        if "date" in names:
            out = out.reset_index(level="date")
        else:
            out = out.reset_index()
            first = out.columns[0]
            out = out.rename(columns={first: "date"})
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        return out

    out["date"] = pd.to_datetime(out.index, errors="coerce")
    return out


def _standardize_cross_section(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        x = out[c].astype(float)
        mu = float(x.mean())
        sd = float(x.std(ddof=0))
        if not np.isfinite(sd) or sd <= 1e-12:
            out[c] = 0.0
        else:
            out[c] = (x - mu) / sd
    return out


def _standardize_cross_section_by_date(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Cross-section z-score within each date using transform (avoids groupby.apply key-dropping quirks).
    """
    out = _with_date_column(df)
    if "date" not in out.columns:
        return _standardize_cross_section(out, cols)

    for c in cols:
        x = pd.to_numeric(out[c], errors="coerce")
        g = out.groupby("date")[c]
        mu = g.transform("mean")
        sd = g.transform(lambda s: s.std(ddof=0))
        z = (x - mu) / sd
        out[c] = pd.to_numeric(z, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def load_panel(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    need = {"Instrument", "Date", "Price_Close"}
    if not need.issubset(df.columns):
        raise ValueError(f"Panel must include columns: {sorted(need)}")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Instrument", "Price_Close"])
    df = df.sort_values(["Instrument", "Date"])
    return df


def daily_close_wide(panel: pd.DataFrame) -> pd.DataFrame:
    wide = panel.pivot_table(index="Date", columns="Instrument", values="Price_Close", aggfunc="last").sort_index()
    wide = wide.dropna(axis=0, how="all")
    return wide


def daily_volume_wide(panel: pd.DataFrame) -> Optional[pd.DataFrame]:
    if "Volume" not in panel.columns:
        return None
    wide = panel.pivot_table(index="Date", columns="Instrument", values="Volume", aggfunc="last").sort_index()
    wide = wide.dropna(axis=0, how="all")
    return wide


def monthly_close_and_returns(close_daily: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    close_m = close_daily.resample("ME").last()
    ret_m = close_m.pct_change()
    return close_m, ret_m


def _daily_event_proxy_features(
    close_daily: pd.DataFrame,
    volume_daily: Optional[pd.DataFrame],
    *,
    lookback_days: int = 21,
    volz_days: int = 60,
    extended: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    Create monthly (month-end) features derived from daily price/volume.

    These are "event proxies" (earnings-like or news-like bursts) without needing
    an external event calendar.
    """
    if close_daily.empty:
        return {}

    # IMPORTANT: mixed universes often include crypto (weekends) + equities (weekdays).
    # We tolerate missing weekend equity prints by using rolling min_periods < window.
    window = int(max(5, lookback_days))
    minp = int(max(3, math.floor(0.7 * window)))

    # Forward-fill to avoid calendar mismatch (e.g., crypto weekends) breaking pct_change for equities.
    close_ff = close_daily.sort_index().ffill()
    dret = close_ff.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    dvol = dret.rolling(window=window, min_periods=minp).std(ddof=1) * math.sqrt(252.0)
    max_1d = dret.rolling(window=window, min_periods=minp).max()
    min_1d = dret.rolling(window=window, min_periods=minp).min()

    # Tail event count: number of days with |ret| > 2 * trailing daily std.
    dstd = dret.rolling(window=max(10, window), min_periods=max(5, minp)).std(ddof=1)
    tail = (dret.abs() > (2.0 * dstd)).astype(float).rolling(window=window, min_periods=minp).sum()

    feats: Dict[str, pd.DataFrame] = {
        "dvol_1m": dvol.resample("ME").last(),
        "dmax_1m": max_1d.resample("ME").last(),
        "dmin_1m": min_1d.resample("ME").last(),
        "dtail_cnt_1m": tail.resample("ME").last(),
    }

    zret = None
    if bool(extended):
        # Standardized return shock metrics (captures index reconstitution / rebalance "debacle" footprints).
        eps = 1e-12
        zret = (dret / (dstd + eps)).replace([np.inf, -np.inf], np.nan).clip(-20.0, 20.0)
        shock_cnt_z3 = (zret.abs() > 3.0).astype(float).rolling(window=window, min_periods=minp).sum()
        shock_cnt_z4 = (zret.abs() > 4.0).astype(float).rolling(window=window, min_periods=minp).sum()
        feats["dmax_z_1m"] = zret.rolling(window=window, min_periods=minp).max().resample("ME").last()
        feats["dmin_z_1m"] = zret.rolling(window=window, min_periods=minp).min().resample("ME").last()
        feats["dshock_cnt_z3_1m"] = shock_cnt_z3.resample("ME").last()
        feats["dshock_cnt_z4_1m"] = shock_cnt_z4.resample("ME").last()

    if volume_daily is not None and not volume_daily.empty:
        vol = volume_daily.reindex(close_daily.index).copy()
        vol = vol.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        lv = np.log1p(vol.clip(lower=0.0))
        vwin = int(max(10, volz_days))
        vminp = int(max(5, math.floor(0.7 * vwin)))
        mu = lv.rolling(window=vwin, min_periods=vminp).mean()
        sd = lv.rolling(window=vwin, min_periods=vminp).std(ddof=1)
        z = (lv - mu) / sd.replace(0.0, np.nan)
        feats["vol_z"] = z.resample("ME").last()

        # Dollar-volume z-score (captures "forced flow" / rebalance pressure better than raw volume).
        dv = (close_ff.reindex(vol.index).ffill() * vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        ldv = np.log1p(dv.clip(lower=0.0))
        dmu = ldv.rolling(window=vwin, min_periods=vminp).mean()
        dsd = ldv.rolling(window=vwin, min_periods=vminp).std(ddof=1)
        dvz = (ldv - dmu) / dsd.replace(0.0, np.nan)
        feats["dollar_vol_z"] = dvz.resample("ME").last()

        # Amihud-style illiquidity proxy: E[|r| / $volume] over a rolling window.
        eps = 1e-12
        amihud = (dret.abs() / (dv + eps)).rolling(window=window, min_periods=minp).mean()
        feats["amihud_1m"] = amihud.resample("ME").last()

        if bool(extended):
            # Flow shock counts: dollar-volume spikes with/without accompanying return shocks.
            if zret is None:
                eps2 = 1e-12
                zret = (dret / (dstd + eps2)).replace([np.inf, -np.inf], np.nan).clip(-20.0, 20.0)
            flow = dvz > 2.0
            flow_cnt = flow.astype(float).rolling(window=window, min_periods=minp).sum()
            flow_only = (flow & (zret.abs() < 1.0)).astype(float).rolling(window=window, min_periods=minp).sum()
            flow_shock = (flow & (zret.abs() > 2.0)).astype(float).rolling(window=window, min_periods=minp).sum()
            feats["dflow_cnt_1m"] = flow_cnt.resample("ME").last()
            feats["dflow_only_cnt_1m"] = flow_only.resample("ME").last()
            feats["dflow_shock_cnt_1m"] = flow_shock.resample("ME").last()

    # Align on month-end and clip extreme outliers to keep ridge stable.
    for k, df in list(feats.items()):
        x = df.copy()
        x = x.replace([np.inf, -np.inf], np.nan)
        feats[k] = x.clip(lower=-10.0, upper=10.0)
    return feats


def _trailing_features(ret_m: pd.DataFrame, close_m: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    # All are aligned on month-end.
    mom_1 = ret_m
    mom_3 = (1.0 + ret_m).rolling(3).apply(np.prod, raw=True) - 1.0
    mom_12 = (1.0 + ret_m).rolling(12).apply(np.prod, raw=True) - 1.0
    vol_3 = ret_m.rolling(3).std(ddof=1) * math.sqrt(12.0)
    vol_12 = ret_m.rolling(12).std(ddof=1) * math.sqrt(12.0)
    sma_12 = close_m.rolling(12).mean()
    trend_12 = (close_m / sma_12 - 1.0).clip(-1.0, 1.0)
    return {
        "mom_1": mom_1,
        "mom_3": mom_3,
        "mom_12": mom_12,
        "vol_3": vol_3,
        "vol_12": vol_12,
        "trend_12": trend_12,
    }


def _price_records_from_daily(panel: pd.DataFrame, ticker: str, end_date: pd.Timestamp, lookback_days: int) -> List[Dict[str, Any]]:
    sub = panel[panel["Instrument"].astype(str) == str(ticker)].copy()
    if sub.empty:
        return []
    sub = sub[sub["Date"] <= end_date].sort_values("Date")
    start = end_date - pd.Timedelta(days=int(lookback_days))
    sub = sub[sub["Date"] >= start]
    out: List[Dict[str, Any]] = []
    for r in sub.itertuples(index=False):
        px = float(getattr(r, "Price_Close"))
        out.append(
            {
                "date": pd.Timestamp(getattr(r, "Date")).isoformat(),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": float(getattr(r, "Volume")) if hasattr(r, "Volume") and getattr(r, "Volume") == getattr(r, "Volume") else None,
            }
        )
    return out


def _insight_feature_vector(insights: List[Any]) -> Dict[str, float]:
    # Insight objects are dataclasses; in some contexts they may already be dicts.
    rows: List[Dict[str, Any]] = []
    for x in insights:
        if isinstance(x, dict):
            rows.append(x)
        else:
            rows.append(getattr(x, "__dict__", {}) or {})

    bullish = 0.0
    bearish = 0.0
    warning = 0.0
    conf_sum = 0.0
    n = 0.0
    risk_conf = 0.0
    anomaly_conf = 0.0
    trend_conf = 0.0
    momentum_conf = 0.0

    for r in rows:
        sig = str(r.get("signal") or "").lower()
        itype = str(r.get("insight_type") or "").lower()
        conf = float(r.get("confidence") or 0.0)
        conf_sum += conf
        n += 1.0
        if sig in {"bullish", "strong_bullish"}:
            bullish += 1.0 * conf
        elif sig in {"bearish", "strong_bearish"}:
            bearish += 1.0 * conf
        elif sig in {"warning"}:
            warning += 1.0 * conf

        if itype == "risk":
            risk_conf += conf
        elif itype == "anomaly":
            anomaly_conf += conf
        elif itype == "trend":
            trend_conf += conf
        elif itype == "momentum":
            momentum_conf += conf

    avg_conf = conf_sum / n if n > 0 else 0.0
    return {
        "ins_bull": float(bullish),
        "ins_bear": float(bearish),
        "ins_warn": float(warning),
        "ins_avg_conf": float(avg_conf),
        "ins_risk": float(risk_conf),
        "ins_anom": float(anomaly_conf),
        "ins_trend": float(trend_conf),
        "ins_momo": float(momentum_conf),
    }


def _load_reddit_sentiment(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Expected columns: Date,Ticker,Mentions,Weight,Sentiment
    rename = {}
    if "Date" in df.columns:
        rename["Date"] = "date"
    if "Ticker" in df.columns:
        rename["Ticker"] = "ticker"
    if "Mentions" in df.columns:
        rename["Mentions"] = "mentions"
    if "Weight" in df.columns:
        rename["Weight"] = "weight"
    if "Sentiment" in df.columns:
        rename["Sentiment"] = "sentiment"
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df["ticker"] = df.get("ticker").astype(str)
    for c in ["mentions", "weight", "sentiment"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date", "ticker"])
    df = df.sort_values(["ticker", "date"])
    return df


def _reddit_window_features(
    df_ticker: Optional[pd.DataFrame],
    dt: pd.Timestamp,
    lookback_days: int,
) -> Dict[str, float]:
    if df_ticker is None or df_ticker.empty:
        return {
            "rd_mentions_sum": 0.0,
            "rd_mentions_days": 0.0,
            "rd_sent_mean": 0.0,
            "rd_sent_wmean": 0.0,
            "rd_sent_std": 0.0,
            "rd_pos_share": 0.0,
            "rd_neg_share": 0.0,
        }
    end = pd.Timestamp(dt)
    start = end - pd.Timedelta(days=int(lookback_days))
    w = df_ticker[(df_ticker["date"] > start) & (df_ticker["date"] <= end)]
    if w.empty:
        return {
            "rd_mentions_sum": 0.0,
            "rd_mentions_days": 0.0,
            "rd_sent_mean": 0.0,
            "rd_sent_wmean": 0.0,
            "rd_sent_std": 0.0,
            "rd_pos_share": 0.0,
            "rd_neg_share": 0.0,
        }

    mentions = w["mentions"] if "mentions" in w.columns else pd.Series(1.0, index=w.index)
    sentiment = w["sentiment"] if "sentiment" in w.columns else pd.Series(0.0, index=w.index)
    weight = w["weight"] if "weight" in w.columns else mentions
    weight = weight.fillna(0.0)
    sentiment = sentiment.fillna(0.0)

    wsum = float(weight.sum())
    wmean = float((sentiment * weight).sum() / wsum) if wsum > 0 else float(sentiment.mean())
    n = float(len(w))
    pos = float((sentiment > 0).sum())
    neg = float((sentiment < 0).sum())
    return {
        "rd_mentions_sum": float(mentions.fillna(0.0).sum()),
        "rd_mentions_days": float(n),
        "rd_sent_mean": float(sentiment.mean()) if n > 0 else 0.0,
        "rd_sent_wmean": float(wmean) if n > 0 else 0.0,
        "rd_sent_std": float(sentiment.std(ddof=0)) if n > 1 else 0.0,
        "rd_pos_share": float(pos / n) if n > 0 else 0.0,
        "rd_neg_share": float(neg / n) if n > 0 else 0.0,
    }


def _load_sec_events(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Expected columns: Date,Ticker,Form
    rename = {}
    if "Date" in df.columns:
        rename["Date"] = "date"
    if "Ticker" in df.columns:
        rename["Ticker"] = "ticker"
    if "Form" in df.columns:
        rename["Form"] = "form"
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df["ticker"] = df.get("ticker").astype(str).str.upper()
    df["form"] = df.get("form").astype(str).str.upper()
    df = df.dropna(subset=["date", "ticker", "form"]).copy()
    df["date"] = df["date"].dt.normalize()
    df = df.sort_values(["ticker", "date"])
    return df


def _load_manual_events(path: Path) -> pd.DataFrame:
    """
    Manual event feed for injecting external context (e.g., "MSCI debacle") without live news access.

    CSV columns (minimum):
      - Date (or date): YYYY-MM-DD
      - Score (or score): float in [-1, +1] (negative = risk-off, positive = risk-on)
    Optional:
      - Tickers (or tickers): semicolon-separated tickers the event applies to, blank = global
      - Event (or event): string label
      - Horizon_Days (or horizon_days): how long the event should be considered "active"
    """
    df = pd.read_csv(path)
    rename = {}
    if "Date" in df.columns:
        rename["Date"] = "date"
    if "Score" in df.columns:
        rename["Score"] = "score"
    if "Tickers" in df.columns:
        rename["Tickers"] = "tickers"
    if "Event" in df.columns:
        rename["Event"] = "event"
    if "Horizon_Days" in df.columns:
        rename["Horizon_Days"] = "horizon_days"
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df["score"] = pd.to_numeric(df.get("score"), errors="coerce")
    if "horizon_days" in df.columns:
        df["horizon_days"] = pd.to_numeric(df.get("horizon_days"), errors="coerce").fillna(0.0)
    else:
        df["horizon_days"] = 0.0
    df["tickers"] = df.get("tickers").fillna("").astype(str) if "tickers" in df.columns else ""
    df["event"] = df.get("event").fillna("").astype(str) if "event" in df.columns else ""
    df = df.dropna(subset=["date", "score"]).copy()
    df = df.sort_values("date")
    return df


def _manual_event_features(
    manual_events: Optional[pd.DataFrame],
    dt: pd.Timestamp,
    instrument: str,
) -> Dict[str, float]:
    if manual_events is None or manual_events.empty:
        return {"man_evt_score": 0.0, "man_evt_active": 0.0, "man_evt_ticker_active": 0.0}

    dtn = pd.Timestamp(dt).normalize()
    inst = str(instrument).upper()

    # Active events: event_date <= dt <= event_date + horizon_days (or same day if horizon_days=0).
    ev = manual_events.copy()
    ev["end_date"] = ev["date"] + pd.to_timedelta(ev["horizon_days"].astype(float), unit="D")
    active = ev[(ev["date"] <= dtn) & (ev["end_date"] >= dtn)]
    if active.empty:
        return {"man_evt_score": 0.0, "man_evt_active": 0.0, "man_evt_ticker_active": 0.0}

    # Score: sum of active scores, clipped.
    score = float(np.clip(float(active["score"].sum()), -1.0, 1.0))

    # Global-active if any active event has blank tickers.
    global_active = bool((active["tickers"].astype(str).str.strip() == "").any())

    # Ticker-active if any active event lists this instrument.
    tick_active = False
    for raw in active["tickers"].astype(str).tolist():
        raw = raw.strip()
        if not raw:
            continue
        toks = [t.strip().upper() for t in raw.split(";") if t.strip()]
        if inst in set(toks):
            tick_active = True
            break

    return {
        "man_evt_score": float(score),
        "man_evt_active": float(1.0 if global_active else 0.0),
        "man_evt_ticker_active": float(1.0 if tick_active else 0.0),
    }


def _sec_window_features(
    df_ticker: Optional[pd.DataFrame],
    dt: pd.Timestamp,
    *,
    lookback_days: int,
    half_life_days: int,
) -> Dict[str, float]:
    if df_ticker is None or df_ticker.empty:
        return {
            "sec_any_cnt": 0.0,
            "sec_8k_cnt": 0.0,
            "sec_10q_cnt": 0.0,
            "sec_10k_cnt": 0.0,
            "sec_days_since": float(lookback_days),
            "sec_decay_score": 0.0,
        }

    end = pd.Timestamp(dt).normalize()
    start = end - pd.Timedelta(days=int(lookback_days))
    w = df_ticker[(df_ticker["date"] > start) & (df_ticker["date"] <= end)]
    if w.empty:
        return {
            "sec_any_cnt": 0.0,
            "sec_8k_cnt": 0.0,
            "sec_10q_cnt": 0.0,
            "sec_10k_cnt": 0.0,
            "sec_days_since": float(lookback_days),
            "sec_decay_score": 0.0,
        }

    forms = w["form"].astype(str).str.upper()
    c8 = float((forms == "8-K").sum())
    c10q = float((forms == "10-Q").sum())
    c10k = float((forms == "10-K").sum())

    last_dt = pd.to_datetime(w["date"].max(), errors="coerce")
    if pd.isna(last_dt):
        days_since = float(lookback_days)
    else:
        days_since = float((end - pd.Timestamp(last_dt).normalize()).days)
        days_since = float(np.clip(days_since, 0.0, float(lookback_days)))

    half_life_days = int(max(1, half_life_days))
    lam = math.log(2.0) / float(half_life_days)
    base_w = {"8-K": 1.0, "10-Q": 0.6, "10-K": 0.8}
    ddays = (end - pd.to_datetime(w["date"], errors="coerce").dt.normalize()).dt.days.astype(float)
    ddays = ddays.replace([np.inf, -np.inf], np.nan).fillna(float(lookback_days))
    weights = forms.map(base_w).fillna(0.5).astype(float)
    decay = np.exp(-lam * ddays.to_numpy(dtype=float))
    score = float(np.sum(decay * weights.to_numpy(dtype=float)))

    return {
        "sec_any_cnt": float(len(w)),
        "sec_8k_cnt": c8,
        "sec_10q_cnt": c10q,
        "sec_10k_cnt": c10k,
        "sec_days_since": float(days_since),
        "sec_decay_score": float(score),
    }


def build_feature_panel(
    panel: pd.DataFrame,
    close_d: pd.DataFrame,
    volume_d: Optional[pd.DataFrame],
    close_m: pd.DataFrame,
    ret_m: pd.DataFrame,
    *,
    lookback_days: int,
    use_insights: bool,
    reddit_sentiment: Optional[pd.DataFrame] = None,
    reddit_lookback_days: int = 30,
    sec_events: Optional[pd.DataFrame] = None,
    sec_lookback_days: int = 365,
    sec_half_life_days: int = 45,
    event_proxy: bool = True,
    event_proxy_extended: bool = False,
    event_lookback_days: int = 21,
    volz_days: int = 60,
    manual_events: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    feats = _trailing_features(ret_m, close_m)
    if bool(event_proxy):
        feats.update(
            _daily_event_proxy_features(
                close_d,
                volume_d,
                lookback_days=int(event_lookback_days),
                volz_days=int(volz_days),
                extended=bool(event_proxy_extended),
            )
        )
    idx = close_m.index
    instruments = list(close_m.columns)

    engine = InsightsEngine() if use_insights else None
    cache: Dict[Tuple[str, str], Dict[str, float]] = {}
    reddit_by_ticker: Dict[str, pd.DataFrame] = {}
    if reddit_sentiment is not None and not reddit_sentiment.empty:
        for t, df_t in reddit_sentiment.groupby("ticker", sort=False):
            reddit_by_ticker[str(t)] = df_t.sort_values("date")
    sec_by_ticker: Dict[str, pd.DataFrame] = {}
    if sec_events is not None and not sec_events.empty:
        for t, df_t in sec_events.groupby("ticker", sort=False):
            sec_by_ticker[str(t)] = df_t.sort_values("date")

    rows: List[Dict[str, Any]] = []
    for dt in idx:
        for inst in instruments:
            if pd.isna(close_m.at[dt, inst]):
                continue
            r: Dict[str, Any] = {"date": dt, "instrument": inst}
            for k, df in feats.items():
                v = df.at[dt, inst] if (dt in df.index and inst in df.columns) else np.nan
                r[k] = float(v) if pd.notna(v) else np.nan

            if use_insights and engine is not None:
                key = (str(inst), str(pd.Timestamp(dt).date()))
                if key not in cache:
                    price_recs = _price_records_from_daily(panel, inst, pd.Timestamp(dt), lookback_days)
                    if price_recs:
                        try:
                            ins = asyncio.run(
                                engine.generate_all_insights(ticker=inst, price_data=price_recs, quote_data=None)
                            )
                            cache[key] = _insight_feature_vector(ins)
                        except Exception:
                            cache[key] = _insight_feature_vector([])
                    else:
                        cache[key] = _insight_feature_vector([])
                r.update(cache[key])

            if reddit_by_ticker:
                r.update(_reddit_window_features(reddit_by_ticker.get(str(inst)), pd.Timestamp(dt), int(reddit_lookback_days)))

            if sec_by_ticker:
                r.update(
                    _sec_window_features(
                        sec_by_ticker.get(str(inst).upper()),
                        pd.Timestamp(dt),
                        lookback_days=int(sec_lookback_days),
                        half_life_days=int(sec_half_life_days),
                    )
                )

            # Manual events: injected external context (global or ticker-specific).
            r.update(_manual_event_features(manual_events, pd.Timestamp(dt), str(inst)))

            rows.append(r)

    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    return out


def walkforward_backtest(
    features: pd.DataFrame,
    ret_m: pd.DataFrame,
    *,
    benchmark: str,
    train_months: int,
    top_n: int,
    max_weight: float,
    cash_ticker: Optional[str],
    cost_bps: float,
    lam_grid: List[float],
    min_assets: int,
    target_vol: float,
    vol_lookback: int,
    max_gross: float,
    allow_leverage: bool,
    regime_filter: bool,
    regime_window: int,
    regime_off_gross: float,
    base: str,
    alpha_mode: str,
    ic_months: int,
    alpha_tstat_scale: float,
    auto_params: bool,
    policy_window: int,
    corr_filter: bool,
    corr_threshold: float,
    corr_lookback: int,
    risk_budget: bool,
    max_turnover: float,
    pf_dd_threshold: float,
    pf_dd_floor_gross: float,
    min_cash_weight: float = 0.05,
    max_crypto_gross: float = 0.60,
    cb_dd_trigger: float = 0.12,
    cb_alpha_trigger: float = -0.02,
    cb_alpha_window: int = 3,
    cb_cooldown_months: int = 2,
    cb_floor_gross: float = 0.35,
    glidepath: bool,
    build_max_dd: float,
    coast_max_dd: float,
    coast_multiple: float,
    cppi_mult: float,
    decay_half_life: float = 0.0,
    feature_screen: bool = False,
    lambda_ensemble: bool = False,
) -> Dict[str, Any]:
    # Build target next-month returns.
    # Keep stack() call pandas-version compatible (dropna kw can fail in newer versions).
    ret_long = ret_m.stack().rename("ret").reset_index()
    # Normalize column names from the stack output.
    cols = list(ret_long.columns)
    if len(cols) >= 2:
        ret_long = ret_long.rename(columns={cols[0]: "date", cols[1]: "instrument"})
    ret_long["date"] = pd.to_datetime(ret_long["date"], errors="coerce")
    ret_long = ret_long.dropna(subset=["date", "instrument"])
    ret_long = ret_long.sort_values(["instrument", "date"])
    ret_long["ret_fwd_1m"] = ret_long.groupby("instrument")["ret"].shift(-1)

    df = features.merge(ret_long[["date", "instrument", "ret_fwd_1m"]], on=["date", "instrument"], how="left")
    df = df.dropna(subset=["ret_fwd_1m"])

    feature_cols = [c for c in df.columns if c not in {"date", "instrument", "ret_fwd_1m"}]
    feature_cols = [c for c in feature_cols if df[c].notna().mean() > 0.2]

    bench_ret = ret_m[benchmark].copy() if benchmark in ret_m.columns else None
    if regime_filter:
        if bench_ret is None:
            raise ValueError(f"Benchmark {benchmark} not found for regime filter.")
        if int(regime_window) < 3:
            raise ValueError("--regime-window must be >= 3 months")
        bench_trailing = (1.0 + bench_ret.fillna(0.0)).rolling(int(regime_window)).apply(np.prod, raw=True) - 1.0
    else:
        bench_trailing = None

    dates = sorted(df["date"].unique())
    if len(dates) < train_months + 6:
        raise ValueError("Not enough monthly data for the requested train window.")

    positions: List[pd.Series] = []
    port_rets: List[Tuple[pd.Timestamp, float]] = []
    used_lams: List[Tuple[pd.Timestamp, float]] = []
    alpha_scales: List[Tuple[pd.Timestamp, float]] = []
    last_coef_pair: Optional[Tuple[List[str], np.ndarray]] = None

    prev_w = None
    realized: List[float] = []
    realized_dates: List[pd.Timestamp] = []
    equity_live = 1.0
    peak_live = 1.0
    coast_reached = False
    cb_cooldown = 0

    # For adaptive policy, use trailing benchmark returns available at each dt.
    bench_ret = ret_m[benchmark].copy() if benchmark in ret_m.columns else None
    if bench_ret is None:
        raise ValueError(f"Benchmark {benchmark} not found in panel.")

    chosen_params: List[Tuple[pd.Timestamp, Dict[str, Any]]] = []
    oos_ics: List[float] = []
    prev_pred: Optional[pd.Series] = None  # instrument-indexed predictions from prior month
    for i in range(train_months, len(dates) - 1):
        dt = pd.Timestamp(dates[i])
        train_start = pd.Timestamp(dates[i - train_months])
        train = df[(df["date"] >= train_start) & (df["date"] < dt)].copy()
        test_raw = df[df["date"] == dt].copy()
        test = test_raw.copy()

        # Optional adaptive parameters based on trailing benchmark regime.
        local_top_n = int(top_n)
        local_max_weight = float(max_weight)
        local_target_vol = float(target_vol)
        local_regime_off_gross = float(regime_off_gross)
        local_alpha_tstat_scale = float(alpha_tstat_scale)
        local_min_cash_weight = float(min_cash_weight)
        local_max_crypto_gross = float(max_crypto_gross)
        local_cb_dd_trigger = float(cb_dd_trigger)
        local_cb_alpha_trigger = float(cb_alpha_trigger)
        local_cb_alpha_window = int(cb_alpha_window)
        local_cb_cooldown_months = int(cb_cooldown_months)
        local_cb_floor_gross = float(cb_floor_gross)
        if auto_params:
            base_params = StrategyParams(
                target_vol=float(local_target_vol),
                top_n=int(local_top_n),
                max_weight=float(local_max_weight),
                regime_off_gross=float(local_regime_off_gross),
                alpha_tstat_scale=float(local_alpha_tstat_scale),
                min_cash_weight=float(local_min_cash_weight),
                max_crypto_gross=float(local_max_crypto_gross),
                cb_dd_trigger=float(local_cb_dd_trigger),
                cb_alpha_trigger=float(local_cb_alpha_trigger),
                cb_alpha_window=int(local_cb_alpha_window),
                cb_cooldown_months=int(local_cb_cooldown_months),
                cb_floor_gross=float(local_cb_floor_gross),
            )
            metrics = compute_regime_metrics(bench_ret, asof=dt, window_months=int(policy_window))
            tuned = policy_params(base_params, metrics)
            local_top_n = int(tuned.top_n)
            local_max_weight = float(tuned.max_weight)
            local_target_vol = float(tuned.target_vol)
            local_regime_off_gross = float(tuned.regime_off_gross)
            local_alpha_tstat_scale = float(tuned.alpha_tstat_scale)
            local_min_cash_weight = float(tuned.min_cash_weight)
            local_max_crypto_gross = float(tuned.max_crypto_gross)
            local_cb_dd_trigger = float(tuned.cb_dd_trigger)
            local_cb_alpha_trigger = float(tuned.cb_alpha_trigger)
            local_cb_alpha_window = int(tuned.cb_alpha_window)
            local_cb_cooldown_months = int(tuned.cb_cooldown_months)
            local_cb_floor_gross = float(tuned.cb_floor_gross)
            chosen_params.append(
                (
                    dt,
                    {
                        "date": str(dt.date()),
                        "metrics": metrics.__dict__ if metrics is not None else None,
                        "params": tuned.to_dict(),
                    },
                )
            )

        # Optional feature screening: drop features with negative trailing IC.
        active_fcols = list(feature_cols)
        if feature_screen:
            active_fcols = _screen_features_by_ic(train, feature_cols, min_assets, ic_months=max(6, ic_months))

        # Cross-sectional standardization by month (within train and test separately).
        train = _standardize_cross_section_by_date(train, active_fcols)
        test = _standardize_cross_section(test, active_fcols)

        # Filter to complete rows.
        train = train.dropna(subset=active_fcols + ["ret_fwd_1m"])
        test = test.dropna(subset=active_fcols)

        if test["instrument"].nunique() < min_assets:
            continue

        X = train[active_fcols].to_numpy(dtype=float)
        y = train["ret_fwd_1m"].to_numpy(dtype=float)
        X = np.column_stack([np.ones(len(X)), X])
        Xt = np.column_stack([np.ones(len(test)), test[active_fcols].to_numpy(dtype=float)])

        # Exponential decay weighting: recent observations count more.
        sample_w = _exp_decay_weights(len(y), float(decay_half_life)) if float(decay_half_life) > 0 else None

        if lambda_ensemble:
            # IC-weighted blend of predictions from multiple lambdas.
            dates_train = sorted(train["date"].unique())
            split = int(len(dates_train) * 0.75)
            cv_tr = train[train["date"].isin(dates_train[:split])]
            cv_val = train[train["date"].isin(dates_train[split:])]
            if cv_tr.empty or cv_val.empty:
                best_lam = _cv_select_lambda(train, active_fcols, lam_grid, min_assets)
                beta = _ridge_fit(X, y, lam=float(best_lam), w=sample_w)
                pred = Xt @ beta
            else:
                pred = _cv_ensemble_predict(X, y, Xt, lam_grid, cv_tr, cv_val, active_fcols, min_assets, w=sample_w)
                best_lam = -1.0  # sentinel: ensemble used
        else:
            # Lambda selection via chronological CV on training window only (no lookahead).
            best_lam = _cv_select_lambda(train, active_fcols, lam_grid, min_assets)
            beta = _ridge_fit(X, y, lam=float(best_lam), w=sample_w)
            pred = Xt @ beta
            # Track the most recent fit so callers can introspect feature
            # importance (β excluding the intercept).
            last_coef_pair = (list(active_fcols), np.asarray(beta[1:], dtype=float))

        test = test.assign(pred=pred)
        test = test.sort_values("pred", ascending=False)

        # Trailing monthly returns up to dt (for corr filter / risk budgeting).
        trailing = ret_m.loc[ret_m.index <= dt].copy()
        if int(corr_lookback) > 0:
            trailing = trailing.tail(int(corr_lookback))

        # Build alpha picks: top-N predicted, long-only. If all <=0, go cash.
        ranked = test.copy()
        ranked["instrument"] = ranked["instrument"].astype(str)
        picks = ranked.head(int(local_top_n)).copy()
        if corr_filter:
            chosen = _corr_filter_select(
                ranked,
                already=[],
                want=int(local_top_n),
                trailing_returns=trailing,
                corr_threshold=float(corr_threshold),
            )
            if chosen:
                picks = ranked[ranked["instrument"].isin(chosen)].copy()
                # preserve ranking order
                picks["__rank"] = picks["instrument"].map({k: j for j, k in enumerate(chosen)})
                picks = picks.sort_values("__rank").drop(columns=["__rank"])

        if picks["pred"].max() <= 0 and cash_ticker:
            w = pd.Series(0.0, index=ret_m.columns, dtype=float)
            if cash_ticker in w.index:
                w.loc[cash_ticker] = 1.0
        else:
            w = pd.Series(0.0, index=ret_m.columns, dtype=float)
            if risk_budget:
                wi = _risk_budget_weights(picks, pred_col="pred", trailing_returns=trailing, vol_lookback=max(3, int(vol_lookback)))
                for inst, weight in wi.items():
                    if inst in w.index:
                        w.loc[inst] = float(weight)
            else:
                denom = float(np.abs(picks["pred"]).sum()) or 1.0
                for _, row in picks.iterrows():
                    w.loc[str(row["instrument"])] = float(row["pred"]) / denom
                w = w.clip(lower=0.0)
                if w.sum() > 0:
                    w = w / w.sum()
            # Cap weights then renormalize.
            w = w.clip(upper=float(local_max_weight))
            if w.sum() > 0:
                w = w / w.sum()
            else:
                # Fallback
                if cash_ticker and cash_ticker in w.index:
                    w.loc[cash_ticker] = 1.0

        # Base weights computed from raw (unstandardized) features as a robustness sleeve.
        w_base = pd.Series(0.0, index=ret_m.columns, dtype=float)
        if str(base) == "benchmark":
            if benchmark in w_base.index:
                w_base.loc[benchmark] = 1.0
            elif cash_ticker and cash_ticker in w_base.index:
                w_base.loc[cash_ticker] = 1.0
        elif str(base) == "trend":
            if not {"trend_12", "vol_12"}.issubset(set(test_raw.columns)):
                if cash_ticker and cash_ticker in w_base.index:
                    w_base.loc[cash_ticker] = 1.0
            else:
                sub = test_raw.copy()
                sub["instrument"] = sub["instrument"].astype(str)
                sub["trend_12"] = pd.to_numeric(sub["trend_12"], errors="coerce")
                sub["vol_12"] = pd.to_numeric(sub["vol_12"], errors="coerce")
                sub = sub.dropna(subset=["instrument", "trend_12", "vol_12"])
                sub = sub[(sub["vol_12"] > 1e-8) & (sub["trend_12"] > 0.0)]
                if not sub.empty:
                    inv = 1.0 / sub["vol_12"].to_numpy(dtype=float)
                    cap = float(np.percentile(inv, 95)) if len(inv) > 3 else float(inv.max())
                    inv = np.clip(inv, 0.0, cap)
                    weights = inv / (float(inv.sum()) or 1.0)
                    for inst, wi in zip(sub["instrument"].to_list(), weights):
                        if inst in w_base.index:
                            w_base.loc[inst] = float(wi)
                    w_base = w_base.clip(upper=float(local_max_weight))
                    if w_base.sum() > 0:
                        w_base = w_base / w_base.sum()
                if w_base.sum() <= 0 and cash_ticker and cash_ticker in w_base.index:
                    w_base.loc[cash_ticker] = 1.0
        else:
            if cash_ticker and cash_ticker in w_base.index:
                w_base.loc[cash_ticker] = 1.0

        # Alpha confidence scaling using training IC t-stat (uses only training data).
        alpha_scale = 1.0
        if str(alpha_mode) == "ic_tstat":
            Xtr = np.column_stack([np.ones(len(train)), train[feature_cols].to_numpy(dtype=float)])
            pred_tr = Xtr @ beta
            tr = train.assign(pred=pred_tr)
            ics: List[float] = []
            for _, g in tr.groupby("date"):
                g = g.dropna(subset=["pred", "ret_fwd_1m"])
                if g["instrument"].nunique() < min_assets:
                    continue
                ic = _spearman_ic(g["pred"].to_numpy(dtype=float), g["ret_fwd_1m"].to_numpy(dtype=float))
                if np.isfinite(ic):
                    ics.append(float(ic))
            if len(ics) >= max(6, int(ic_months)):
                ics = ics[-int(ic_months) :]
                mu = float(np.mean(ics))
                sd = float(np.std(ics, ddof=1))
                tstat = float(mu / (sd / math.sqrt(len(ics)))) if sd > 1e-12 else (float("inf") if mu > 0 else float("-inf"))
                alpha_scale = float(_clamp(tstat / float(local_alpha_tstat_scale), 0.0, 1.0))
            else:
                alpha_scale = 0.0

        # OOS IC decay gate: if recent out-of-sample IC is negative, halve confidence.
        if len(oos_ics) >= 6:
            oos_mu = float(np.mean(oos_ics[-12:]))
            if oos_mu < 0:
                alpha_scale *= 0.5

        # Blend alpha with base; keep long-only and sum-to-one.
        w = (float(alpha_scale) * w) + ((1.0 - float(alpha_scale)) * w_base)
        w = w.clip(lower=0.0)
        if w.sum() > 0:
            w = w / w.sum()
        w = w.clip(upper=float(local_max_weight))
        if w.sum() > 0:
            w = w / w.sum()
        elif cash_ticker and cash_ticker in w.index:
            w.loc[cash_ticker] = 1.0

        # Turnover cap: shrink changes vs prev_w (portfolio mgmt).
        if prev_w is not None and float(max_turnover) < 1.0:
            prev = prev_w.reindex(w.index).fillna(0.0)
            target = w.fillna(0.0)
            t = _turnover(prev, target)
            if t > float(max_turnover) and t > 1e-12:
                frac = float(max_turnover) / float(t)
                w = (prev + frac * (target - prev)).clip(lower=0.0)
                if w.sum() > 0:
                    w = w / w.sum()

        # Optional vol targeting / gross exposure cap (risk overlay that sits on top of alpha weights).
        # Scale down into cash to target volatility while staying long-only.
        if float(local_target_vol) > 0 and cash_ticker and cash_ticker in w.index:
            # Estimate vol from realized portfolio returns (monthly), annualized.
            if len(realized) >= max(3, int(vol_lookback)):
                window = np.asarray(realized[-int(vol_lookback):], dtype=float)
                est = float(np.std(window, ddof=1) * math.sqrt(12.0))
            else:
                est = float(local_target_vol)
            est = max(est, 1e-6)
            scale = float(_clamp(float(local_target_vol) / est, 0.0, float(max_gross)))
            risky = w.drop(labels=[cash_ticker]).copy()
            w.loc[risky.index] = risky * scale
            w.loc[cash_ticker] = float(1.0 - w.drop(labels=[cash_ticker]).sum())
            if not allow_leverage:
                w.loc[cash_ticker] = float(_clamp(float(w.loc[cash_ticker]), 0.0, 1.0))

        # Portfolio drawdown throttle: if live equity drawdown exceeds threshold, cap gross.
        if float(pf_dd_threshold) > 0 and float(pf_dd_floor_gross) < 1.0 and cash_ticker and cash_ticker in w.index:
            dd_now = (equity_live / peak_live - 1.0) if peak_live > 0 else 0.0
            if dd_now <= -abs(float(pf_dd_threshold)):
                rg = float(_clamp(float(pf_dd_floor_gross), 0.0, 1.0))
                risky = w.drop(labels=[cash_ticker]).copy()
                w.loc[risky.index] = risky * rg
                w.loc[cash_ticker] = float(1.0 - w.drop(labels=[cash_ticker]).sum())
                if not allow_leverage:
                    w.loc[cash_ticker] = float(_clamp(float(w.loc[cash_ticker]), 0.0, 1.0))

        # CPPI glidepath: objective max drawdown budget.
        # Build phase uses build_max_dd; after reaching coast_multiple equity, use coast_max_dd.
        if glidepath and cash_ticker and cash_ticker in w.index:
            dd_budget = float(coast_max_dd) if coast_reached else float(build_max_dd)
            dd_budget = float(_clamp(abs(dd_budget), 0.01, 0.90))
            floor = float(peak_live * (1.0 - dd_budget))
            cushion = float(max(0.0, equity_live - floor))
            risky_target = float(_clamp(float(cppi_mult) * (cushion / max(equity_live, 1e-12)), 0.0, float(max_gross)))

            risky = w.drop(labels=[cash_ticker]).copy()
            risky_sum = float(risky.sum())
            if risky_sum > 0:
                scale = float(risky_target / risky_sum)
                w.loc[risky.index] = risky * scale
            else:
                w.loc[risky.index] = 0.0
            w.loc[cash_ticker] = float(1.0 - w.drop(labels=[cash_ticker]).sum())
            if not allow_leverage:
                w.loc[cash_ticker] = float(_clamp(float(w.loc[cash_ticker]), 0.0, 1.0))

        # Optional regime filter: if benchmark trailing return is negative, throttle risky gross.
        if regime_filter and cash_ticker and cash_ticker in w.index and bench_trailing is not None:
            trailing = float(bench_trailing.reindex([dt]).iloc[0]) if dt in bench_trailing.index else float("nan")
            risk_on = bool(np.isfinite(trailing) and trailing > 0.0)
            if not risk_on:
                rg = float(_clamp(float(local_regime_off_gross), 0.0, 1.0))
                risky = w.drop(labels=[cash_ticker]).copy()
                w.loc[risky.index] = risky * rg
                w.loc[cash_ticker] = float(1.0 - w.drop(labels=[cash_ticker]).sum())
                if not allow_leverage:
                    w.loc[cash_ticker] = float(_clamp(float(w.loc[cash_ticker]), 0.0, 1.0))

        # Circuit breaker: temporary de-risk if DD or trailing active return breaches threshold.
        if cash_ticker and cash_ticker in w.index:
            dd_now = (equity_live / peak_live - 1.0) if peak_live > 0 else 0.0
            active_trailing = float("nan")
            if int(local_cb_alpha_window) > 0 and len(realized) >= int(local_cb_alpha_window):
                recent_r = np.asarray(realized[-int(local_cb_alpha_window):], dtype=float)
                recent_d = pd.DatetimeIndex(realized_dates[-int(local_cb_alpha_window):])
                recent_b = bench_ret.reindex(recent_d).fillna(0.0).to_numpy(dtype=float)
                active_trailing = float(np.mean(recent_r - recent_b))

            cb_on = False
            if cb_cooldown > 0:
                cb_on = True
                cb_cooldown -= 1
            else:
                dd_triggered = bool(float(local_cb_dd_trigger) > 0 and dd_now <= -abs(float(local_cb_dd_trigger)))
                alpha_triggered = bool(
                    int(local_cb_alpha_window) > 0
                    and np.isfinite(active_trailing)
                    and active_trailing <= float(local_cb_alpha_trigger)
                )
                if dd_triggered or alpha_triggered:
                    cb_on = True
                    cb_cooldown = max(0, int(local_cb_cooldown_months) - 1)

            if cb_on:
                rg = float(_clamp(float(local_cb_floor_gross), 0.0, 1.0))
                risky = w.drop(labels=[cash_ticker]).copy()
                w.loc[risky.index] = risky * rg
                w.loc[cash_ticker] = float(1.0 - w.drop(labels=[cash_ticker]).sum())
                if not allow_leverage:
                    w.loc[cash_ticker] = float(_clamp(float(w.loc[cash_ticker]), 0.0, 1.0))

        # Hard sleeve controls after all overlays.
        w = _apply_sleeve_controls(
            w,
            cash_ticker=cash_ticker,
            min_cash_weight=float(local_min_cash_weight),
            max_crypto_gross=float(local_max_crypto_gross),
        )

        # Next-month realized return for dt+1
        dt_next = pd.Timestamp(dates[i + 1])
        r_next = ret_m.loc[dt_next].reindex(w.index).fillna(0.0)

        # OOS IC: compare PREVIOUS month's prediction with its now-realized returns.
        if prev_pred is not None:
            common = prev_pred.index.intersection(r_next.index)
            if len(common) >= min_assets:
                oos_ic = _spearman_ic(
                    prev_pred.reindex(common).to_numpy(dtype=float),
                    r_next.reindex(common).to_numpy(dtype=float),
                )
                if np.isfinite(oos_ic):
                    oos_ics.append(float(oos_ic))

        # Store current predictions for next iteration's OOS IC.
        prev_pred = pd.Series(
            dict(zip(test["instrument"].astype(str), test["pred"].astype(float))),
        )

        gross = float((w * r_next).sum())

        # Turnover costs
        if prev_w is None:
            tcost = 0.0
        else:
            t = _turnover(prev_w, w)
            tcost = (float(cost_bps) / 10000.0) * t
        net = gross - tcost

        equity_live = float(equity_live * (1.0 + net))
        peak_live = float(max(peak_live, equity_live))
        if (not coast_reached) and float(coast_multiple) > 1.0 and equity_live >= float(coast_multiple):
            coast_reached = True

        positions.append(w.rename(dt_next))
        port_rets.append((dt_next, net))
        realized.append(float(net))
        realized_dates.append(pd.Timestamp(dt_next))
        used_lams.append((dt, float(best_lam)))
        alpha_scales.append((dt_next, float(alpha_scale)))
        prev_w = w

    ret_series = pd.Series({d: r for d, r in port_rets}).sort_index()
    equity = (1.0 + ret_series).cumprod()
    pos = pd.DataFrame(positions).fillna(0.0)

    perf = {
        "start": str(ret_series.index.min().date()) if not ret_series.empty else None,
        "end": str(ret_series.index.max().date()) if not ret_series.empty else None,
        "n_months": int(len(ret_series)),
        "cagr": _cagr(equity),
        "sharpe": _sharpe(ret_series),
        "max_drawdown": _max_drawdown(equity),
        "final_equity": float(equity.iloc[-1]) if not equity.empty else float("nan"),
        "feature_cols": feature_cols,
        "lambda_grid": lam_grid,
        "benchmark": benchmark,
        "regime_filter": bool(regime_filter),
        "regime_window": int(regime_window),
        "regime_off_gross": float(regime_off_gross),
    }
    last_coef: Optional[pd.Series] = None
    if last_coef_pair is not None:
        cols, coefs = last_coef_pair
        if len(cols) == len(coefs):
            last_coef = pd.Series(coefs, index=cols)

    return {
        "perf": perf,
        "returns": ret_series,
        "equity": equity,
        "positions": pos,
        "lambdas": pd.Series({d: lam for d, lam in used_lams}).sort_index(),
        "alpha_scale": pd.Series({d: s for d, s in alpha_scales}).sort_index(),
        "chosen_params": pd.DataFrame([p for _, p in chosen_params]) if chosen_params else pd.DataFrame(),
        "last_coef": last_coef,
    }


def _benchmark_series(ret_m: pd.DataFrame, benchmark: str) -> pd.Series:
    if benchmark not in ret_m.columns:
        raise ValueError(f"Benchmark {benchmark} not found in panel.")
    return ret_m[benchmark].dropna()


def _risk_matched_benchmark(
    bench_ret: pd.Series,
    *,
    target_vol: float,
    vol_lookback: int,
    max_gross: float,
    regime_filter: bool,
    regime_window: int,
    regime_off_gross: float,
) -> pd.Series:
    """
    Risk-match benchmark using the same *style* of overlays:
    - volatility targeting to a target annual vol (via realized monthly returns)
    - optional regime throttle based on trailing benchmark return

    This is for fairer Sharpe comparisons when the strategy uses overlays.
    """
    r = bench_ret.dropna().copy()
    if r.empty:
        return r

    bench_trailing = None
    if regime_filter:
        bench_trailing = (1.0 + r.fillna(0.0)).rolling(int(regime_window)).apply(np.prod, raw=True) - 1.0

    out = []
    realized = []
    for dt in r.index:
        gross = float(r.loc[dt])
        scale = 1.0

        if float(target_vol) > 0:
            if len(realized) >= max(3, int(vol_lookback)):
                window = np.asarray(realized[-int(vol_lookback):], dtype=float)
                est = float(np.std(window, ddof=1) * np.sqrt(12.0))
            else:
                est = float(target_vol)
            est = max(est, 1e-6)
            scale = float(_clamp(float(target_vol) / est, 0.0, float(max_gross)))

        if bench_trailing is not None:
            trailing = float(bench_trailing.reindex([dt]).iloc[0]) if dt in bench_trailing.index else float("nan")
            if not (np.isfinite(trailing) and trailing > 0.0):
                scale *= float(_clamp(float(regime_off_gross), 0.0, 1.0))

        net = float(scale) * gross
        out.append((dt, net))
        realized.append(net)

    return pd.Series({d: v for d, v in out}).sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward alpha runner (ridge + optional insights features).")
    ap.add_argument("--panel", type=Path, default=SR_ROOT / "data_lake" / "yfinance_multi_asset_core_10y.csv")
    ap.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_insights_walkforward")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--universe", choices=["all", "equities", "crypto"], default="all")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--cash-ticker", type=str, default="BIL")
    ap.add_argument("--train-months", type=int, default=48)
    ap.add_argument("--top-n", type=int, default=4)
    ap.add_argument("--max-weight", type=float, default=0.40)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--lam-grid", nargs="*", type=float, default=[0.01, 0.1, 1.0, 10.0, 100.0])
    ap.add_argument("--min-assets", type=int, default=4)
    ap.add_argument("--lookback-days", type=int, default=365)
    ap.add_argument("--use-insights", action="store_true", help="Add InsightEngine-derived features.")
    ap.add_argument(
        "--reddit-sentiment",
        type=Path,
        default=None,
        help="Optional CSV like data_lake/reddit_sentiment_panel_more.csv to add sentiment features.",
    )
    ap.add_argument("--reddit-lookback-days", type=int, default=30, help="Trailing days of Reddit signals per month-end.")
    ap.add_argument(
        "--sec-events",
        type=Path,
        default=None,
        help="Optional CSV like data_lake/sec/filing_events_nasdaq100.csv (Date,Ticker,Form) to add filing features.",
    )
    ap.add_argument("--sec-lookback-days", type=int, default=365, help="Trailing days of SEC filings per month-end.")
    ap.add_argument("--sec-half-life-days", type=int, default=45, help="Half-life (days) for SEC filing decay score.")
    ap.add_argument("--event-proxy", action="store_true", help="Add price/volume event-proxy features (jump/volume shock).")
    ap.add_argument(
        "--event-proxy-extended",
        action="store_true",
        help="Experimental: add extra flow/shock proxies (often noisy; off by default).",
    )
    ap.add_argument("--event-lookback-days", type=int, default=21, help="Trailing days window for event-proxy features.")
    ap.add_argument("--volz-days", type=int, default=60, help="Trailing days window for volume z-score.")
    ap.add_argument(
        "--manual-events",
        type=Path,
        default=None,
        help="Optional CSV to inject external context (Date,Score[,Tickers,Event,Horizon_Days]).",
    )
    ap.add_argument(
        "--feature-cache",
        type=Path,
        default=None,
        help="Optional path to cache computed feature panel (parquet/csv). Speeds up sweeps.",
    )
    ap.add_argument("--target-vol", type=float, default=0.0, help="Annualized vol target (0 disables).")
    ap.add_argument("--vol-lookback", type=int, default=12, help="Months of realized returns for vol estimate.")
    ap.add_argument("--max-gross", type=float, default=1.0, help="Max risky gross exposure when vol targeting.")
    ap.add_argument("--allow-leverage", action="store_true", help="Allow negative cash weight when vol targeting scales > 1.")
    ap.add_argument("--regime-filter", action="store_true", help="If benchmark trailing return is negative, throttle risky gross.")
    ap.add_argument("--regime-window", type=int, default=12, help="Months used for benchmark trailing return.")
    ap.add_argument("--regime-off-gross", type=float, default=0.0, help="Risky gross exposure when regime is off.")
    ap.add_argument("--base", choices=["cash", "benchmark", "trend"], default="trend", help="Base sleeve when alpha is weak.")
    ap.add_argument("--alpha-mode", choices=["fixed", "ic_tstat"], default="ic_tstat", help="How to scale alpha vs base.")
    ap.add_argument("--ic-months", type=int, default=12, help="Months of IC history for alpha-mode ic_tstat.")
    ap.add_argument("--alpha-tstat-scale", type=float, default=2.0, help="t-stat value mapping to alpha_scale=1.0")
    ap.add_argument("--auto-params", action="store_true", help="Auto-adjust key params using a mechanical regime policy.")
    ap.add_argument("--policy-window", type=int, default=12, help="Months used for regime policy features.")
    ap.add_argument("--corr-filter", action="store_true", help="Diversify picks by limiting pairwise correlations.")
    ap.add_argument("--corr-threshold", type=float, default=0.85, help="Max abs corr allowed among selected picks.")
    ap.add_argument("--corr-lookback", type=int, default=12, help="Months used for correlation estimates.")
    ap.add_argument("--risk-budget", action="store_true", help="Size positions by signal / trailing vol (risk budgeting).")
    ap.add_argument("--max-turnover", type=float, default=1.0, help="Max monthly turnover (0-1).")
    ap.add_argument("--pf-dd-threshold", type=float, default=0.0, help="Portfolio DD threshold (e.g., 0.2). 0 disables.")
    ap.add_argument("--pf-dd-floor-gross", type=float, default=0.5, help="Risky gross when DD breached.")
    ap.add_argument(
        "--control-profile",
        choices=["custom", "off", "growth", "balanced", "defensive"],
        default="custom",
        help="Named control preset. If not custom, overrides manual sleeve/circuit knobs.",
    )
    ap.add_argument("--print-control-profiles", action="store_true", help="Print built-in control profiles as JSON and exit.")
    ap.add_argument("--min-cash-weight", type=float, default=0.05, help="Minimum cash sleeve weight if cash ticker exists.")
    ap.add_argument("--max-crypto-gross", type=float, default=0.60, help="Maximum aggregate crypto sleeve gross (tickers ending -USD).")
    ap.add_argument("--cb-dd-trigger", type=float, default=0.12, help="Circuit breaker DD trigger; 0 disables DD trigger.")
    ap.add_argument("--cb-alpha-trigger", type=float, default=-0.02, help="Circuit breaker trigger for trailing monthly active return.")
    ap.add_argument("--cb-alpha-window", type=int, default=3, help="Trailing months for circuit-breaker active-return check.")
    ap.add_argument("--cb-cooldown-months", type=int, default=2, help="Months to keep circuit breaker active once triggered.")
    ap.add_argument("--cb-floor-gross", type=float, default=0.35, help="Risky gross cap while circuit breaker is active.")
    ap.add_argument("--glidepath", action="store_true", help="Enable CPPI glidepath (objective drawdown budget).")
    ap.add_argument("--build-max-dd", type=float, default=0.25, help="Max drawdown budget during build phase.")
    ap.add_argument("--coast-max-dd", type=float, default=0.15, help="Max drawdown budget after hitting coast_multiple.")
    ap.add_argument("--coast-multiple", type=float, default=2.0, help="Equity multiple at which to enter coast phase.")
    ap.add_argument("--cppi-mult", type=float, default=3.0, help="CPPI multiplier (aggressiveness).")
    ap.add_argument("--decay-half-life", type=float, default=0.0, help="Training sample exp-decay half-life in months (0 disables).")
    ap.add_argument("--feature-screen", action="store_true", help="Pre-screen features by trailing IC (drop negatives).")
    ap.add_argument("--lambda-ensemble", action="store_true", help="IC-weighted blend of lambdas instead of winner-take-all.")
    args = ap.parse_args()

    if bool(args.print_control_profiles):
        print(profiles_json())
        return 0
    if str(args.control_profile) != "custom":
        apply_profile_to_namespace(args, str(args.control_profile))

    panel = load_panel(args.panel)
    close_d = daily_close_wide(panel)
    volume_d = daily_volume_wide(panel)

    # Universe selection
    cols = list(close_d.columns)
    if args.universe == "crypto":
        keep = [c for c in cols if str(c).endswith("-USD")]
        if args.cash_ticker in cols:
            keep.append(args.cash_ticker)
        close_d = close_d[sorted(set(keep))]
    elif args.universe == "equities":
        keep = [c for c in cols if not str(c).endswith("-USD")]
        close_d = close_d[sorted(set(keep))]

    if args.exclude:
        close_d = close_d[[c for c in close_d.columns if c not in set(args.exclude)]]

    # Synthetic cash support for equity-only panels (e.g., NASDAQ-100 files that don't include BIL).
    if args.cash_ticker and args.cash_ticker not in close_d.columns:
        close_d[str(args.cash_ticker)] = 1.0
        if volume_d is not None:
            volume_d[str(args.cash_ticker)] = 0.0

    close_m, ret_m = monthly_close_and_returns(close_d)

    reddit_df: Optional[pd.DataFrame] = None
    if args.reddit_sentiment:
        p = Path(args.reddit_sentiment)
        if p.exists():
            reddit_df = _load_reddit_sentiment(p)

    sec_df: Optional[pd.DataFrame] = None
    if args.sec_events:
        p = Path(args.sec_events)
        if p.exists():
            sec_df = _load_sec_events(p)

    manual_df: Optional[pd.DataFrame] = None
    if args.manual_events:
        p = Path(args.manual_events)
        if p.exists():
            manual_df = _load_manual_events(p)

    feats: pd.DataFrame
    if args.feature_cache and args.feature_cache.exists():
        if args.feature_cache.suffix.lower() == ".parquet":
            feats = pd.read_parquet(args.feature_cache)
        else:
            feats = pd.read_csv(args.feature_cache, parse_dates=["date"])
    else:
        feats = build_feature_panel(
            panel,
            close_d=close_d,
            volume_d=volume_d,
            close_m=close_m,
            ret_m=ret_m,
            lookback_days=int(args.lookback_days),
            use_insights=bool(args.use_insights),
            reddit_sentiment=reddit_df,
            reddit_lookback_days=int(args.reddit_lookback_days),
            sec_events=sec_df,
            sec_lookback_days=int(args.sec_lookback_days),
            sec_half_life_days=int(args.sec_half_life_days),
            event_proxy=bool(args.event_proxy),
            event_proxy_extended=bool(args.event_proxy_extended),
            event_lookback_days=int(args.event_lookback_days),
            volz_days=int(args.volz_days),
            manual_events=manual_df,
        )
        if args.feature_cache:
            args.feature_cache.parent.mkdir(parents=True, exist_ok=True)
            if args.feature_cache.suffix.lower() == ".parquet":
                feats.to_parquet(args.feature_cache, index=False)
            else:
                feats.to_csv(args.feature_cache, index=False)

    res = walkforward_backtest(
        feats,
        ret_m=ret_m,
        benchmark=str(args.benchmark),
        train_months=int(args.train_months),
        top_n=int(args.top_n),
        max_weight=float(args.max_weight),
        cash_ticker=str(args.cash_ticker) if args.cash_ticker else None,
        cost_bps=float(args.cost_bps),
        lam_grid=[float(x) for x in args.lam_grid],
        min_assets=int(args.min_assets),
        target_vol=float(args.target_vol),
        vol_lookback=int(args.vol_lookback),
        max_gross=float(args.max_gross),
        allow_leverage=bool(args.allow_leverage),
        regime_filter=bool(args.regime_filter),
        regime_window=int(args.regime_window),
        regime_off_gross=float(args.regime_off_gross),
        base=str(args.base),
        alpha_mode=str(args.alpha_mode),
        ic_months=int(args.ic_months),
        alpha_tstat_scale=float(args.alpha_tstat_scale),
        auto_params=bool(args.auto_params),
        policy_window=int(args.policy_window),
        corr_filter=bool(args.corr_filter),
        corr_threshold=float(args.corr_threshold),
        corr_lookback=int(args.corr_lookback),
        risk_budget=bool(args.risk_budget),
        max_turnover=float(args.max_turnover),
        pf_dd_threshold=float(args.pf_dd_threshold),
        pf_dd_floor_gross=float(args.pf_dd_floor_gross),
        min_cash_weight=float(args.min_cash_weight),
        max_crypto_gross=float(args.max_crypto_gross),
        cb_dd_trigger=float(args.cb_dd_trigger),
        cb_alpha_trigger=float(args.cb_alpha_trigger),
        cb_alpha_window=int(args.cb_alpha_window),
        cb_cooldown_months=int(args.cb_cooldown_months),
        cb_floor_gross=float(args.cb_floor_gross),
        glidepath=bool(args.glidepath),
        build_max_dd=float(args.build_max_dd),
        coast_max_dd=float(args.coast_max_dd),
        coast_multiple=float(args.coast_multiple),
        cppi_mult=float(args.cppi_mult),
        decay_half_life=float(args.decay_half_life),
        feature_screen=bool(args.feature_screen),
        lambda_ensemble=bool(args.lambda_ensemble),
    )

    bench_ret = _benchmark_series(ret_m, str(args.benchmark))
    # Align on strategy returns index
    strat_ret = res["returns"].reindex(bench_ret.index).dropna()
    bench_ret = bench_ret.reindex(strat_ret.index).fillna(0.0)
    bench_eq = (1.0 + bench_ret).cumprod()

    perf = dict(res["perf"])
    perf["benchmark"] = {
        "ticker": str(args.benchmark),
        "cagr": _cagr(bench_eq),
        "sharpe": _sharpe(bench_ret),
        "max_drawdown": _max_drawdown(bench_eq),
        "final_equity": float(bench_eq.iloc[-1]) if not bench_eq.empty else float("nan"),
    }

    # Risk-matched benchmark: apply the same overlay style (vol targeting + regime throttle).
    bench_rm = _risk_matched_benchmark(
        bench_ret,
        target_vol=float(args.target_vol),
        vol_lookback=int(args.vol_lookback),
        max_gross=float(args.max_gross),
        regime_filter=bool(args.regime_filter),
        regime_window=int(args.regime_window),
        regime_off_gross=float(args.regime_off_gross),
    )
    bench_rm = bench_rm.reindex(strat_ret.index).fillna(0.0)
    bench_rm_eq = (1.0 + bench_rm).cumprod()
    perf["benchmark_risk_matched"] = {
        "ticker": str(args.benchmark),
        "cagr": _cagr(bench_rm_eq),
        "sharpe": _sharpe(bench_rm),
        "max_drawdown": _max_drawdown(bench_rm_eq),
        "final_equity": float(bench_rm_eq.iloc[-1]) if not bench_rm_eq.empty else float("nan"),
    }

    # Information ratio (monthly)
    active = strat_ret - bench_ret
    perf["information_ratio"] = _sharpe(active)
    perf["active_cagr_diff"] = float(perf["cagr"] - perf["benchmark"]["cagr"])
    perf["active_cagr_diff_risk_matched"] = float(perf["cagr"] - perf["benchmark_risk_matched"]["cagr"])
    perf["controls"] = {
        "control_profile": str(args.control_profile),
        "min_cash_weight": float(args.min_cash_weight),
        "max_crypto_gross": float(args.max_crypto_gross),
        "cb_dd_trigger": float(args.cb_dd_trigger),
        "cb_alpha_trigger": float(args.cb_alpha_trigger),
        "cb_alpha_window": int(args.cb_alpha_window),
        "cb_cooldown_months": int(args.cb_cooldown_months),
        "cb_floor_gross": float(args.cb_floor_gross),
        "auto_params": bool(args.auto_params),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(perf, indent=2) + "\n")
    (args.out_dir / "run_config.json").write_text(json.dumps(_jsonable_args(args), indent=2) + "\n")
    res["equity"].to_csv(args.out_dir / "equity_curve.csv", header=True)
    bench_eq.to_csv(args.out_dir / "benchmark_equity.csv", header=True)
    bench_rm_eq.to_csv(args.out_dir / "benchmark_risk_matched_equity.csv", header=True)
    res["positions"].to_csv(args.out_dir / "positions.csv", index=True)
    res["lambdas"].to_csv(args.out_dir / "lambdas.csv", header=["lambda"])
    res["alpha_scale"].to_csv(args.out_dir / "alpha_scale.csv", header=["alpha_scale"])
    if isinstance(res.get("chosen_params"), pd.DataFrame) and not res["chosen_params"].empty:
        res["chosen_params"].to_csv(args.out_dir / "chosen_params.csv", index=False)

    report = []
    report.append("# Alpha Walk-Forward Report\n\n")
    report.append(f"- universe: `{args.universe}`  \n")
    report.append(f"- use_insights: `{bool(args.use_insights)}`  \n")
    report.append(f"- benchmark: `{args.benchmark}`  \n")
    report.append(f"- train_months: `{args.train_months}`  \n")
    report.append(f"- top_n: `{args.top_n}`  \n")
    report.append(f"- cost_bps: `{args.cost_bps}`  \n\n")
    report.append(f"- control_profile: `{args.control_profile}`  \n")
    report.append(f"- min_cash_weight: `{args.min_cash_weight}`  \n")
    report.append(f"- max_crypto_gross: `{args.max_crypto_gross}`  \n\n")
    report.append("## Performance\n\n")
    report.append("```json\n")
    report.append(json.dumps({k: perf[k] for k in ["start", "end", "n_months", "cagr", "sharpe", "max_drawdown", "information_ratio", "active_cagr_diff"]}, indent=2))
    report.append("\n```\n\n")
    report.append("## Benchmark\n\n")
    report.append("```json\n")
    report.append(json.dumps(perf["benchmark"], indent=2))
    report.append("\n```\n")
    (args.out_dir / "report.md").write_text("".join(report))

    print(json.dumps(perf, indent=2))
    print(f"Saved to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
