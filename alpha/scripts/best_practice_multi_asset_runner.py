#!/usr/bin/env python3
"""
Best-practice protocol runner for multi-asset trend.

Design goals:
- Small grid / quick runs (small universe)
- Walk-forward folds
- Costed, risk-matched benchmark (same overlays on SPY)

This is a research harness, not a promise of future returns.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _grid(params: Dict[str, List[Any]]) -> Iterable[Dict[str, Any]]:
    keys = list(params.keys())
    for values in itertools.product(*[params[k] for k in keys]):
        yield dict(zip(keys, values))


def _split_months(idx: pd.DatetimeIndex, *, train_months: int, val_months: int, test_months: int, folds: int) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    idx = pd.DatetimeIndex(idx).sort_values()
    n = len(idx)
    if n < train_months + val_months + test_months + 6:
        return []
    max_folds = int((n - val_months - train_months) // test_months)
    folds = max(1, min(int(folds), max_folds))
    boundaries = []
    for k in range(folds):
        test_end_i = n - 1 - k * test_months
        test_start_i = n - (k + 1) * test_months
        val_end_i = test_start_i - 1
        val_start_i = val_end_i - val_months + 1
        if val_start_i < train_months:
            break
        boundaries.append((idx[val_start_i], idx[test_start_i], idx[test_end_i]))
    return list(reversed(boundaries))


def _info_ratio(excess: pd.Series) -> float:
    excess = excess.dropna()
    if len(excess) < 12:
        return 0.0
    ann = float(excess.mean() * 12.0)
    vol = float(excess.std(ddof=0) * np.sqrt(12.0))
    return float(ann / vol) if vol > 0 else 0.0


def _factor_proxy_panel(pnl_index: pd.DatetimeIndex, prices_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Simple factor proxies from the panel itself (monthly).
    This is not a substitute for FF factors; it's a robust offline diagnostic.
    """
    px_m = prices_daily.resample("ME").last()
    r = px_m.pct_change().fillna(0.0)
    cols = []
    for c in ["SPY", "IEF", "TLT", "GLD", "DBC", "BTC-USD"]:
        if c in r.columns:
            cols.append(c)
    X = r[cols] if cols else pd.DataFrame(index=r.index)
    X = X.reindex(pnl_index).fillna(0.0)
    return X


