#!/usr/bin/env python3
from __future__ import annotations

"""
Grid search for robustness (not single-period cherry-picking).

This script searches over a small set of strategy knobs and scores each config by:
- pass rate: % of sampled windows where strategy Sharpe > benchmark Sharpe
- pass rate (CAGR): % windows where strategy CAGR > benchmark CAGR
- median deltas (Sharpe, CAGR)

Use it to "push" towards stable outperformance rather than a one-off run.
"""

import argparse
import json
import math
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)

from scripts.alpha_insights_walkforward_runner import (  # noqa: E402
    daily_close_wide,
    load_panel,
    monthly_close_and_returns,
    walkforward_backtest,
)
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


def _pick_unique_windows(
    dates: List[pd.Timestamp],
    *,
    window_months: int,
    n_windows: int,
    seed: int,
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    if len(dates) < window_months + 2:
        raise ValueError("Not enough months to sample requested windows.")
    max_start = len(dates) - window_months
    n = int(min(int(n_windows), int(max_start))) if max_start > 0 else 0
    if n <= 0:
        return []
    rng = np.random.default_rng(int(seed))
    starts = rng.choice(np.arange(max_start), size=n, replace=False)
    return [(pd.Timestamp(dates[int(s)]), pd.Timestamp(dates[int(s) + int(window_months) - 1])) for s in list(starts)]


@dataclass(frozen=True)
class GridRow:
    target_vol: float
    regime_off_gross: float
    top_n: int
    max_weight: float
    score: float
    pass_sharpe: float
    pass_cagr: float
    median_sharpe_diff: float
    median_cagr_diff: float
    median_mdd: float


def main() -> int:
    warnings.filterwarnings("ignore", category=FutureWarning)

    ap = argparse.ArgumentParser(description="Robustness grid search for alpha runner knobs.")
    ap.add_argument("--panel", type=Path, default=SR_ROOT / "data_lake" / "yfinance_multi_asset_core_10y.csv")
    ap.add_argument("--feature-cache", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_robustness_grid")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--universe", choices=["all", "equities", "crypto"], default="all")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--cash-ticker", type=str, default="BIL")
    ap.add_argument("--train-months", type=int, default=48)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--lam-grid", nargs="*", type=float, default=[0.1, 1.0, 10.0])
    ap.add_argument("--min-assets", type=int, default=4)
    ap.add_argument("--vol-lookback", type=int, default=12)
    ap.add_argument("--max-gross", type=float, default=1.0)
    ap.add_argument("--allow-leverage", action="store_true")
    ap.add_argument("--regime-filter", action="store_true")
    ap.add_argument("--regime-window", type=int, default=12)
    ap.add_argument("--base", choices=["cash", "benchmark", "trend"], default="trend")
    ap.add_argument("--alpha-mode", choices=["fixed", "ic_tstat"], default="ic_tstat")
    ap.add_argument("--ic-months", type=int, default=12)
    ap.add_argument("--alpha-tstat-scale", type=float, default=2.0)
    ap.add_argument("--auto-params", action="store_true")
    ap.add_argument("--policy-window", type=int, default=12)

    ap.add_argument("--window-months", type=int, default=96)
    ap.add_argument("--n-windows", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)

    ap.add_argument("--grid-target-vol", nargs="*", type=float, default=[0.10, 0.12, 0.15])
    ap.add_argument("--grid-regime-off-gross", nargs="*", type=float, default=[0.0, 0.25, 0.5])
    ap.add_argument("--grid-top-n", nargs="*", type=int, default=[3, 4, 5])
    ap.add_argument("--grid-max-weight", nargs="*", type=float, default=[0.25, 0.40])
    args = ap.parse_args()

    panel = load_panel(args.panel)
    close_d = daily_close_wide(panel)

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

    _, ret_m = monthly_close_and_returns(close_d)

    if args.feature_cache.suffix.lower() == ".parquet":
        feats = pd.read_parquet(args.feature_cache)
    else:
        feats = pd.read_csv(args.feature_cache, parse_dates=["date"])
    feats["date"] = pd.to_datetime(feats["date"], errors="coerce")

    dates = sorted(set(pd.Timestamp(d) for d in feats["date"].dropna().unique()))
    windows = _pick_unique_windows(dates, window_months=int(args.window_months), n_windows=int(args.n_windows), seed=int(args.seed))

    def subset_features(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        f = feats[(feats["date"] >= start) & (feats["date"] <= end)].copy()
        return f

    def subset_ret(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        return ret_m.loc[(ret_m.index >= start) & (ret_m.index <= end)].copy()

    grid_rows: List[GridRow] = []
    run_rows = []
    total = len(args.grid_target_vol) * len(args.grid_regime_off_gross) * len(args.grid_top_n) * len(args.grid_max_weight)
    k = 0
    for target_vol in [float(x) for x in args.grid_target_vol]:
        for regime_off in [float(x) for x in args.grid_regime_off_gross]:
            for top_n in [int(x) for x in args.grid_top_n]:
                for max_weight in [float(x) for x in args.grid_max_weight]:
                    k += 1
                    sharpe_diff = []
                    cagr_diff = []
                    mdds = []
                    pass_sh = 0
                    pass_cg = 0
                    n_ok = 0

                    for (start, end) in windows:
                        f_sub = subset_features(start, end)
                        r_sub = subset_ret(start, end)
                        if len(r_sub.index) < int(args.train_months) + 6:
                            continue
                        res = walkforward_backtest(
                            f_sub,
                            ret_m=r_sub,
                            benchmark=str(args.benchmark),
                            train_months=int(args.train_months),
                            top_n=int(top_n),
                            max_weight=float(max_weight),
                            cash_ticker=str(args.cash_ticker) if args.cash_ticker else None,
                            cost_bps=float(args.cost_bps),
                            lam_grid=[float(x) for x in args.lam_grid],
                            min_assets=int(args.min_assets),
                            target_vol=float(target_vol),
                            vol_lookback=int(args.vol_lookback),
                            max_gross=float(args.max_gross),
                            allow_leverage=bool(args.allow_leverage),
                            regime_filter=bool(args.regime_filter),
                            regime_window=int(args.regime_window),
                            regime_off_gross=float(regime_off),
                            base=str(args.base),
                            alpha_mode=str(args.alpha_mode),
                            ic_months=int(args.ic_months),
                            alpha_tstat_scale=float(args.alpha_tstat_scale),
                            auto_params=bool(args.auto_params),
                            policy_window=int(args.policy_window),
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
                                target_vol=float(target_vol),
                                top_n=int(top_n),
                                max_weight=float(max_weight),
                                regime_off_gross=float(regime_off),
                                alpha_tstat_scale=float(args.alpha_tstat_scale),
                            ),
                        )
                        bench_rm = bench_rm.loc[(bench_rm.index >= start) & (bench_rm.index <= end)]
                        bench_rm_eq = (1.0 + bench_rm.fillna(0.0)).cumprod()
                        bench_rm_perf = {"cagr": _cagr(bench_rm_eq), "sharpe": _sharpe(bench_rm)}

                        # Score vs risk-matched benchmark (fairer if we use vol targeting / regime throttles).
                        sd = float(perf.get("sharpe") or float("nan")) - float(bench_rm_perf["sharpe"])
                        cd = float(perf.get("cagr") or float("nan")) - float(bench_rm_perf["cagr"])
                        mdd = float(perf.get("max_drawdown") or float("nan"))
                        if not (np.isfinite(sd) and np.isfinite(cd) and np.isfinite(mdd)):
                            continue
                        sharpe_diff.append(sd)
                        cagr_diff.append(cd)
                        mdds.append(mdd)
                        pass_sh += int(sd > 0)
                        pass_cg += int(cd > 0)
                        n_ok += 1
                        run_rows.append(
                            {
                                "target_vol": float(target_vol),
                                "regime_off_gross": float(regime_off),
                                "top_n": int(top_n),
                                "max_weight": float(max_weight),
                                "start": str(pd.Timestamp(start).date()),
                                "end": str(pd.Timestamp(end).date()),
                                "sharpe": float(perf.get("sharpe")),
                                "cagr": float(perf.get("cagr")),
                                "max_drawdown": float(perf.get("max_drawdown")),
                                "bench_sharpe": float(bench["sharpe"]),
                                "bench_cagr": float(bench["cagr"]),
                                "bench_rm_sharpe": float(bench_rm_perf["sharpe"]),
                                "bench_rm_cagr": float(bench_rm_perf["cagr"]),
                            }
                        )

                    if n_ok <= 0:
                        continue
                    pass_sharpe = float(pass_sh) / float(n_ok)
                    pass_cagr = float(pass_cg) / float(n_ok)
                    med_sh = float(np.median(sharpe_diff))
                    med_cg = float(np.median(cagr_diff))
                    med_mdd = float(np.median(mdds))

                    # Score: emphasize consistent beating (pass rates) and positive median deltas, but penalize deep drawdowns.
                    score = (
                        2.0 * pass_sharpe
                        + 2.0 * pass_cagr
                        + 1.0 * med_sh
                        + 3.0 * med_cg
                        + 0.5 * float(-med_mdd)  # smaller drawdown is better -> (-mdd) larger is better
                    )

                    grid_rows.append(
                        GridRow(
                            target_vol=float(target_vol),
                            regime_off_gross=float(regime_off),
                            top_n=int(top_n),
                            max_weight=float(max_weight),
                            score=float(score),
                            pass_sharpe=float(pass_sharpe),
                            pass_cagr=float(pass_cagr),
                            median_sharpe_diff=float(med_sh),
                            median_cagr_diff=float(med_cg),
                            median_mdd=float(med_mdd),
                        )
                    )
                    print(
                        f"[{k}/{total}] tv={target_vol:.2f} off={regime_off:.2f} top={top_n} mw={max_weight:.2f} "
                        f"score={score:.3f} pass_sh={pass_sharpe:.2f} pass_cg={pass_cagr:.2f} "
                        f"med_dS={med_sh:.3f} med_dC={med_cg:.3f} med_mdd={med_mdd:.3f}"
                    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(r) for r in grid_rows]).sort_values("score", ascending=False)
    df.to_csv(args.out_dir / "grid_scores.csv", index=False)
    pd.DataFrame(run_rows).to_csv(args.out_dir / "grid_window_details.csv", index=False)
    (args.out_dir / "grid_windows.json").write_text(json.dumps([{"start": str(a.date()), "end": str(b.date())} for a, b in windows], indent=2))

    best = df.head(1).to_dict(orient="records")[0] if not df.empty else {}
    (args.out_dir / "best.json").write_text(json.dumps(best, indent=2))
    print(f"Saved to {args.out_dir}")
    if best:
        print("Best:", json.dumps(best, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
