#!/usr/bin/env python3
"""
Best-practice equity protocol runner (offline).

- Selects parameters using VALIDATION only (no tuning on the holdout).
- Benchmarks vs a *risk-managed* market index (default SPY) with identical overlays.
- Adds simple liquidity + slippage knobs to avoid paper-alpha.

This is intended as a disciplined evaluation harness, not a guarantee of future returns.
"""

from __future__ import annotations

import argparse
import time
import importlib.util
import itertools
import json
import sys
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class Perf:
    start: str
    end: str
    n_months: int
    cagr: float
    sharpe: float
    max_drawdown: float
    annual_vol: float
    final_equity: float
    worst_12m: float


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    dd = equity / equity.cummax() - 1.0
    return float(dd.min())


def _perf(pnl: pd.Series) -> Perf:
    pnl = pnl.fillna(0.0)
    equity = (1.0 + pnl).cumprod()
    n = len(pnl)
    vol = float(pnl.std(ddof=0) * np.sqrt(12.0)) if n > 2 else 0.0
    sharpe = float((pnl.mean() * 12.0) / vol) if vol > 0 else 0.0
    cagr = float(equity.iloc[-1] ** (12.0 / n) - 1.0) if n > 1 else 0.0
    worst_12m = (
        float(((1.0 + pnl).rolling(12).apply(np.prod, raw=True) - 1.0).min())
        if n >= 12
        else float("nan")
    )
    return Perf(
        start=str(equity.index.min().date()) if not equity.empty else "",
        end=str(equity.index.max().date()) if not equity.empty else "",
        n_months=int(n),
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=_max_drawdown(equity),
        annual_vol=vol,
        final_equity=float(equity.iloc[-1]) if not equity.empty else 1.0,
        worst_12m=worst_12m,
    )


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


def _sample_grid(
    params: Dict[str, List[Any]],
    *,
    n: int,
    seed: int,
) -> List[Dict[str, Any]]:
    keys = list(params.keys())
    sizes = [len(params[k]) for k in keys]
    total = int(np.prod(sizes)) if sizes else 0
    rng = np.random.default_rng(seed)

    if total <= 200_000:
        all_params = list(_grid(params))
        n = min(n, len(all_params))
        idx = rng.choice(len(all_params), size=n, replace=False)
        return [all_params[int(i)] for i in idx]

    # Fallback: independent sampling (may repeat combos if lists are small).
    out: List[Dict[str, Any]] = []
    for _ in range(n):
        out.append({k: params[k][int(rng.integers(0, len(params[k])))] for k in keys})
    return out


def _split_months(idx: pd.DatetimeIndex, train_frac: float, val_frac: float) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex, pd.DatetimeIndex]:
    idx = pd.DatetimeIndex(idx).sort_values()
    n = len(idx)
    if n < 60:
        raise ValueError(f"Need at least 60 months for a robust split, have {n}")
    n_train = max(24, int(round(n * train_frac)))
    n_val = max(12, int(round(n * val_frac)))
    n_train = min(n_train, n - 24)
    n_val = min(n_val, n - n_train - 12)
    train = idx[:n_train]
    val = idx[n_train : n_train + n_val]
    test = idx[n_train + n_val :]
    return train, val, test


def _info_ratio(excess: pd.Series) -> float:
    excess = excess.dropna()
    if len(excess) < 12:
        return 0.0
    ann = float(excess.mean() * 12.0)
    vol = float(excess.std(ddof=0) * np.sqrt(12.0))
    return float(ann / vol) if vol > 0 else 0.0


def _avg_turnover(weights_hist: List[Tuple[pd.Timestamp, pd.Series]]) -> float:
    if len(weights_hist) < 2:
        return 0.0
    turns = []
    prev = weights_hist[0][1].fillna(0.0)
    for _, w in weights_hist[1:]:
        w = w.fillna(0.0)
        turns.append(float((w - prev).abs().sum()))
        prev = w
    return float(np.mean(turns)) if turns else 0.0


