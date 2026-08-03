#!/usr/bin/env python3
from __future__ import annotations

"""
Robustness harness for the walk-forward alpha runner.

What it does
- Runs the alpha strategy over many random contiguous time windows (different periods).
- Optionally runs "shuffle" tests that destroy the feature->return relationship to estimate a
  chance-performance baseline (null distribution).

This helps answer: "Is this working only because of the specific 2020-2025 period?"

Notes
- This is still historical backtesting; it does NOT guarantee future performance.
- Shuffling is a statistical sanity check, not a tradable simulation.
"""

import argparse
import json
import math
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)

# Reuse the strategy implementation.
from scripts.alpha_insights_walkforward_runner import (  # noqa: E402
    daily_close_wide,
    load_panel,
    monthly_close_and_returns,
    walkforward_backtest,
)
from src.strategy.control_profiles import apply_profile_to_namespace, profiles_json  # noqa: E402
from src.strategy.regime_policy import StrategyParams, compute_regime_metrics, policy_params  # noqa: E402


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


def _benchmark_perf(ret_m: pd.DataFrame, benchmark: str, start: pd.Timestamp, end: pd.Timestamp) -> Dict[str, Any]:
    if benchmark not in ret_m.columns:
        raise ValueError(f"Benchmark {benchmark} not found in panel.")
    r = ret_m[benchmark].loc[(ret_m.index >= start) & (ret_m.index <= end)].dropna()
    eq = (1.0 + r).cumprod()
    return {
        "ticker": benchmark,
        "cagr": _cagr(eq),
        "sharpe": _sharpe(r),
        "max_drawdown": _max_drawdown(eq),
        "final_equity": float(eq.iloc[-1]) if not eq.empty else float("nan"),
        "n_months": int(len(r)),
    }


def _risk_matched_benchmark_series(
    bench_ret: pd.Series,
    *,
    vol_lookback: int,
    max_gross: float,
    regime_filter: bool,
    regime_window: int,
    auto_params: bool,
    policy_window: int,
    base_params: StrategyParams,
) -> pd.Series:
    """
    Risk-match the benchmark using the same overlay style (vol targeting + optional regime throttle).
    If auto_params is enabled, adjust parameters per-date using the same regime policy.
    """
    r = bench_ret.dropna().copy()
    if r.empty:
        return r

    trailing = None
    if regime_filter:
        trailing = (1.0 + r.fillna(0.0)).rolling(int(regime_window)).apply(np.prod, raw=True) - 1.0

    realized: List[float] = []
    out: List[Tuple[pd.Timestamp, float]] = []
    for dt in r.index:
        p = base_params
        if auto_params:
            metrics = compute_regime_metrics(r, asof=pd.Timestamp(dt), window_months=int(policy_window))
            p = policy_params(base_params, metrics)

        scale = 1.0
        if float(p.target_vol) > 0:
            if len(realized) >= max(3, int(vol_lookback)):
                window = np.asarray(realized[-int(vol_lookback) :], dtype=float)
                est = float(np.std(window, ddof=1) * np.sqrt(12.0))
            else:
                est = float(p.target_vol)
            est = max(est, 1e-6)
            scale = float(max(0.0, min(float(p.target_vol) / est, float(max_gross))))

        if trailing is not None:
            tr = float(trailing.reindex([dt]).iloc[0]) if dt in trailing.index else float("nan")
            if not (np.isfinite(tr) and tr > 0.0):
                scale *= float(max(0.0, min(float(p.regime_off_gross), 1.0)))

        net = float(scale) * float(r.loc[dt])
        out.append((pd.Timestamp(dt), net))
        realized.append(net)

    return pd.Series({d: v for d, v in out}).sort_index()


