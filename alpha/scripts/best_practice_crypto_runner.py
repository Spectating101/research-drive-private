#!/usr/bin/env python3
"""
Best-practice (offline) selection runner for the passive crypto ML portfolio.

What this does:
- Runs a small, pre-registered parameter grid.
- Selects params using VALIDATION only (no tuning on the holdout).
- Reports holdout performance vs a *risk-managed* benchmark (BTC/ETH 60/40).

Why:
- If your mandate is "stable and consistent", the right benchmark is not raw BTC,
  but BTC/ETH with the same risk overlays (vol targeting + drawdown throttle),
  and similar cost assumptions.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# Allow `Sharpe-Renaissance/` local imports when invoked as a script.
import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
_SR_ROOT = _bmod.bootstrap_repo_paths(__file__)
if str(_SR_ROOT) not in sys.path:
    sys.path.insert(0, str(_SR_ROOT))

try:
    from research.cite_agent_client import CiteAgentClient
except Exception:
    CiteAgentClient = None  # type: ignore[assignment]


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
    pos_month: float


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
    pos_month = float((pnl > 0).mean()) if n else 0.0
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
        pos_month=pos_month,
    )


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _split_months(idx: pd.DatetimeIndex, train_frac: float, val_frac: float) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex, pd.DatetimeIndex]:
    idx = pd.DatetimeIndex(idx).sort_values()
    n = len(idx)
    if n < 48:
        raise ValueError(f"Need at least 48 months of data, have {n}")
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


def _grid(params: Dict[str, List[Any]]) -> Iterable[Dict[str, Any]]:
    keys = list(params.keys())
    for values in itertools.product(*[params[k] for k in keys]):
        yield dict(zip(keys, values))


def _score_stability(val: Perf, val_ir: float, *, dd_cap: float, worst12_cap: float, turnover_cap: float, avg_turnover: float) -> float:
    # Hard constraints (reject if violated)
    if val.n_months < 12:
        return -1e9
    if val.max_drawdown < -abs(dd_cap):
        return -1e9
    if not np.isnan(val.worst_12m) and val.worst_12m < -abs(worst12_cap):
        return -1e9
    if avg_turnover > turnover_cap:
        return -1e9

    # Soft objective: prioritize stability and genuine excess (IR).
    # (Weights are intentionally modest to avoid chasing noise.)
    return float(1.0 * val.sharpe + 0.75 * val_ir + 0.25 * val.cagr - 0.25 * abs(val.max_drawdown))


def main() -> int:
    p = argparse.ArgumentParser(description="Best-practice runner for the passive crypto ML portfolio.")
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("Sharpe-Renaissance/backtests/outputs/crypto_best_practice"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--train-frac", type=float, default=0.6)
    p.add_argument("--val-frac", type=float, default=0.2)
    p.add_argument("--dd-cap", type=float, default=0.25, help="Reject configs with worse val drawdown than this (e.g. 0.25 => -25%)")
    p.add_argument("--worst12-cap", type=float, default=0.30, help="Reject configs with worse 12m loss than this (e.g. 0.30 => -30%)")
    p.add_argument("--turnover-cap", type=float, default=1.2, help="Reject configs with higher avg monthly turnover than this")

    # Strategy base (kept stable-ish)
    p.add_argument("--train-months", type=int, default=36)
    p.add_argument("--min-history-months", type=int, default=48)
    p.add_argument("--max-assets", type=int, default=20)
    p.add_argument("--max-abs-monthly-return", type=float, default=3.0)
    p.add_argument("--min-median-dollar-volume", type=float, default=0.0, help="Liquidity filter: min trailing median monthly $ volume (0 disables)")
    p.add_argument("--dollar-volume-lookback-months", type=int, default=6)
    p.add_argument("--allow-numeric-tickers", action="store_true")
    p.add_argument("--btc-filter", action="store_true", default=True)
    p.add_argument("--slippage-bps", type=float, default=5.0, help="Base slippage in bps at reference participation")
    p.add_argument("--slippage-cap-bps", type=float, default=50.0)
    p.add_argument("--slippage-ref-participation", type=float, default=0.001)
    p.add_argument("--cite-agent-url", type=str, default="", help="Optional Cite-Agent base URL (e.g. http://127.0.0.1:8001)")
    p.add_argument("--cite-topics", nargs="*", default=[], help="Topic names to snapshot into the run summary")

    # Small grid (avoid data-snooping)
    p.add_argument("--top-n", type=int, nargs="+", default=[5, 7])
    p.add_argument("--max-weight", type=float, nargs="+", default=[0.35])
    p.add_argument("--target-vol", type=float, nargs="+", default=[0.12, 0.16])
    p.add_argument("--dd-throttle", type=float, nargs="+", default=[0.2, 0.25])
    p.add_argument("--dd-floor-exposure", type=float, nargs="+", default=[0.35])
    p.add_argument("--rebalance-months", type=int, nargs="+", default=[1])
    p.add_argument("--cost-bps", type=float, nargs="+", default=[20.0])
    args = p.parse_args()

    crypto_mod = _load_module(Path("Sharpe-Renaissance/scripts/crypto_passive_ml_portfolio.py"), "crypto_passive_ml_portfolio")
    prices_daily, vols_daily = crypto_mod.load_prices(args.panel, universe="crypto")

    # Determine split on strategy's monthly index.
    base = crypto_mod.backtest(
        prices_daily=prices_daily,
        volumes_daily=vols_daily,
        train_months=args.train_months,
        top_n=int(args.top_n[0]),
        max_weight=float(args.max_weight[0]),
        rebalance_months=int(args.rebalance_months[0]),
        cost_bps=float(args.cost_bps[0]),
        slippage_bps=float(args.slippage_bps),
        slippage_cap_bps=float(args.slippage_cap_bps),
        slippage_ref_participation=float(args.slippage_ref_participation),
        target_vol=float(args.target_vol[0]),
        dd_throttle=float(args.dd_throttle[0]),
        dd_floor_exposure=float(args.dd_floor_exposure[0]),
        btc_filter=bool(args.btc_filter),
        seed=args.seed,
        min_history_months=args.min_history_months,
        max_assets=args.max_assets,
        max_abs_monthly_return=args.max_abs_monthly_return,
        min_median_dollar_volume=float(args.min_median_dollar_volume),
        dollar_volume_lookback_months=int(args.dollar_volume_lookback_months),
        exclude_numeric_tickers=not args.allow_numeric_tickers,
    )
    if "error" in base:
        raise SystemExit(base["error"])
    idx = pd.DatetimeIndex(base["pnl"].index).sort_values()
    _, val_idx, test_idx = _split_months(idx, train_frac=args.train_frac, val_frac=args.val_frac)
    val_start = val_idx.min()
    test_start = test_idx.min()

    grid = {
        "top_n": args.top_n,
        "max_weight": args.max_weight,
        "target_vol": args.target_vol,
        "dd_throttle": args.dd_throttle,
        "dd_floor_exposure": args.dd_floor_exposure,
        "rebalance_months": args.rebalance_months,
        "cost_bps": args.cost_bps,
    }

    rows: List[Dict[str, Any]] = []
    best_row: Optional[Dict[str, Any]] = None
    best_score = -1e18

    for params in _grid(grid):
        res = crypto_mod.backtest(
            prices_daily=prices_daily,
            volumes_daily=vols_daily,
            train_months=args.train_months,
            top_n=int(params["top_n"]),
            max_weight=float(params["max_weight"]),
            rebalance_months=int(params["rebalance_months"]),
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=float(args.slippage_cap_bps),
            slippage_ref_participation=float(args.slippage_ref_participation),
            target_vol=float(params["target_vol"]),
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            btc_filter=bool(args.btc_filter),
            seed=args.seed,
            min_history_months=args.min_history_months,
            max_assets=args.max_assets,
            max_abs_monthly_return=args.max_abs_monthly_return,
            min_median_dollar_volume=float(args.min_median_dollar_volume),
            dollar_volume_lookback_months=int(args.dollar_volume_lookback_months),
            exclude_numeric_tickers=not args.allow_numeric_tickers,
        )
        if "error" in res:
            continue

        pnl = res["pnl"].sort_index()
        weights_hist = res["weights"]
        avg_turn = _avg_turnover(weights_hist)

        # Risk-managed benchmark (BTC/ETH 60/40 if possible; fall back to BTC).
        benches = crypto_mod.make_benchmarks(
            prices_daily,
            universe=res["universe"],
            target_vol=float(params["target_vol"]),
            dd_throttle=float(params["dd_throttle"]),
            dd_floor_exposure=float(params["dd_floor_exposure"]),
            cost_bps=float(params["cost_bps"]),
            slippage_bps=float(args.slippage_bps),
            slippage_cap_bps=float(args.slippage_cap_bps),
            slippage_ref_participation=float(args.slippage_ref_participation),
        )
        bench = None
        for key in ("btc_eth_60_40_costed_risk_managed", "btc_eth_60_40_risk_managed", "btc_risk_managed"):
            if key in benches and benches[key] is not None:
                bench = benches[key]
                break
        if bench is None:
            continue
        pnl_a, bench_a = pnl.align(bench, join="inner")

        val_pnl = pnl_a[(pnl_a.index >= val_start) & (pnl_a.index < test_start)]
        val_b = bench_a[(bench_a.index >= val_start) & (bench_a.index < test_start)]
        test_pnl = pnl_a[pnl_a.index >= test_start]
        test_b = bench_a[bench_a.index >= test_start]

        val_perf = _perf(val_pnl)
        test_perf = _perf(test_pnl)
        val_ir = _info_ratio(val_pnl - val_b)
        test_ir = _info_ratio(test_pnl - test_b)

        score = _score_stability(
            val_perf,
            val_ir,
            dd_cap=float(args.dd_cap),
            worst12_cap=float(args.worst12_cap),
            turnover_cap=float(args.turnover_cap),
            avg_turnover=avg_turn,
        )
        row = {
            **{k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in params.items()},
            "avg_turnover": avg_turn,
            "val": asdict(val_perf),
            "test": asdict(test_perf),
            "val_info_ratio": float(val_ir),
            "test_info_ratio": float(test_ir),
            "val_excess_ann_ret": float((val_pnl - val_b).mean() * 12.0),
            "test_excess_ann_ret": float((test_pnl - test_b).mean() * 12.0),
            "score": float(score),
        }
        rows.append(row)

        if score > best_score:
            best_score = score
            best_row = row

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "grid_results.json").write_text(json.dumps(rows, indent=2))
    if rows:
        df = pd.DataFrame(
            [
                {
                    **{k: r[k] for k in ["top_n", "max_weight", "target_vol", "dd_throttle", "dd_floor_exposure", "rebalance_months", "cost_bps", "avg_turnover", "val_info_ratio", "test_info_ratio", "val_excess_ann_ret", "test_excess_ann_ret", "score"]},
                    "val_sharpe": r["val"]["sharpe"],
                    "val_cagr": r["val"]["cagr"],
                    "val_max_dd": r["val"]["max_drawdown"],
                    "test_sharpe": r["test"]["sharpe"],
                    "test_cagr": r["test"]["cagr"],
                    "test_max_dd": r["test"]["max_drawdown"],
                }
                for r in rows
            ]
        ).sort_values("score", ascending=False)
        df.to_csv(args.out_dir / "grid_results.csv", index=False)

    if best_row is None:
        print("No configuration survived constraints.")
        return 2

    (args.out_dir / "best.json").write_text(json.dumps(best_row, indent=2))
    cite_context = {}
    if args.cite_agent_url and CiteAgentClient is not None:
        try:
            client = CiteAgentClient(args.cite_agent_url)
            for t in list(args.cite_topics):
                topic = client.get_topic(t)
                cite_context[t] = {
                    "query": topic.query,
                    "description": topic.description,
                    "last_updated": topic.last_updated,
                    "state": topic.state,
                }
        except Exception as e:
            cite_context = {"error": str(e)}

    summary = {
        "panel": str(args.panel),
        "split": {"val_start": str(val_start.date()), "test_start": str(test_start.date())},
        "grid_size": int(len(list(_grid(grid)))),
        "survivors": int(len(rows)),
        "best": best_row,
        "cite_agent": {"url": args.cite_agent_url, "topics": cite_context} if args.cite_agent_url else None,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