def _rankings_from_weights_history(weights_hist: List[Tuple[pd.Timestamp, pd.Series]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt, weights in weights_hist:
        w = weights.replace([np.inf, -np.inf], np.nan).dropna()
        for instrument, value in w.items():
            rows.append(
                {
                    "date": pd.Timestamp(dt).date().isoformat(),
                    "instrument": str(instrument),
                    "score": float(value),
                }
            )
    return pd.DataFrame(rows)


def _score(
    val: Perf,
    val_ir: float,
    *,
    dd_cap: float,
    worst12_cap: float,
    turnover_cap: float,
    avg_turnover: float,
    stability_bonus: float,
) -> float:
    if val.n_months < 12:
        return -1e9
    if val.max_drawdown < -abs(dd_cap):
        return -1e9
    if not np.isnan(val.worst_12m) and val.worst_12m < -abs(worst12_cap):
        return -1e9
    if avg_turnover > turnover_cap:
        return -1e9
    return float(
        1.0 * val.sharpe
        + 0.75 * val_ir
        + 0.25 * val.cagr
        - 0.25 * abs(val.max_drawdown)
        + 0.25 * stability_bonus
    )


def sample_windows(
    *,
    prices_daily: pd.DataFrame,
    volumes_daily: Optional[pd.DataFrame],
    mod,
    market_ticker: str,
    universe: str,
    factor_set: str,
    exclude: List[str],
    params: Dict[str, Any],
    base_kwargs: Dict[str, Any],
    samples: int,
    window_months: int,
    seed: int,
) -> Dict[str, Any]:
    px_m = prices_daily.resample("ME").last()
    dates = px_m.index.dropna()
    if len(dates) < window_months + int(base_kwargs["train_months"]) + 2:
        return {"error": "not enough months for sampling"}

    rng = np.random.default_rng(seed)
    start_max = len(dates) - window_months
    starts = rng.integers(0, start_max, size=samples)

    out = []
    for s in starts:
        start = dates[s]
        end = dates[s + window_months - 1]
        pdw = prices_daily[(prices_daily.index >= start) & (prices_daily.index <= end)]
        vdw = volumes_daily[(volumes_daily.index >= start) & (volumes_daily.index <= end)] if volumes_daily is not None else None

        # Adjust history requirement for shorter windows.
        mh = int(base_kwargs["min_history_months"])
        base_kwargs_local = dict(base_kwargs)
        base_kwargs_local["min_history_months"] = int(min(mh, max(12, window_months - 6)))

        res = mod.run_equity_backtest(
            prices_daily=pdw,
            volumes_daily=vdw,
            market_ticker=market_ticker,
            train_months=int(base_kwargs_local["train_months"]),
            top_n=int(params["top_n"]),
            max_weight=float(params["max_weight"]),
            rebalance_months=1,
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(base_kwargs_local["slippage_bps"]),
            slippage_cap_bps=float(base_kwargs_local["slippage_cap_bps"]),
            slippage_ref_participation=float(base_kwargs_local["slippage_ref_participation"]),
            portfolio_usd=float(base_kwargs_local.get("portfolio_usd", 0.0)),
            target_vol=float(params["target_vol"]),
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            regime_filter=True,
            regime_off_exposure=float(params["regime_off_exposure"]),
            seed=int(base_kwargs_local["seed"]),
            min_history_months=int(base_kwargs_local["min_history_months"]),
            max_assets=int(base_kwargs_local["max_assets"]),
            include_max=(factor_set == "zoo"),
            include_amihud=(factor_set == "zoo"),
            exclude=list(exclude),
            min_median_dollar_volume=float(base_kwargs_local["min_median_dollar_volume"]),
            dollar_volume_lookback_months=int(base_kwargs_local["dollar_volume_lookback_months"]),
        )
        if "error" in res:
            continue
        row = res["perf"]
        row["window_start"] = str(pd.Timestamp(start).date())
        row["window_end"] = str(pd.Timestamp(end).date())
        out.append(row)
    return {"samples": out}


def main() -> int:
    p = argparse.ArgumentParser(description="Best-practice equity runner (validation/holdout).")
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--market-ticker", type=str, default="SPY")
    p.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests/outputs/equity_best_practice")
    p.add_argument("--candidate-registry-out", type=Path, default=SR_ROOT / "backtests/outputs/investment_cockpit/candidates")
    p.add_argument("--skip-candidate-manifest", action="store_true")
    p.add_argument("--universe", choices=["equities", "all"], default="equities")
    p.add_argument("--exclude", nargs="*", default=[])
    p.add_argument("--factor-set", choices=["parsimonious", "zoo"], default="parsimonious")
    p.add_argument("--side", choices=["long_only", "long_short"], default="long_only")

    p.add_argument("--train-frac", type=float, default=0.6)
    p.add_argument("--val-frac", type=float, default=0.2)
    p.add_argument("--dd-cap", type=float, default=0.35)
    p.add_argument("--worst12-cap", type=float, default=0.35)
    p.add_argument("--turnover-cap", type=float, default=1.5)

    # Base config
    p.add_argument("--train-months", type=int, default=36)
    p.add_argument("--min-history-months", type=int, default=24)
    p.add_argument("--max-assets", type=int, default=50)
    p.add_argument("--cost-bps", type=float, nargs="+", default=[10.0])
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--slippage-cap-bps", type=float, default=25.0)
    p.add_argument("--slippage-ref-participation", type=float, default=0.001)
    p.add_argument("--portfolio-usd", type=float, default=100000.0)
    p.add_argument("--min-median-dollar-volume", type=float, default=0.0)
    p.add_argument("--dollar-volume-lookback-months", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)

    # Grid (keep small; avoid data-snooping)
    p.add_argument("--top-n", type=int, nargs="+", default=[8, 10, 12])
    p.add_argument("--bottom-n", type=int, nargs="+", default=[0], help="Only used for --side long_short (0 => same as top_n).")
    p.add_argument("--max-weight", type=float, nargs="+", default=[0.15, 0.20])
    p.add_argument("--max-leverage", type=float, nargs="+", default=[1.5], help="Cap on vol-target scaling.")
    p.add_argument("--target-vol", type=float, nargs="+", default=[0.12, 0.15, 0.18])
    p.add_argument("--dd-throttle", type=float, nargs="+", default=[0.15, 0.20, 0.25])
    p.add_argument("--dd-floor-exposure", type=float, nargs="+", default=[0.35, 0.50])
    p.add_argument("--regime-off-exposure", type=float, nargs="+", default=[0.0, 0.25])
    p.add_argument("--sample", action="store_true", help="Run robustness window sampling on the selected best config")
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--window-months", type=int, default=60)
    p.add_argument("--walkforward-folds", type=int, default=1, help="Number of sequential test folds (>=1). 1 means single split.")
    p.add_argument("--val-months", type=int, default=18)
    p.add_argument("--test-months", type=int, default=18)
    p.add_argument("--min-val-fold-ir", type=float, default=-1e9, help="Hard constraint: minimum validation-fold Information Ratio (vs benchmark).")
    p.add_argument("--min-val-fold-excess-ann", type=float, default=-1e9, help="Hard constraint: minimum validation-fold excess annual return (vs benchmark).")
    p.add_argument("--min-val-fold-sharpe", type=float, default=-1e9, help="Hard constraint: minimum validation-fold Sharpe.")
    p.add_argument("--random-evals", type=int, default=0, help="If >0, evaluate a random subset of the grid (validation-only selection).")
    p.add_argument("--max-evals", type=int, default=0, help="If >0, stop after evaluating this many configs (after any random sampling).")
    p.add_argument("--log-every", type=int, default=10, help="Progress log frequency (configs).")
    args = p.parse_args()

    sys.path.insert(0, str(SR_ROOT))
    mod = _load_module(SR_ROOT / "scripts/equity_academic_runner.py", "equity_academic_runner")

    prices, vols = mod.load_prices(args.panel)
    if args.universe == "equities":
        keep = [c for c in prices.columns if not str(c).endswith("-USD")]
        prices = prices[keep]
        if vols is not None:
            vols = vols[keep]

    # Determine split using a single baseline run for index.
    base = mod.run_equity_backtest(
        prices_daily=prices,
        volumes_daily=vols,
        market_ticker=args.market_ticker,
        train_months=args.train_months,
        top_n=int(args.top_n[0]),
        bottom_n=int(args.bottom_n[0]),
        max_weight=float(args.max_weight[0]),
        rebalance_months=1,
        cost_bps=float(args.cost_bps[0]),
        slippage_bps=float(args.slippage_bps),
        slippage_cap_bps=float(args.slippage_cap_bps),
        slippage_ref_participation=float(args.slippage_ref_participation),
        portfolio_usd=float(args.portfolio_usd),
        target_vol=float(args.target_vol[0]),
        dd_throttle=float(args.dd_throttle[0]),
        dd_floor_exposure=float(args.dd_floor_exposure[0]),
        regime_filter=True,
        regime_off_exposure=float(args.regime_off_exposure[0]),
        seed=int(args.seed),
        min_history_months=int(args.min_history_months),
        max_assets=int(args.max_assets),
        include_max=(args.factor_set == "zoo"),
        include_amihud=(args.factor_set == "zoo"),
        exclude=list(args.exclude),
        min_median_dollar_volume=float(args.min_median_dollar_volume),
        dollar_volume_lookback_months=int(args.dollar_volume_lookback_months),
        side=str(args.side),
        max_leverage=float(args.max_leverage[0]),
    )
    if "error" in base:
        raise SystemExit(base["error"])
    idx = pd.DatetimeIndex(base["pnl"].index).sort_values()
    # Single split (default) or sequential walk-forward folds.
    if int(args.walkforward_folds) <= 1:
        _, val_idx, test_idx = _split_months(idx, train_frac=args.train_frac, val_frac=args.val_frac)
        fold_boundaries = [(val_idx.min(), test_idx.min(), test_idx.max())]
    else:
        folds_req = int(args.walkforward_folds)
        val_m = int(args.val_months)
        test_m = int(args.test_months)

        n = len(idx)
        # Ensure we have enough months for the requested folds given the rolling training requirement.
        max_folds = int((n - val_m - int(args.train_months)) // test_m)
        folds = max(1, min(folds_req, max_folds))
        if folds != folds_req:
            print(f"⚠️ Reducing walkforward folds from {folds_req} to {folds} due to limited history.")

        boundaries = []
        for k in range(folds):
            test_end_i = n - 1 - k * test_m
            test_start_i = n - (k + 1) * test_m
            val_end_i = test_start_i - 1
            val_start_i = val_end_i - val_m + 1
            if val_start_i < int(args.train_months):
                break
            boundaries.append((idx[val_start_i], idx[test_start_i], idx[test_end_i]))
        fold_boundaries = list(reversed(boundaries))

    val_start = fold_boundaries[0][0]
    test_start = fold_boundaries[0][1]

    grid = {
        "top_n": args.top_n,
        "bottom_n": args.bottom_n,
        "max_weight": args.max_weight,
        "max_leverage": args.max_leverage,
        "target_vol": args.target_vol,
        "dd_throttle": args.dd_throttle,
        "dd_floor_exposure": args.dd_floor_exposure,
        "regime_off_exposure": args.regime_off_exposure,
        "cost_bps": args.cost_bps,
    }

    grid_total = int(np.prod([len(v) for v in grid.values()])) if grid else 0
    if int(args.random_evals) > 0:
        param_list = _sample_grid(grid, n=int(args.random_evals), seed=int(args.seed))
    else:
        param_list = list(_grid(grid))
    if int(args.max_evals) > 0:
        param_list = param_list[: int(args.max_evals)]

    rows: List[Dict[str, Any]] = []
    best_row: Optional[Dict[str, Any]] = None
    best_result: Optional[Dict[str, Any]] = None
    best_score = -1e18
    t0 = time.time()
    survivors = 0

    for i, params in enumerate(param_list, 1):
        res = mod.run_equity_backtest(
            prices_daily=prices,
            volumes_daily=vols,
            market_ticker=args.market_ticker,
            train_months=args.train_months,
            top_n=int(params["top_n"]),
            bottom_n=int(params["bottom_n"]),
            max_weight=float(params["max_weight"]),
            rebalance_months=1,
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=float(args.slippage_cap_bps),
            slippage_ref_participation=float(args.slippage_ref_participation),
            portfolio_usd=float(args.portfolio_usd),
            target_vol=float(params["target_vol"]),
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            regime_filter=True,
            regime_off_exposure=float(params["regime_off_exposure"]),
            seed=int(args.seed),
            min_history_months=int(args.min_history_months),
            max_assets=int(args.max_assets),
            include_max=(args.factor_set == "zoo"),
            include_amihud=(args.factor_set == "zoo"),
            exclude=list(args.exclude),
            min_median_dollar_volume=float(args.min_median_dollar_volume),
            dollar_volume_lookback_months=int(args.dollar_volume_lookback_months),
            side=str(args.side),
            max_leverage=float(params["max_leverage"]),
        )
        if "error" in res:
            if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
                dt = max(1e-9, time.time() - t0)
                rate = i / dt
                remain = (len(param_list) - i) / max(1e-9, rate)
                print(
                    f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                    f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
                )
            continue

        benches = mod.make_benchmarks(
            prices,
            vols,
            market_ticker=args.market_ticker,
            target_vol=float(params["target_vol"]),
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            regime_filter=True,
            regime_off_exposure=float(params["regime_off_exposure"]),
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=float(args.slippage_cap_bps),
            slippage_ref_participation=float(args.slippage_ref_participation),
            portfolio_usd=float(args.portfolio_usd),
            market_regime=res.get("market_regime"),
        )
        bench = None
        for key in ("risk_managed_costed", "risk_managed", "raw"):
            if key in benches and benches[key] is not None:
                bench = benches[key]
                break
        if bench is None:
            if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
                dt = max(1e-9, time.time() - t0)
                rate = i / dt
                remain = (len(param_list) - i) / max(1e-9, rate)
                print(
                    f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                    f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
                )
            continue

        pnl = res["pnl"].sort_index()
        bench = bench.reindex(pnl.index).fillna(0.0)

        # Score using ALL folds' validation windows (more stable than a single year).
        fold_vals = []
        fold_tests = []
        for f_val_start, f_test_start, f_test_end in fold_boundaries:
            f_val_pnl = pnl[(pnl.index >= f_val_start) & (pnl.index < f_test_start)]
            f_val_b = bench[(bench.index >= f_val_start) & (bench.index < f_test_start)]
            f_val_perf = _perf(f_val_pnl)
            f_val_ir = _info_ratio(f_val_pnl - f_val_b)
            fold_vals.append(
                {
                    "val_start": str(pd.Timestamp(f_val_start).date()),
                    "val_end": str(pd.Timestamp(f_test_start).date()),
                    "val": asdict(f_val_perf),
                    "val_info_ratio": float(f_val_ir),
                    "val_excess_ann_ret": float((f_val_pnl - f_val_b).mean() * 12.0) if len(f_val_pnl) else 0.0,
                }
            )

            f_test_pnl = pnl[(pnl.index >= f_test_start) & (pnl.index <= f_test_end)]
            f_test_b = bench[(bench.index >= f_test_start) & (bench.index <= f_test_end)]
            f_test_perf = _perf(f_test_pnl)
            f_test_ir = _info_ratio(f_test_pnl - f_test_b)
            fold_tests.append(
                {
                    "val_start": str(pd.Timestamp(f_val_start).date()),
                    "test_start": str(pd.Timestamp(f_test_start).date()),
                    "test_end": str(pd.Timestamp(f_test_end).date()),
                    "test": asdict(f_test_perf),
                    "test_info_ratio": float(f_test_ir),
                    "test_excess_ann_ret": float((f_test_pnl - f_test_b).mean() * 12.0) if len(f_test_pnl) else 0.0,
                }
            )

        # Aggregate validation performance by concatenating the fold validation windows.
        val_pnl_agg = pd.concat(
            [pnl[(pnl.index >= f_val_start) & (pnl.index < f_test_start)] for f_val_start, f_test_start, _ in fold_boundaries],
            axis=0,
        ).sort_index()
        val_b_agg = pd.concat(
            [bench[(bench.index >= f_val_start) & (bench.index < f_test_start)] for f_val_start, f_test_start, _ in fold_boundaries],
            axis=0,
        ).sort_index()
        # Guard against duplicate month-ends if boundaries ever overlap.
        val_pnl_agg = val_pnl_agg[~val_pnl_agg.index.duplicated(keep="first")]
        val_b_agg = val_b_agg[~val_b_agg.index.duplicated(keep="first")]

        val_perf = _perf(val_pnl_agg)
        val_ir = _info_ratio(val_pnl_agg - val_b_agg)
        val_excess_ann = float((val_pnl_agg - val_b_agg).mean() * 12.0) if len(val_pnl_agg) else 0.0

        # Stability bonus: reward configs that avoid "bad years" on validation.
        val_ir_min = float(np.min([fv["val_info_ratio"] for fv in fold_vals])) if fold_vals else 0.0
        val_sh_min = float(np.min([fv["val"]["sharpe"] for fv in fold_vals])) if fold_vals else 0.0
        val_excess_min = float(np.min([fv["val_excess_ann_ret"] for fv in fold_vals])) if fold_vals else 0.0
        stability_bonus = float(0.5 * val_ir_min + 0.5 * val_sh_min + 0.25 * val_excess_min)

        avg_turn = _avg_turnover(res["weights"])

        # Hard stability constraints (validation folds ONLY; avoids test leakage).
        if val_ir_min < float(args.min_val_fold_ir):
            if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
                dt = max(1e-9, time.time() - t0)
                rate = i / dt
                remain = (len(param_list) - i) / max(1e-9, rate)
                print(
                    f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                    f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
                )
            continue
        if val_excess_min < float(args.min_val_fold_excess_ann):
            if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
                dt = max(1e-9, time.time() - t0)
                rate = i / dt
                remain = (len(param_list) - i) / max(1e-9, rate)
                print(
                    f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                    f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
                )
            continue
        if val_sh_min < float(args.min_val_fold_sharpe):
            if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
                dt = max(1e-9, time.time() - t0)
                rate = i / dt
                remain = (len(param_list) - i) / max(1e-9, rate)
                print(
                    f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                    f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
                )
            continue

        score = _score(
            val_perf,
            val_ir,
            dd_cap=float(args.dd_cap),
            worst12_cap=float(args.worst12_cap),
            turnover_cap=float(args.turnover_cap),
            avg_turnover=avg_turn,
            stability_bonus=stability_bonus,
        )

        # Aggregate fold tests (mean of fold IR / excess) + aggregate test perf for sanity.
        test_ir_mean = float(np.mean([ft["test_info_ratio"] for ft in fold_tests])) if fold_tests else 0.0
        test_excess_mean = float(np.mean([ft["test_excess_ann_ret"] for ft in fold_tests])) if fold_tests else 0.0
        test_start_agg = fold_boundaries[0][1]
        test_end_agg = fold_boundaries[-1][2]
        test_pnl_agg = pnl[(pnl.index >= test_start_agg) & (pnl.index <= test_end_agg)]
        test_perf_agg = _perf(test_pnl_agg)

        row = {
            "params": {k: params[k] for k in params},
            "avg_turnover": float(avg_turn),
            "val": asdict(val_perf),
            "val_info_ratio": float(val_ir),
            "val_excess_ann_ret": float(val_excess_ann),
            "test": asdict(test_perf_agg),
            "test_info_ratio": float(test_ir_mean),
            "test_excess_ann_ret": float(test_excess_mean),
            "fold_vals": fold_vals,
            "fold_tests": fold_tests,
            "stability": {
                "val_ir_min": float(val_ir_min),
                "val_sh_min": float(val_sh_min),
                "val_excess_ann_ret_min": float(val_excess_min),
            },
            "score": float(score),
        }
        rows.append(row)
        survivors += 1
        if score > best_score:
            best_score = score
            best_row = row
            best_result = res

        if int(args.log_every) > 0 and (i % int(args.log_every) == 0 or i == len(param_list)):
            dt = max(1e-9, time.time() - t0)
            rate = i / dt
            remain = (len(param_list) - i) / max(1e-9, rate)
            print(
                f"[grid] {i}/{len(param_list)} (survivors={survivors}) "
                f"best_score={best_score:.4f} rate={rate:.3f}/s eta={remain/60.0:.1f}m"
            )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "grid_results.json").write_text(json.dumps(rows, indent=2))

    if rows:
        flat = []
        for r in rows:
            flat.append(
                {
                    **r["params"],
                    "avg_turnover": r["avg_turnover"],
                    "score": r["score"],
                    "val_sharpe": r["val"]["sharpe"],
                    "val_cagr": r["val"]["cagr"],
                    "val_max_dd": r["val"]["max_drawdown"],
                    "val_ir": r["val_info_ratio"],
                    "test_sharpe": r["test"]["sharpe"],
                    "test_cagr": r["test"]["cagr"],
                    "test_max_dd": r["test"]["max_drawdown"],
                    "test_ir": r["test_info_ratio"],
                }
            )
        pd.DataFrame(flat).sort_values("score", ascending=False).to_csv(args.out_dir / "grid_results.csv", index=False)

    if best_row is None:
        print("No configuration survived constraints.")
        return 2

    (args.out_dir / "best.json").write_text(json.dumps(best_row, indent=2))
    factor_tearsheet_paths: dict[str, str] = {}
    try:
        from src.research.investment_cockpit import compute_factor_tearsheet

        if best_result and best_result.get("weights"):
            rankings = _rankings_from_weights_history(best_result["weights"])
            if not rankings.empty:
                rankings_path = args.out_dir / "factor_rankings.csv"
                rankings.to_csv(rankings_path, index=False)
                sheet = compute_factor_tearsheet(
                    rankings,
                    args.panel,
                    date_col="date",
                    instrument_col="instrument",
                    score_col="score",
                    horizon_days=21,
                    quantiles=5,
                    top_n=int(best_row["params"]["top_n"]),
                )
                factor_tearsheet_paths = sheet.write(args.out_dir / "factor_tearsheet")
                factor_tearsheet_paths["rankings"] = str(rankings_path)
    except Exception as exc:
        print(f"[warn] factor tear sheet generation failed: {exc}")

    summary = {
        "panel": str(args.panel),
        "market_ticker": args.market_ticker,
        "split": {"val_start": str(val_start.date()), "test_start": str(test_start.date())},
        "grid_size": int(grid_total),
        "grid_evaluated": int(len(param_list)),
        "survivors": int(len(rows)),
        "best": best_row,
        "frictions": {
            "cost_bps": args.cost_bps,
            "slippage_bps": args.slippage_bps,
            "min_median_dollar_volume": args.min_median_dollar_volume,
        },
        "factor_tearsheet": factor_tearsheet_paths,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    if not args.skip_candidate_manifest:
        try:
            from src.research.investment_cockpit import register_candidate_run
            from src.research.stock_investment_data import make_universe_record, universe_from_panel, upsert_universe_registry

            tickers = universe_from_panel(args.panel)
            universe_id = f"{args.universe}_{args.factor_set}_{args.market_ticker}"
            universe_record = make_universe_record(
                universe_id=universe_id,
                tickers=tickers,
                source=str(args.panel),
                notes="Generated from best_practice_equity_runner panel.",
            )
            upsert_universe_registry(SR_ROOT / "config" / "stock_universe_registry.json", universe_record)
            manifest_status = "paper_candidate" if factor_tearsheet_paths else "blocked"
            artifacts = {
                "summary": args.out_dir / "summary.json",
                "best": args.out_dir / "best.json",
                "grid_results": args.out_dir / "grid_results.json",
                "grid_results_csv": args.out_dir / "grid_results.csv",
            }
            if (args.out_dir / "sampling.json").exists():
                artifacts["sampling"] = args.out_dir / "sampling.json"
            if factor_tearsheet_paths:
                artifacts.update(
                    {
                        "factor_rankings": factor_tearsheet_paths.get("rankings"),
                        "factor_tearsheet_summary": factor_tearsheet_paths.get("summary"),
                        "factor_tearsheet_ic": factor_tearsheet_paths.get("ic_by_date"),
                        "factor_tearsheet_buckets": factor_tearsheet_paths.get("bucket_returns"),
                        "factor_tearsheet_turnover": factor_tearsheet_paths.get("turnover"),
                    }
                )
            register_candidate_run(
                strategy=f"equity_best_practice_{args.universe}_{args.factor_set}",
                status=manifest_status,
                run_dir=args.out_dir,
                out_dir=args.candidate_registry_out,
                artifacts=artifacts,
                params={
                    "market_ticker": args.market_ticker,
                    "universe": args.universe,
                    "universe_id": universe_id,
                    "universe_hash": universe_record["universe_hash"],
                    "factor_set": args.factor_set,
                    "side": args.side,
                    "benchmark_id": args.market_ticker,
                    "cost_model_id": f"cost_bps={args.cost_bps};slippage_bps={args.slippage_bps}",
                    "validation_protocol": "walk_forward_validation_holdout",
                    "requires_factor_tearsheet": True,
                    "selector_type": "stock_selector",
                },
                notes="Auto-registered by best_practice_equity_runner."
                if factor_tearsheet_paths
                else "Auto-registered but blocked because factor tear sheet generation failed.",
            )
        except Exception as exc:
            print(f"[warn] candidate manifest registration failed: {exc}")
    if args.sample:
        samp = sample_windows(
            prices_daily=prices,
            volumes_daily=vols,
            mod=mod,
            market_ticker=args.market_ticker,
            universe=args.universe,
            factor_set=args.factor_set,
            exclude=list(args.exclude),
            params=best_row["params"],
            base_kwargs={
                "train_months": args.train_months,
                "min_history_months": args.min_history_months,
                "max_assets": args.max_assets,
                "seed": args.seed,
                "slippage_bps": args.slippage_bps,
                "slippage_cap_bps": args.slippage_cap_bps,
                "slippage_ref_participation": args.slippage_ref_participation,
                "min_median_dollar_volume": args.min_median_dollar_volume,
                "dollar_volume_lookback_months": args.dollar_volume_lookback_months,
            },
            samples=args.samples,
            window_months=args.window_months,
            seed=args.seed,
        )
        (args.out_dir / "sampling.json").write_text(json.dumps(samp, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
