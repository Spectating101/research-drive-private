#!/usr/bin/env python3
from __future__ import annotations

"""
Constrained sweep: find the best "growth" configuration subject to drawdown limits.

Objective (math-first)
- Maximize CAGR
Constraints
- Max drawdown (MDD) <= budget across sampled windows

Approach
1) Randomly sample configs from sensible ranges.
2) Screen on the full available period (fast-ish).
3) Take the top-K and run multi-window robustness + feature-shuffle null.

This is designed to answer: "keep going until it's best and nothing more to prove"
in a reproducible, parameterized way.
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

from scripts.alpha_insights_walkforward_runner import (  # noqa: E402
    daily_close_wide,
    load_panel,
    monthly_close_and_returns,
    walkforward_backtest,
)
from src.strategy.control_profiles import apply_profile_to_namespace, profiles_json  # noqa: E402

CFG_KEYS = [
    "target_vol",
    "max_gross",
    "allow_leverage",
    "top_n",
    "max_weight",
    "alpha_tstat_scale",
    "regime_off_gross",
    "corr_filter",
    "corr_threshold",
    "corr_lookback",
    "risk_budget",
    "max_turnover",
    "pf_dd_threshold",
    "pf_dd_floor_gross",
    "min_cash_weight",
    "max_crypto_gross",
    "cb_dd_trigger",
    "cb_alpha_trigger",
    "cb_alpha_window",
    "cb_cooldown_months",
    "cb_floor_gross",
]


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer, float, np.floating)):
        return bool(int(v))
    s = str(v).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0", ""}:
        return False
    raise ValueError(f"Cannot coerce to bool: {v!r}")


def _cfg_from_row(row: pd.Series) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    for k in CFG_KEYS:
        if k not in row:
            continue
        v = row[k]
        if k in {"allow_leverage", "corr_filter", "risk_budget"}:
            cfg[k] = _coerce_bool(v)
        elif k in {"top_n", "corr_lookback", "cb_alpha_window", "cb_cooldown_months"}:
            cfg[k] = int(v)
        else:
            cfg[k] = float(v)
    cfg.setdefault("allow_leverage", True)
    cfg.setdefault("min_cash_weight", 0.05)
    cfg.setdefault("max_crypto_gross", 0.60)
    cfg.setdefault("cb_dd_trigger", 0.12)
    cfg.setdefault("cb_alpha_trigger", -0.02)
    cfg.setdefault("cb_alpha_window", 3)
    cfg.setdefault("cb_cooldown_months", 2)
    cfg.setdefault("cb_floor_gross", 0.35)
    return cfg


def _load_windows(path: Path) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    js = json.loads(path.read_text())
    out: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    for w in js:
        out.append((pd.Timestamp(w["start"]), pd.Timestamp(w["end"])))
    return out


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


def _subset_features(features: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    f = features.copy()
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    return f[(f["date"] >= start) & (f["date"] <= end)].copy()


def _subset_ret_m(ret_m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return ret_m.loc[(ret_m.index >= start) & (ret_m.index <= end)].copy()


def _run_one(
    feats: pd.DataFrame,
    ret_m: pd.DataFrame,
    *,
    cfg: Dict[str, Any],
    benchmark: str,
    cash_ticker: str,
    train_months: int,
    cost_bps: float,
    lam_grid: List[float],
    min_assets: int,
    vol_lookback: int,
    regime_filter: bool,
    regime_window: int,
    alpha_mode: str,
    ic_months: int,
    base: str,
) -> Dict[str, Any]:
    return walkforward_backtest(
        feats,
        ret_m=ret_m,
        benchmark=str(benchmark),
        train_months=int(train_months),
        top_n=int(cfg["top_n"]),
        max_weight=float(cfg["max_weight"]),
        cash_ticker=str(cash_ticker),
        cost_bps=float(cost_bps),
        lam_grid=[float(x) for x in lam_grid],
        min_assets=int(min_assets),
        target_vol=float(cfg["target_vol"]),
        vol_lookback=int(vol_lookback),
        max_gross=float(cfg["max_gross"]),
        allow_leverage=bool(cfg["allow_leverage"]),
        regime_filter=bool(regime_filter),
        regime_window=int(regime_window),
        regime_off_gross=float(cfg["regime_off_gross"]),
        base=str(base),
        alpha_mode=str(alpha_mode),
        ic_months=int(ic_months),
        alpha_tstat_scale=float(cfg["alpha_tstat_scale"]),
        auto_params=False,
        policy_window=12,
        corr_filter=bool(cfg["corr_filter"]),
        corr_threshold=float(cfg["corr_threshold"]),
        corr_lookback=int(cfg["corr_lookback"]),
        risk_budget=bool(cfg["risk_budget"]),
        max_turnover=float(cfg["max_turnover"]),
        pf_dd_threshold=float(cfg["pf_dd_threshold"]),
        pf_dd_floor_gross=float(cfg["pf_dd_floor_gross"]),
        min_cash_weight=float(cfg["min_cash_weight"]),
        max_crypto_gross=float(cfg["max_crypto_gross"]),
        cb_dd_trigger=float(cfg["cb_dd_trigger"]),
        cb_alpha_trigger=float(cfg["cb_alpha_trigger"]),
        cb_alpha_window=int(cfg["cb_alpha_window"]),
        cb_cooldown_months=int(cfg["cb_cooldown_months"]),
        cb_floor_gross=float(cfg["cb_floor_gross"]),
        glidepath=False,
        build_max_dd=0.25,
        coast_max_dd=0.15,
        coast_multiple=2.0,
        cppi_mult=3.0,
    )


def _sample_cfg(rng: np.random.Generator) -> Dict[str, Any]:
    # Ranges are intentionally bounded to "reasonable" for this project.
    # Include both "asset allocation" and "equity cross-section" friendly choices.
    target_vol = float(rng.choice([0.10, 0.12, 0.14, 0.16, 0.18, 0.20]))
    max_gross = float(rng.choice([1.0, 1.25, 1.5]))
    allow_leverage = bool(rng.choice([True, False], p=[0.7, 0.3]))
    top_n = int(rng.choice([3, 4, 5, 8, 10, 15]))
    max_weight = float(rng.choice([0.10, 0.15, 0.20, 0.25, 0.35, 0.40, 0.50]))
    alpha_tstat_scale = float(rng.choice([1.0, 1.25, 1.5, 2.0]))
    regime_off_gross = float(rng.choice([0.0, 0.10, 0.25]))

    # Portfolio mgmt knobs (these are the biggest levers on drawdown).
    corr_filter = bool(rng.choice([True, False], p=[0.7, 0.3]))
    corr_threshold = float(rng.choice([0.75, 0.80, 0.85, 0.90]))
    corr_lookback = int(rng.choice([6, 12]))
    risk_budget = bool(rng.choice([True, False], p=[0.7, 0.3]))
    max_turnover = float(rng.choice([0.25, 0.50, 0.75, 1.0]))
    pf_dd_threshold = float(rng.choice([0.0, 0.15, 0.20, 0.25, 0.30]))
    pf_dd_floor_gross = float(rng.choice([0.30, 0.50, 0.70, 0.85]))
    min_cash_weight = float(rng.choice([0.0, 0.03, 0.05, 0.10]))
    max_crypto_gross = float(rng.choice([0.45, 0.60, 0.75, 0.90, 1.0]))
    cb_dd_trigger = float(rng.choice([0.0, 0.10, 0.12, 0.15]))
    cb_alpha_trigger = float(rng.choice([-0.03, -0.02, -0.015, -0.01]))
    cb_alpha_window = int(rng.choice([0, 2, 3, 4]))
    cb_cooldown_months = int(rng.choice([0, 1, 2, 3]))
    cb_floor_gross = float(rng.choice([0.30, 0.45, 0.60, 0.75, 1.0]))

    return {
        "target_vol": target_vol,
        "max_gross": max_gross,
        "allow_leverage": bool(allow_leverage),
        "top_n": top_n,
        "max_weight": max_weight,
        "alpha_tstat_scale": alpha_tstat_scale,
        "regime_off_gross": regime_off_gross,
        "corr_filter": corr_filter,
        "corr_threshold": corr_threshold,
        "corr_lookback": corr_lookback,
        "risk_budget": risk_budget,
        "max_turnover": max_turnover,
        "pf_dd_threshold": pf_dd_threshold,
        "pf_dd_floor_gross": pf_dd_floor_gross,
        "min_cash_weight": min_cash_weight,
        "max_crypto_gross": max_crypto_gross,
        "cb_dd_trigger": cb_dd_trigger,
        "cb_alpha_trigger": cb_alpha_trigger,
        "cb_alpha_window": cb_alpha_window,
        "cb_cooldown_months": cb_cooldown_months,
        "cb_floor_gross": cb_floor_gross,
    }


@dataclass(frozen=True)
class ScreenRow:
    cfg_id: int
    cagr: float
    sharpe: float
    max_drawdown: float
    final_equity: float
    cfg: Dict[str, Any]


@dataclass(frozen=True)
class RobustRow:
    cfg_id: int
    pass_mdd: float
    pass_cagr: float
    median_cagr: float
    median_mdd: float
    worst_mdd: float
    cfg: Dict[str, Any]


def main() -> int:
    warnings.filterwarnings("ignore", category=FutureWarning)

    ap = argparse.ArgumentParser(description="Constrained sweep: maximize CAGR subject to MDD budget.")
    ap.add_argument("--panel", type=Path, default=SR_ROOT / "data_lake" / "yfinance_multi_asset_core_10y.csv")
    ap.add_argument("--feature-cache", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=SR_ROOT / "backtests" / "outputs" / "alpha_constrained_sweep")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--universe", choices=["all", "equities", "crypto"], default="all")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--cash-ticker", type=str, default="BIL")
    ap.add_argument("--train-months", type=int, default=48)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--lam-grid", nargs="*", type=float, default=[0.1, 1.0, 10.0])
    ap.add_argument("--min-assets", type=int, default=4)
    ap.add_argument("--vol-lookback", type=int, default=12)
    ap.add_argument("--regime-filter", action="store_true")
    ap.add_argument("--regime-window", type=int, default=12)
    ap.add_argument("--alpha-mode", choices=["fixed", "ic_tstat"], default="ic_tstat")
    ap.add_argument("--ic-months", type=int, default=12)
    ap.add_argument("--base", choices=["cash", "benchmark", "trend"], default="trend")
    ap.add_argument(
        "--control-profile",
        choices=["custom", "off", "growth", "balanced", "defensive"],
        default="custom",
        help="Named control preset used as defaults for random sweep ranges if not custom.",
    )
    ap.add_argument("--print-control-profiles", action="store_true", help="Print built-in control profiles as JSON and exit.")
    ap.add_argument("--min-cash-weight", type=float, default=0.05)
    ap.add_argument("--max-crypto-gross", type=float, default=0.60)
    ap.add_argument("--cb-dd-trigger", type=float, default=0.12)
    ap.add_argument("--cb-alpha-trigger", type=float, default=-0.02)
    ap.add_argument("--cb-alpha-window", type=int, default=3)
    ap.add_argument("--cb-cooldown-months", type=int, default=2)
    ap.add_argument("--cb-floor-gross", type=float, default=0.35)

    ap.add_argument("--dd-budget", type=float, default=0.25, help="Drawdown budget constraint (e.g., 0.25).")
    ap.add_argument("--n-samples", type=int, default=30, help="Number of random configs to sample.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--top-k", type=int, default=6, help="Top K configs to robustness-check.")
    ap.add_argument("--window-months", type=int, default=96)
    ap.add_argument("--n-windows", type=int, default=6)
    ap.add_argument(
        "--robust-only",
        action="store_true",
        help="Skip screening and only run robustness on out-dir/candidates.csv using out-dir/windows.json.",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Resume robustness if out-dir/robust_progress.csv exists (skips completed cfg_ids).",
    )
    args = ap.parse_args()

    if bool(args.print_control_profiles):
        print(profiles_json())
        return 0
    if str(args.control_profile) != "custom":
        apply_profile_to_namespace(args, str(args.control_profile))

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

    # Ensure cash exists for overlays (vol targeting / throttles) on equity panels.
    if args.cash_ticker and args.cash_ticker not in close_d.columns:
        close_d[str(args.cash_ticker)] = 1.0
    _, ret_m = monthly_close_and_returns(close_d)

    if args.feature_cache.suffix.lower() == ".parquet":
        feats = pd.read_parquet(args.feature_cache)
    else:
        feats = pd.read_csv(args.feature_cache, parse_dates=["date"])
    feats["date"] = pd.to_datetime(feats["date"], errors="coerce")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    windows_path = args.out_dir / "windows.json"
    candidates_path = args.out_dir / "candidates.csv"

    if bool(args.robust_only):
        if not windows_path.exists():
            raise FileNotFoundError(f"Missing windows file: {windows_path}")
        if not candidates_path.exists():
            raise FileNotFoundError(f"Missing candidates file: {candidates_path}")
        windows = _load_windows(windows_path)
        sampled = []
    else:
        dates = sorted(set(pd.Timestamp(d) for d in feats["date"].dropna().unique()))
        windows = _pick_unique_windows(
            dates,
            window_months=int(args.window_months),
            n_windows=int(args.n_windows),
            seed=int(args.seed),
        )
        windows_path.write_text(
            json.dumps([{"start": str(a.date()), "end": str(b.date())} for a, b in windows], indent=2)
        )
        rng = np.random.default_rng(int(args.seed))
        sampled = [_sample_cfg(rng) for _ in range(int(args.n_samples))]
        # Ensure profile knobs are included in each sampled cfg.
        for cfg in sampled:
            cfg.setdefault("min_cash_weight", float(args.min_cash_weight))
            cfg.setdefault("max_crypto_gross", float(args.max_crypto_gross))
            cfg.setdefault("cb_dd_trigger", float(args.cb_dd_trigger))
            cfg.setdefault("cb_alpha_trigger", float(args.cb_alpha_trigger))
            cfg.setdefault("cb_alpha_window", int(args.cb_alpha_window))
            cfg.setdefault("cb_cooldown_months", int(args.cb_cooldown_months))
            cfg.setdefault("cb_floor_gross", float(args.cb_floor_gross))

    screen_progress_path = args.out_dir / "screen_progress.csv"
    done_screen: set[int] = set()
    if not bool(args.robust_only) and bool(args.resume) and screen_progress_path.exists():
        try:
            done_screen = set(int(x) for x in pd.read_csv(screen_progress_path)["cfg_id"].dropna().unique())
            print(f"[resume] loaded {len(done_screen)} screened cfgs from {screen_progress_path}")
        except Exception as e:
            print(f"[resume] failed to read {screen_progress_path}: {e}")
            done_screen = set()

    if bool(args.robust_only):
        ok = pd.read_csv(candidates_path)
    else:
        for i, cfg in enumerate(sampled):
            if int(i) in done_screen:
                continue
            res = _run_one(
                feats,
                ret_m=ret_m,
                cfg=cfg,
                benchmark=str(args.benchmark),
                cash_ticker=str(args.cash_ticker),
                train_months=int(args.train_months),
                cost_bps=float(args.cost_bps),
                lam_grid=[float(x) for x in args.lam_grid],
                min_assets=int(args.min_assets),
                vol_lookback=int(args.vol_lookback),
                regime_filter=bool(args.regime_filter),
                regime_window=int(args.regime_window),
                alpha_mode=str(args.alpha_mode),
                ic_months=int(args.ic_months),
                base=str(args.base),
            )
            p = res["perf"]
            row_out = {
                "cfg_id": int(i),
                "cagr": float(p.get("cagr") or float("nan")),
                "sharpe": float(p.get("sharpe") or float("nan")),
                "max_drawdown": float(p.get("max_drawdown") or float("nan")),
                "final_equity": float(p.get("final_equity") or float("nan")),
                **dict(cfg),
            }
            pd.DataFrame([row_out]).to_csv(screen_progress_path, mode="a", header=not screen_progress_path.exists(), index=False)
            print(f"[screen {i+1}/{len(sampled)}] cagr={row_out['cagr']:.3f} mdd={row_out['max_drawdown']:.3f} cfg={cfg}")

        if screen_progress_path.exists():
            df_screen = pd.read_csv(screen_progress_path)
        else:
            df_screen = pd.DataFrame()
        df_screen.to_csv(args.out_dir / "screen.csv", index=False)

        # Select top-k by CAGR among those meeting the full-period drawdown budget.
        ok = df_screen[
            np.isfinite(df_screen["max_drawdown"]) & (df_screen["max_drawdown"] >= -abs(float(args.dd_budget)))
        ].copy()
        ok = ok.sort_values("cagr", ascending=False).head(int(args.top_k))
        ok.to_csv(candidates_path, index=False)

    progress_path = args.out_dir / "robust_progress.csv"
    done_cfg_ids: set[int] = set()
    if bool(args.resume) and progress_path.exists():
        try:
            done_cfg_ids = set(int(x) for x in pd.read_csv(progress_path)["cfg_id"].dropna().unique())
            print(f"[resume] loaded {len(done_cfg_ids)} completed cfgs from {progress_path}")
        except Exception as e:
            print(f"[resume] failed to read {progress_path}: {e}")
            done_cfg_ids = set()

    robust: List[RobustRow] = []
    for _, row in ok.iterrows():
        cfg_id = int(row["cfg_id"])
        if cfg_id in done_cfg_ids:
            continue
        cfg = _cfg_from_row(row)
        cagr = []
        mdd = []
        pass_mdd = 0
        pass_cagr = 0
        for (a, b) in windows:
            f_sub = _subset_features(feats, a, b)
            r_sub = _subset_ret_m(ret_m, a, b)
            if len(r_sub.index) < int(args.train_months) + 6:
                continue
            res = _run_one(
                f_sub,
                ret_m=r_sub,
                cfg=cfg,
                benchmark=str(args.benchmark),
                cash_ticker=str(args.cash_ticker),
                train_months=int(args.train_months),
                cost_bps=float(args.cost_bps),
                lam_grid=[float(x) for x in args.lam_grid],
                min_assets=int(args.min_assets),
                vol_lookback=int(args.vol_lookback),
                regime_filter=bool(args.regime_filter),
                regime_window=int(args.regime_window),
                alpha_mode=str(args.alpha_mode),
                ic_months=int(args.ic_months),
                base=str(args.base),
            )
            p = res["perf"]
            c = float(p.get("cagr") or float("nan"))
            d = float(p.get("max_drawdown") or float("nan"))
            if np.isfinite(c) and np.isfinite(d):
                cagr.append(c)
                mdd.append(d)
                pass_mdd += int(d >= -abs(float(args.dd_budget)))
                pass_cagr += int(c > 0.0)
        if not cagr:
            continue
        rr = RobustRow(
            cfg_id=cfg_id,
            pass_mdd=float(pass_mdd) / float(len(cagr)),
            pass_cagr=float(pass_cagr) / float(len(cagr)),
            median_cagr=float(np.median(cagr)),
            median_mdd=float(np.median(mdd)),
            worst_mdd=float(np.min(mdd)),
            cfg=cfg,
        )
        robust.append(rr)
        print(f"[robust cfg={cfg_id}] med_cagr={rr.median_cagr:.3f} worst_mdd={rr.worst_mdd:.3f} pass_mdd={rr.pass_mdd:.2f}")

        # Incremental checkpoint to survive long runs / timeouts.
        row_out = {
            "cfg_id": rr.cfg_id,
            "pass_mdd": rr.pass_mdd,
            "pass_cagr": rr.pass_cagr,
            "median_cagr": rr.median_cagr,
            "median_mdd": rr.median_mdd,
            "worst_mdd": rr.worst_mdd,
            **rr.cfg,
        }
        pd.DataFrame([row_out]).to_csv(progress_path, mode="a", header=not progress_path.exists(), index=False)

    # Combine any prior progress with this run.
    if progress_path.exists():
        df_robust = pd.read_csv(progress_path)
    else:
        df_robust = pd.DataFrame(
            [
                {
                    "cfg_id": r.cfg_id,
                    "pass_mdd": r.pass_mdd,
                    "pass_cagr": r.pass_cagr,
                    "median_cagr": r.median_cagr,
                    "median_mdd": r.median_mdd,
                    "worst_mdd": r.worst_mdd,
                    **r.cfg,
                }
                for r in robust
            ]
        )
    if not df_robust.empty:
        # Enforce the constraint across sampled windows when selecting "best".
        dd_budget = abs(float(args.dd_budget))
        df_robust["_feasible"] = df_robust["worst_mdd"] >= -dd_budget
        df_feasible = df_robust[df_robust["_feasible"]].copy()
        # Rank by median CAGR, then worst drawdown (less negative is better).
        if not df_feasible.empty:
            df_robust = df_feasible.sort_values(["median_cagr", "worst_mdd"], ascending=[False, False])
        else:
            df_robust = df_robust.sort_values(["median_cagr", "worst_mdd"], ascending=[False, False])
    df_robust.to_csv(args.out_dir / "robust.csv", index=False)

    best = df_robust.head(1).to_dict(orient="records")[0] if not df_robust.empty else {}
    (args.out_dir / "best.json").write_text(json.dumps(best, indent=2))
    print("Best (constrained):", json.dumps(best, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