def main() -> int:
    p = argparse.ArgumentParser(description="Best-practice multi-asset trend protocol runner.")
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
    _bmod = _ilu.module_from_spec(_bspec)
    _bspec.loader.exec_module(_bmod)
    sr_root = _bmod.bootstrap_repo_paths(__file__)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=sr_root / "backtests/outputs/multi_asset_best_practice")
    p.add_argument("--assets-file", type=Path, default=sr_root / "config/tickers_multi_asset_core.txt")
    p.add_argument("--cash-proxy", type=str, default="BIL")
    p.add_argument("--benchmark", type=str, default="SPY")
    p.add_argument("--bond-benchmark", type=str, default="IEF")
    p.add_argument("--portfolio-usd", type=float, default=250000.0)
    p.add_argument("--min-median-dollar-volume", type=float, default=10_000_000.0)

    # Walk-forward
    p.add_argument("--train-months", type=int, default=36)
    p.add_argument("--val-months", type=int, default=12)
    p.add_argument("--test-months", type=int, default=12)
    p.add_argument("--folds", type=int, default=3)

    # Grid (kept small)
    p.add_argument("--lookback-months", type=int, nargs="+", default=[12])
    p.add_argument("--ma-months", type=int, nargs="+", default=[8, 10])
    p.add_argument("--ensemble-lookbacks", type=int, nargs="*", default=[], help="If provided, use these lookbacks as an ensemble (overrides grid lookback).")
    p.add_argument("--ensemble-mas", type=int, nargs="*", default=[], help="If provided, use these MA windows as an ensemble (overrides grid MA).")
    p.add_argument("--vol-months", type=int, nargs="+", default=[6, 12])
    p.add_argument("--target-vol", type=float, nargs="+", default=[0.10, 0.12])
    p.add_argument("--dd-throttle", type=float, nargs="+", default=[0.15, 0.20])
    p.add_argument("--dd-floor-exposure", type=float, nargs="+", default=[0.25, 0.50])
    p.add_argument("--max-weight", type=float, nargs="+", default=[0.35])
    p.add_argument("--cost-bps", type=float, nargs="+", default=[2.5, 5.0])
    p.add_argument("--signal-threshold", type=float, nargs="+", default=[0.0, 0.25])
    p.add_argument("--signal-smooth-months", type=int, nargs="+", default=[1, 3])
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--side", choices=["long_only", "long_short"], default="long_only")
    p.add_argument("--alpha-hac-lags", type=int, default=3)
    p.add_argument("--log-every", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    mod = _load_module(sr_root / "scripts/multi_asset_trend_runner.py", "multi_asset_trend_runner")
    alpha_mod = _load_module(sr_root / "scripts/alpha_regression.py", "alpha_regression")

    prices, vols = mod.load_prices(args.panel)
    assets = [
        l.strip()
        for l in args.assets_file.read_text().splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assets = sorted(dict.fromkeys(assets))

    # Establish month index with a baseline run.
    base = mod.run_trend_backtest(
        prices_daily=prices,
        volumes_daily=vols,
        assets=assets,
        cash_proxy=args.cash_proxy,
        lookback_months=list(args.ensemble_lookbacks) if args.ensemble_lookbacks else [int(args.lookback_months[0])],
        ma_months=list(args.ensemble_mas) if args.ensemble_mas else [int(args.ma_months[0])],
        vol_months=int(args.vol_months[0]),
        min_history_months=24,
        max_weight=float(args.max_weight[0]),
        rebalance_months=1,
        side=str(args.side),
        signal_combine="sum",
        signal_threshold=0.0,
        signal_smooth_months=1,
        cost_bps=float(args.cost_bps[0]),
        slippage_bps=float(args.slippage_bps),
        slippage_cap_bps=25.0,
        slippage_ref_participation=0.10,
        portfolio_usd=float(args.portfolio_usd),
        min_median_dollar_volume=float(args.min_median_dollar_volume),
        dollar_volume_lookback_months=12,
        target_vol=float(args.target_vol[0]),
        vol_target_lookback_months=12,
        max_leverage=1.5,
        dd_throttle=float(args.dd_throttle[0]),
        dd_floor_exposure=float(args.dd_floor_exposure[0]),
    )
    if "error" in base:
        print(base["error"])
        return 2
    idx = pd.DatetimeIndex(base["pnl"].index).sort_values()
    fold_bounds = _split_months(idx, train_months=int(args.train_months), val_months=int(args.val_months), test_months=int(args.test_months), folds=int(args.folds))
    if not fold_bounds:
        print("Not enough history for requested folds.")
        return 2

    grid = {
        "lookback_months": args.lookback_months,
        "ma_months": args.ma_months,
        "vol_months": args.vol_months,
        "target_vol": args.target_vol,
        "dd_throttle": args.dd_throttle,
        "dd_floor_exposure": args.dd_floor_exposure,
        "max_weight": args.max_weight,
        "cost_bps": args.cost_bps,
        "signal_threshold": args.signal_threshold,
        "signal_smooth_months": args.signal_smooth_months,
    }
    param_list = list(_grid(grid))

    best: Optional[Dict[str, Any]] = None
    best_score = -1e18
    rows: List[Dict[str, Any]] = []
    t0 = time.time()

    for i, params in enumerate(param_list, 1):
        res = mod.run_trend_backtest(
            prices_daily=prices,
            volumes_daily=vols,
            assets=assets,
            cash_proxy=args.cash_proxy,
            lookback_months=list(args.ensemble_lookbacks) if args.ensemble_lookbacks else [int(params["lookback_months"])],
            ma_months=list(args.ensemble_mas) if args.ensemble_mas else [int(params["ma_months"])],
            vol_months=int(params["vol_months"]),
            min_history_months=24,
            max_weight=float(params["max_weight"]),
            rebalance_months=1,
            side=str(args.side),
            signal_combine="sum",
            signal_threshold=float(params.get("signal_threshold", 0.0)),
            signal_smooth_months=int(params.get("signal_smooth_months", 1)),
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=25.0,
            slippage_ref_participation=0.10,
            portfolio_usd=float(args.portfolio_usd),
            min_median_dollar_volume=float(args.min_median_dollar_volume),
            dollar_volume_lookback_months=12,
            target_vol=float(params["target_vol"]),
            vol_target_lookback_months=12,
            max_leverage=1.5,
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
        )
        if "error" in res:
            continue
        benches = mod.make_benchmarks(
            prices,
            vols,
            benchmark_ticker=str(args.benchmark),
            bond_ticker=str(args.bond_benchmark),
            target_vol=float(params["target_vol"]),
            vol_target_lookback_months=12,
            max_leverage=1.5,
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=25.0,
            slippage_ref_participation=0.10,
            portfolio_usd=float(args.portfolio_usd),
            dollar_volume_lookback_months=12,
        )
        bench_raw = benches.get("raw")
        bench_rm = benches.get("risk_managed_costed")
        bench_6040 = benches.get("sixty_forty_costed")
        if bench_6040 is None:
            bench_6040 = benches.get("sixty_forty_raw")
        if bench_raw is None or bench_rm is None:
            continue

        pnl = res["pnl"].sort_index()
        bench_raw = bench_raw.reindex(pnl.index).fillna(0.0)
        bench_rm = bench_rm.reindex(pnl.index).fillna(0.0)
        if bench_6040 is not None:
            bench_6040 = bench_6040.reindex(pnl.index).fillna(0.0)

        fold_vals = []
        fold_tests = []
        for v_start, t_start, t_end in fold_bounds:
            v_p = pnl[(pnl.index >= v_start) & (pnl.index < t_start)]
            v_b_raw = bench_raw[(bench_raw.index >= v_start) & (bench_raw.index < t_start)]
            v_b_rm = bench_rm[(bench_rm.index >= v_start) & (bench_rm.index < t_start)]
            v_ex_raw = v_p - v_b_raw
            v_ex_rm = v_p - v_b_rm
            fold_vals.append(
                {
                    "val_start": str(pd.Timestamp(v_start).date()),
                    "val_end": str(pd.Timestamp(t_start).date()),
                    "val_excess_ann_raw": float(v_ex_raw.mean() * 12.0) if len(v_ex_raw) else 0.0,
                    "val_ir_raw": float(_info_ratio(v_ex_raw)),
                    "val_excess_ann_rm": float(v_ex_rm.mean() * 12.0) if len(v_ex_rm) else 0.0,
                    "val_ir_rm": float(_info_ratio(v_ex_rm)),
                    "val_sharpe": float(mod.perf(v_p).sharpe),
                }
            )

            t_p = pnl[(pnl.index >= t_start) & (pnl.index <= t_end)]
            t_b_raw = bench_raw[(bench_raw.index >= t_start) & (bench_raw.index <= t_end)]
            t_b_rm = bench_rm[(bench_rm.index >= t_start) & (bench_rm.index <= t_end)]
            t_ex_raw = t_p - t_b_raw
            t_ex_rm = t_p - t_b_rm
            fold_tests.append(
                {
                    "test_start": str(pd.Timestamp(t_start).date()),
                    "test_end": str(pd.Timestamp(t_end).date()),
                    "test_excess_ann_raw": float(t_ex_raw.mean() * 12.0) if len(t_ex_raw) else 0.0,
                    "test_ir_raw": float(_info_ratio(t_ex_raw)),
                    "test_excess_ann_rm": float(t_ex_rm.mean() * 12.0) if len(t_ex_rm) else 0.0,
                    "test_ir_rm": float(_info_ratio(t_ex_rm)),
                    "test_sharpe": float(mod.perf(t_p).sharpe),
                }
            )

        # Select on RAW-SPY alpha by default; report risk-managed and 60/40 separately.
        val_ir_mean = float(np.mean([x["val_ir_raw"] for x in fold_vals])) if fold_vals else 0.0
        val_excess_mean = float(np.mean([x["val_excess_ann_raw"] for x in fold_vals])) if fold_vals else 0.0
        val_ir_min = float(np.min([x["val_ir_raw"] for x in fold_vals])) if fold_vals else 0.0

        # Score: reward validation IR/excess; penalize configs with very bad validation fold.
        score = float(1.0 * val_ir_mean + 0.5 * val_excess_mean + 0.5 * val_ir_min)

        # Alpha regression diagnostics on the combined validation window (proxy factors).
        val_pnl_agg = pd.concat(
            [pnl[(pnl.index >= v_start) & (pnl.index < t_start)] for v_start, t_start, _ in fold_bounds],
            axis=0,
        ).sort_index()
        val_b_raw_agg = pd.concat(
            [bench_raw[(bench_raw.index >= v_start) & (bench_raw.index < t_start)] for v_start, t_start, _ in fold_bounds],
            axis=0,
        ).sort_index()
        val_excess_raw = (val_pnl_agg - val_b_raw_agg).astype(float)
        X = _factor_proxy_panel(val_excess_raw.index, prices)
        alpha = alpha_mod.alpha_report_dict(alpha_mod.alpha_regression(val_excess_raw, X, lags=int(args.alpha_hac_lags)))

        row = {
            "params": {k: params[k] for k in params},
            "val_ir_mean": val_ir_mean,
            "val_excess_ann_mean": val_excess_mean,
            "val_ir_min": val_ir_min,
            "val_alpha_proxy": alpha,
            "test_ir_mean_raw": float(np.mean([x["test_ir_raw"] for x in fold_tests])) if fold_tests else 0.0,
            "test_excess_ann_mean_raw": float(np.mean([x["test_excess_ann_raw"] for x in fold_tests])) if fold_tests else 0.0,
            "test_ir_mean_rm": float(np.mean([x["test_ir_rm"] for x in fold_tests])) if fold_tests else 0.0,
            "test_excess_ann_mean_rm": float(np.mean([x["test_excess_ann_rm"] for x in fold_tests])) if fold_tests else 0.0,
            "test_excess_ann_mean_60_40": (
                float(np.mean([(pnl[(pnl.index >= pd.Timestamp(x['test_start'])) & (pnl.index <= pd.Timestamp(x['test_end']))] - bench_6040[(bench_6040.index >= pd.Timestamp(x['test_start'])) & (bench_6040.index <= pd.Timestamp(x['test_end']))]).mean() * 12.0 for x in fold_tests]))
                if bench_6040 is not None and fold_tests
                else None
            ),
            "fold_vals": fold_vals,
            "fold_tests": fold_tests,
            "score": score,
        }
        rows.append(row)
        if score > best_score:
            best_score = score
            best = row

        if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
            dt = max(1e-9, time.time() - t0)
            rate = i / dt
            remain = (len(param_list) - i) / max(1e-9, rate)
            print(f"[grid] {i}/{len(param_list)} best_score={best_score:.4f} rate={rate:.2f}/s eta={remain/60.0:.1f}m")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "grid_results.json").write_text(json.dumps(rows, indent=2))
    if best is None:
        print("No configuration succeeded.")
        return 2
    (args.out_dir / "summary.json").write_text(json.dumps(best, indent=2))
    print(json.dumps(best, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