def _subset_features(features: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    f = features.copy()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    return f[(f["date"] >= start) & (f["date"] <= end)].copy()


def _subset_ret_m(ret_m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return ret_m.loc[(ret_m.index >= start) & (ret_m.index <= end)].copy()


def _pick_random_windows(
    dates: List[pd.Timestamp],
    *,
    window_months: int,
    n_windows: int,
    seed: int,
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    if len(dates) < window_months + 2:
        raise ValueError("Not enough months to sample requested windows.")
    rng = np.random.default_rng(int(seed))
    max_start = len(dates) - window_months
    n = int(min(int(n_windows), int(max_start))) if max_start > 0 else 0
    if n <= 0:
        return []
    starts = rng.choice(np.arange(max_start), size=n, replace=False)
    windows: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    for s in list(starts):
        a = pd.Timestamp(dates[int(s)])
        b = pd.Timestamp(dates[int(s) + int(window_months) - 1])
        windows.append((a, b))
    return windows


def _shuffle_ret_m(ret_m: pd.DataFrame, *, mode: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    out = ret_m.copy()
    if mode == "months":
        perm = rng.permutation(len(out.index))
        out.index = out.index.take(perm)
        out = out.sort_index()
        return out
    if mode == "xs":
        # For each month: shuffle returns across instruments, preserving monthly distribution.
        for dt in out.index:
            row = out.loc[dt].to_numpy(dtype=float)
            perm = rng.permutation(len(row))
            out.loc[dt] = row[perm]
        return out
    raise ValueError(f"Unknown shuffle mode: {mode}")


def _shuffle_features_xs(features: pd.DataFrame, *, seed: int) -> pd.DataFrame:
    """
    Shuffle the mapping between features and instruments *within each date*.

    This keeps:
      - the time-series of returns intact (including benchmark/cash)
      - the cross-sectional distribution of features each month
    but destroys:
      - any true relationship between an instrument's features and its future returns
    """
    rng = np.random.default_rng(int(seed))
    f = features.copy()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    out = []
    for _, g in f.groupby("date", dropna=False):
        g = g.copy()
        inst = g["instrument"].astype(str).to_numpy()
        g["instrument"] = rng.permutation(inst)
        out.append(g)
    return pd.concat(out, ignore_index=True)


@dataclass(frozen=True)
class WindowResult:
    start: str
    end: str
    n_months: int
    cagr: float
    sharpe: float
    max_drawdown: float
    final_equity: float
    bench_cagr: float
    bench_sharpe: float
    bench_max_drawdown: float
    bench_rm_cagr: float
    bench_rm_sharpe: float
    bench_rm_max_drawdown: float
    sharpe_diff_rm: float
    cagr_diff_rm: float
    information_ratio: float
    active_cagr_diff: float


def main() -> int:
    warnings.filterwarnings("ignore", category=FutureWarning)

    ap = argparse.ArgumentParser(description="Robustness sweep: random windows + shuffle null tests.")
    ap.add_argument("--panel", type=Path, default=SR_ROOT / "data_lake" / "yfinance_multi_asset_core_10y.csv")
    ap.add_argument("--feature-cache", type=Path, required=True, help="Precomputed features parquet/csv from alpha runner.")
    ap.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_robustness")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--universe", choices=["all", "equities", "crypto"], default="all")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--cash-ticker", type=str, default="BIL")
    ap.add_argument("--train-months", type=int, default=48)
    ap.add_argument("--top-n", type=int, default=4)
    ap.add_argument("--max-weight", type=float, default=0.40)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--lam-grid", nargs="*", type=float, default=[0.1, 1.0, 10.0])
    ap.add_argument("--min-assets", type=int, default=4)
    ap.add_argument("--target-vol", type=float, default=0.12)
    ap.add_argument("--vol-lookback", type=int, default=12)
    ap.add_argument("--max-gross", type=float, default=1.0)
    ap.add_argument("--allow-leverage", action="store_true")
    ap.add_argument("--regime-filter", action="store_true")
    ap.add_argument("--regime-window", type=int, default=12)
    ap.add_argument("--regime-off-gross", type=float, default=0.0)
    ap.add_argument("--base", choices=["cash", "benchmark", "trend"], default="trend")
    ap.add_argument("--alpha-mode", choices=["fixed", "ic_tstat"], default="ic_tstat")
    ap.add_argument("--ic-months", type=int, default=12)
    ap.add_argument("--alpha-tstat-scale", type=float, default=2.0)
    ap.add_argument("--auto-params", action="store_true")
    ap.add_argument("--policy-window", type=int, default=12)
    ap.add_argument("--corr-filter", action="store_true")
    ap.add_argument("--corr-threshold", type=float, default=0.85)
    ap.add_argument("--corr-lookback", type=int, default=12)
    ap.add_argument("--risk-budget", action="store_true")
    ap.add_argument("--max-turnover", type=float, default=1.0)
    ap.add_argument("--pf-dd-threshold", type=float, default=0.0)
    ap.add_argument("--pf-dd-floor-gross", type=float, default=0.5)
    ap.add_argument(
        "--control-profile",
        choices=["custom", "off", "growth", "balanced", "defensive"],
        default="custom",
        help="Named control preset. If not custom, overrides manual sleeve/circuit knobs.",
    )
    ap.add_argument("--print-control-profiles", action="store_true", help="Print built-in control profiles as JSON and exit.")
    ap.add_argument("--min-cash-weight", type=float, default=0.05)
    ap.add_argument("--max-crypto-gross", type=float, default=0.60)
    ap.add_argument("--cb-dd-trigger", type=float, default=0.12)
    ap.add_argument("--cb-alpha-trigger", type=float, default=-0.02)
    ap.add_argument("--cb-alpha-window", type=int, default=3)
    ap.add_argument("--cb-cooldown-months", type=int, default=2)
    ap.add_argument("--cb-floor-gross", type=float, default=0.35)
    ap.add_argument("--glidepath", action="store_true")
    ap.add_argument("--build-max-dd", type=float, default=0.25)
    ap.add_argument("--coast-max-dd", type=float, default=0.15)
    ap.add_argument("--coast-multiple", type=float, default=2.0)
    ap.add_argument("--cppi-mult", type=float, default=3.0)

    # Window sweep controls
    ap.add_argument("--window-months", type=int, default=72, help="Length of each sampled window.")
    ap.add_argument("--n-windows", type=int, default=20, help="Number of random windows to evaluate.")
    ap.add_argument("--seed", type=int, default=42)

    # Shuffle/null controls
    ap.add_argument("--shuffle-mode", choices=["none", "months", "xs", "feat_xs"], default="xs")
    ap.add_argument("--n-shuffles", type=int, default=50)
    args = ap.parse_args()

    if bool(args.print_control_profiles):
        print(profiles_json())
        return 0
    if str(args.control_profile) != "custom":
        apply_profile_to_namespace(args, str(args.control_profile))

    panel = load_panel(args.panel)
    close_d = daily_close_wide(panel)

    # Universe selection (match alpha runner).
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

    close_m, ret_m = monthly_close_and_returns(close_d)

    if args.feature_cache.suffix.lower() == ".parquet":
        feats = pd.read_parquet(args.feature_cache)
    else:
        feats = pd.read_csv(args.feature_cache, parse_dates=["date"])

    # Month-end dates we can evaluate (use features dates intersection).
    feats["date"] = pd.to_datetime(feats["date"], errors="coerce")
    dates = sorted(set(pd.Timestamp(d) for d in feats["date"].dropna().unique()))

    windows = _pick_random_windows(
        dates,
        window_months=int(args.window_months),
        n_windows=int(args.n_windows),
        seed=int(args.seed),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[WindowResult] = []
    for idx, (start, end) in enumerate(windows, start=1):
        f_sub = _subset_features(feats, start, end)
        r_sub = _subset_ret_m(ret_m, start, end)
        if len(r_sub.index) < int(args.train_months) + 6:
            continue

        res = walkforward_backtest(
            f_sub,
            ret_m=r_sub,
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
        )

        perf = res["perf"]
        bench = _benchmark_perf(r_sub, str(args.benchmark), start, end)
        bench_series = r_sub[str(args.benchmark)].dropna()
        bench_rm = _risk_matched_benchmark_series(
            bench_series,
            vol_lookback=int(args.vol_lookback),
            max_gross=float(args.max_gross),
            regime_filter=bool(args.regime_filter),
            regime_window=int(args.regime_window),
            auto_params=bool(args.auto_params),
            policy_window=int(args.policy_window),
            base_params=StrategyParams(
                target_vol=float(args.target_vol),
                top_n=int(args.top_n),
                max_weight=float(args.max_weight),
                regime_off_gross=float(args.regime_off_gross),
                alpha_tstat_scale=float(args.alpha_tstat_scale),
                min_cash_weight=float(args.min_cash_weight),
                max_crypto_gross=float(args.max_crypto_gross),
                cb_dd_trigger=float(args.cb_dd_trigger),
                cb_alpha_trigger=float(args.cb_alpha_trigger),
                cb_alpha_window=int(args.cb_alpha_window),
                cb_cooldown_months=int(args.cb_cooldown_months),
                cb_floor_gross=float(args.cb_floor_gross),
            ),
        )
        bench_rm = bench_rm.loc[(bench_rm.index >= start) & (bench_rm.index <= end)]
        bench_rm_eq = (1.0 + bench_rm.fillna(0.0)).cumprod()
        bench_rm_cagr = _cagr(bench_rm_eq)
        bench_rm_sharpe = _sharpe(bench_rm)
        bench_rm_mdd = _max_drawdown(bench_rm_eq)
        wr = WindowResult(
            start=str(pd.Timestamp(start).date()),
            end=str(pd.Timestamp(end).date()),
            n_months=int(perf.get("n_months") or 0),
            cagr=float(perf.get("cagr") or float("nan")),
            sharpe=float(perf.get("sharpe") or float("nan")),
            max_drawdown=float(perf.get("max_drawdown") or float("nan")),
            final_equity=float(perf.get("final_equity") or float("nan")),
            bench_cagr=float(bench["cagr"]),
            bench_sharpe=float(bench["sharpe"]),
            bench_max_drawdown=float(bench["max_drawdown"]),
            bench_rm_cagr=float(bench_rm_cagr),
            bench_rm_sharpe=float(bench_rm_sharpe),
            bench_rm_max_drawdown=float(bench_rm_mdd),
            sharpe_diff_rm=float(float(perf.get("sharpe") or float("nan")) - float(bench_rm_sharpe)),
            cagr_diff_rm=float(float(perf.get("cagr") or float("nan")) - float(bench_rm_cagr)),
            information_ratio=float(perf.get("information_ratio") or float("nan")),
            active_cagr_diff=float(perf.get("active_cagr_diff") or float("nan")),
        )
        rows.append(wr)
        print(
            f"[{idx}/{len(windows)}] window {wr.start}..{wr.end} sharpe={wr.sharpe:.3f} cagr={wr.cagr:.3f} "
            f"(rm_dS={wr.sharpe_diff_rm:.3f}, rm_dC={wr.cagr_diff_rm:.3f})"
        )

    dfw = pd.DataFrame([asdict(r) for r in rows])
    dfw.to_csv(args.out_dir / "windows.csv", index=False)

    # Shuffle/null tests: keep features fixed but destroy the timeline relation in returns.
    null_rows = []
    if args.shuffle_mode != "none" and int(args.n_shuffles) > 0:
        for j in range(int(args.n_shuffles)):
            # Use full overlapping date range of the feature set (so it’s comparable to “full run”).
            start = pd.Timestamp(min(dates))
            end = pd.Timestamp(max(dates))
            r_sub = _subset_ret_m(ret_m, start, end)
            if str(args.shuffle_mode) == "feat_xs":
                f_sub = _shuffle_features_xs(_subset_features(feats, start, end), seed=int(args.seed) + 10_000 + j)
            else:
                r_shuf = _shuffle_ret_m(ret_m, mode=str(args.shuffle_mode), seed=int(args.seed) + 10_000 + j)
                f_sub = _subset_features(feats, start, end)
                r_sub = _subset_ret_m(r_shuf, start, end)
            if len(r_sub.index) < int(args.train_months) + 6:
                continue
            res = walkforward_backtest(
                f_sub,
                ret_m=r_sub,
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
            )
            p = res["perf"]
            null_rows.append(
                {
                    "shuffle_idx": int(j),
                    "shuffle_mode": str(args.shuffle_mode),
                    "cagr": float(p.get("cagr") or float("nan")),
                    "sharpe": float(p.get("sharpe") or float("nan")),
                    "max_drawdown": float(p.get("max_drawdown") or float("nan")),
                    "information_ratio": float(p.get("information_ratio") or float("nan")),
                }
            )
            if (j + 1) % 10 == 0:
                print(f"[shuffle {j+1}/{int(args.n_shuffles)}] done")

    dfn = pd.DataFrame(null_rows)
    if not dfn.empty:
        dfn.to_csv(args.out_dir / "null_shuffles.csv", index=False)

    def _summ_stats(x: pd.Series) -> Dict[str, Any]:
        x = pd.to_numeric(x, errors="coerce").dropna()
        if x.empty:
            return {}
        return {
            "mean": float(x.mean()),
            "median": float(x.median()),
            "p10": float(x.quantile(0.10)),
            "p25": float(x.quantile(0.25)),
            "p75": float(x.quantile(0.75)),
            "p90": float(x.quantile(0.90)),
            "n": int(len(x)),
        }

    summary = {
        "config": {
            "benchmark": str(args.benchmark),
            "universe": str(args.universe),
            "train_months": int(args.train_months),
            "top_n": int(args.top_n),
            "max_weight": float(args.max_weight),
            "cost_bps": float(args.cost_bps),
            "target_vol": float(args.target_vol),
            "allow_leverage": bool(args.allow_leverage),
            "regime_filter": bool(args.regime_filter),
            "regime_window": int(args.regime_window),
            "regime_off_gross": float(args.regime_off_gross),
            "base": str(args.base),
            "alpha_mode": str(args.alpha_mode),
            "ic_months": int(args.ic_months),
            "alpha_tstat_scale": float(args.alpha_tstat_scale),
            "auto_params": bool(args.auto_params),
            "policy_window": int(args.policy_window),
            "corr_filter": bool(args.corr_filter),
            "corr_threshold": float(args.corr_threshold),
            "corr_lookback": int(args.corr_lookback),
            "risk_budget": bool(args.risk_budget),
            "max_turnover": float(args.max_turnover),
            "pf_dd_threshold": float(args.pf_dd_threshold),
            "pf_dd_floor_gross": float(args.pf_dd_floor_gross),
            "control_profile": str(args.control_profile),
            "min_cash_weight": float(args.min_cash_weight),
            "max_crypto_gross": float(args.max_crypto_gross),
            "cb_dd_trigger": float(args.cb_dd_trigger),
            "cb_alpha_trigger": float(args.cb_alpha_trigger),
            "cb_alpha_window": int(args.cb_alpha_window),
            "cb_cooldown_months": int(args.cb_cooldown_months),
            "cb_floor_gross": float(args.cb_floor_gross),
            "glidepath": bool(args.glidepath),
            "build_max_dd": float(args.build_max_dd),
            "coast_max_dd": float(args.coast_max_dd),
            "coast_multiple": float(args.coast_multiple),
            "cppi_mult": float(args.cppi_mult),
            "window_months": int(args.window_months),
            "n_windows": int(args.n_windows),
            "seed": int(args.seed),
            "shuffle_mode": str(args.shuffle_mode),
            "n_shuffles": int(args.n_shuffles),
        },
        "windows": {
            "cagr": _summ_stats(dfw["cagr"]) if not dfw.empty else {},
            "sharpe": _summ_stats(dfw["sharpe"]) if not dfw.empty else {},
            "max_drawdown": _summ_stats(dfw["max_drawdown"]) if not dfw.empty else {},
            "information_ratio": _summ_stats(dfw["information_ratio"]) if not dfw.empty else {},
            "active_cagr_diff": _summ_stats(dfw["active_cagr_diff"]) if not dfw.empty else {},
            "bench_cagr": _summ_stats(dfw["bench_cagr"]) if not dfw.empty else {},
            "bench_sharpe": _summ_stats(dfw["bench_sharpe"]) if not dfw.empty else {},
            "bench_rm_cagr": _summ_stats(dfw["bench_rm_cagr"]) if not dfw.empty else {},
            "bench_rm_sharpe": _summ_stats(dfw["bench_rm_sharpe"]) if not dfw.empty else {},
            "sharpe_diff_rm": _summ_stats(dfw["sharpe_diff_rm"]) if not dfw.empty else {},
            "cagr_diff_rm": _summ_stats(dfw["cagr_diff_rm"]) if not dfw.empty else {},
        },
        "null": {
            "cagr": _summ_stats(dfn["cagr"]) if not dfn.empty else {},
            "sharpe": _summ_stats(dfn["sharpe"]) if not dfn.empty else {},
            "max_drawdown": _summ_stats(dfn["max_drawdown"]) if not dfn.empty else {},
            "information_ratio": _summ_stats(dfn["information_ratio"]) if not dfn.empty else {},
        },
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Saved to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
