#!/usr/bin/env python3
"""Run news/GDELT strategy variants through Sharpe-Renaissance promotion gates.

Uses existing fused panel + asia modeling trial helpers, writes equity_curve.csv
grid under backtests/outputs/news_strategy_grid/, then runs DSR/PBO/α gates
from scripts/promote_signal.py on every candidate.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))

from scripts.promote_signal import GateThresholds, run_gates  # noqa: E402
from src.research.fingerprint import make_fingerprint  # noqa: E402

FUSED_PANEL = (
    REPO
    / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
)
CRYPTO_PANEL = (
    REPO
    / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"
)
GLOBAL_PANEL = (
    REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
)
OUT_GRID = REPO / "backtests/outputs/news_strategy_grid"


def _load_trial():
    if str(REPO / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO / "scripts"))
    import run_asia_news_market_modeling_trial as trial  # noqa: WPS433

    return trial


def weekly_to_monthly_equity(weekly: pd.Series) -> pd.Series:
    s = weekly.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().fillna(0.0)
    equity = (1.0 + s).cumprod()
    return equity.resample("ME").last().dropna()


def write_equity_curve(path: Path, weekly_returns: pd.Series) -> Path:
    monthly = weekly_to_monthly_equity(weekly_returns)
    if len(monthly) < 2:
        monthly = pd.Series([1.0, 1.0], index=pd.to_datetime(["2020-01-31", "2020-02-29"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_frame("equity").to_csv(path)
    return path


def country_weekly_returns(df: pd.DataFrame, col: str) -> pd.Series:
    rows = []
    for week, group in df.groupby("week_end"):
        if col not in group.columns:
            continue
        val = group[col].iloc[0] if group[col].nunique() == 1 else float(group[col].mean())
        if np.isfinite(val):
            rows.append((week, val))
    if not rows:
        return pd.Series(dtype=float)
    out = pd.Series({w: v for w, v in rows})
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def build_country_strategies(trial, df: pd.DataFrame, preds: pd.DataFrame) -> dict[str, pd.Series]:
    df = trial.build_risk_scores(df)
    out: dict[str, pd.Series] = {}

    # Avoidance-style country baskets (fwd_return_1w cross-sectional rules).
    avoid_weekly = []
    for week, group in df.groupby("week_end"):
        sub = group[["country_iso3", "risk_score", "fwd_return_1w"]].dropna()
        if len(sub) < 8:
            continue
        eq = float(sub["fwd_return_1w"].mean())
        avoid = float(sub.nsmallest(max(1, len(sub) - 3), "risk_score")["fwd_return_1w"].mean())
        low = float(sub.nsmallest(max(1, len(sub) // 3), "risk_score")["fwd_return_1w"].mean())
        high = float(sub.nlargest(max(1, len(sub) // 3), "risk_score")["fwd_return_1w"].mean())
        avoid_weekly.append((week, eq, avoid, low, high))
    aw = pd.DataFrame(avoid_weekly, columns=["week_end", "eq", "avoid", "low", "high"]).set_index("week_end")
    for name, col in [
        ("country_eq_weight", "eq"),
        ("country_avoid_top3_risk", "avoid"),
        ("country_low_risk_tercile", "low"),
        ("country_high_risk_tercile", "high"),
    ]:
        out[name] = aw[col]

    # Walk-forward prediction baskets.
    pred_weekly = []
    for week, group in preds.groupby("week_end"):
        sub = group[["pred_fwd_return_1w", "fwd_return_1w", "risk_score"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 8 or sub["pred_fwd_return_1w"].nunique() < 3:
            continue
        top_n = max(1, len(sub) // 3)
        eq = float(sub["fwd_return_1w"].mean())
        top = float(sub.nlargest(top_n, "pred_fwd_return_1w")["fwd_return_1w"].mean())
        bottom = float(sub.nsmallest(top_n, "pred_fwd_return_1w")["fwd_return_1w"].mean())
        filt = sub[sub["risk_score"] <= sub["risk_score"].quantile(0.75)]
        top_f = (
            float(filt.nlargest(max(1, len(filt) // 3), "pred_fwd_return_1w")["fwd_return_1w"].mean())
            if len(filt) >= 5
            else float("nan")
        )
        pred_weekly.append((week, eq, top, bottom, top - bottom, top - eq, top_f))
    pw = pd.DataFrame(
        pred_weekly,
        columns=["week_end", "eq", "top", "bottom", "ls", "te", "top_f"],
    ).set_index("week_end")
    for name, col in [
        ("country_top_predicted", "top"),
        ("country_bottom_predicted", "bottom"),
        ("country_top_minus_bottom", "ls"),
        ("country_top_minus_equal", "te"),
        ("country_top_pred_ex_high_risk", "top_f"),
    ]:
        if col in pw.columns:
            out[name] = pw[col].dropna()

    return out


def build_crypto_strategies() -> dict[str, pd.Series]:
    g = pd.read_parquet(GLOBAL_PANEL)
    g["week_end"] = pd.to_datetime(g["week_end"])
    g = g.set_index("week_end").sort_index()
    btc = g["global_BTC-USD_fwd_return_1w"]
    eth = g["global_ETH-USD_fwd_return_1w"]
    base = 0.5 * btc + 0.5 * eth

    crypto = pd.read_parquet(CRYPTO_PANEL)
    crypto["week_end"] = pd.to_datetime(crypto["week_end"])
    asia_reg = crypto.groupby("week_end")["event_regulation_enforcement_per_1k_crypto_rows"].sum()
    ind_reg = crypto[crypto.country_iso3 == "IND"].groupby("week_end")["event_regulation_enforcement_per_1k_crypto_rows"].sum()
    hkg_reg = crypto[crypto.country_iso3 == "HKG"].groupby("week_end")["event_regulation_enforcement_per_1k_crypto_rows"].sum()
    exploit = crypto.groupby("week_end")["event_security_exploit_per_1k_crypto_rows"].sum()

    def z(s: pd.Series) -> pd.Series:
        sd = s.std(ddof=0)
        return (s - s.mean()) / sd if sd > 0 else s * 0.0

    z_asia = z(asia_reg)
    z_ind = z(ind_reg)
    z_hkg = z(hkg_reg)
    z_exp = z(exploit)

    idx = base.dropna().index
    b = base.reindex(idx)
    za = z_asia.reindex(idx).fillna(0)
    zi = z_ind.reindex(idx).fillna(0)
    zh = z_hkg.reindex(idx).fillna(0)
    ze = z_exp.reindex(idx).fillna(0)
    reg_scale = 1.0 - 0.25 * np.clip(za, 0, 2) / 2.0
    hkg_boost = 1.0 + np.where((zh > 1.0) & (ze > 1.0), 0.25, 0.0)

    out = {
        "crypto_btc_eth_50": b,
        "crypto_reg_scale_overlay": b * reg_scale,
        "crypto_asia_reg_short": pd.Series(np.where(za > 1.5, -b, 0.0), index=idx),
        "crypto_ind_reg_short": pd.Series(np.where(zi > 1.5, -b, 0.0), index=idx),
        "crypto_hkg_reg_exploit_long": b * hkg_boost,
    }
    return {k: v.dropna() for k, v in out.items() if not v.dropna().empty}


def perf_summary(weekly: pd.Series) -> dict:
    s = pd.to_numeric(weekly, errors="coerce").dropna()
    if s.empty:
        return {"weeks": 0}
    eq = (1 + s).cumprod()
    vol = float(s.std(ddof=1))
    return {
        "weeks": int(len(s)),
        "mean_weekly": float(s.mean()),
        "ann_return": float((eq.iloc[-1]) ** (52 / len(s)) - 1) if eq.iloc[-1] > 0 else float("nan"),
        "ann_vol": float(vol * math.sqrt(52)) if vol else float("nan"),
        "sharpe": float(s.mean() / vol * math.sqrt(52)) if vol else float("nan"),
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, default=FUSED_PANEL)
    p.add_argument("--out-grid", type=Path, default=OUT_GRID)
    p.add_argument("--min-train-weeks", type=int, default=52)
    p.add_argument("--ridge-alpha", type=float, default=10.0)
    p.add_argument("--dry-run", action="store_true", help="Do not treat as promotion; still run gates.")
    args = p.parse_args()

    trial = _load_trial()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = args.out_grid / run_id
    out_root.mkdir(parents=True, exist_ok=True)

    df = trial.build_risk_scores(trial.load_panel(args.panel))
    preds, wf_summary = trial.walk_forward(df, args.min_train_weeks, args.ridge_alpha)

    strategies: dict[str, pd.Series] = {}
    strategies.update(build_country_strategies(trial, df, preds))
    strategies.update(build_crypto_strategies())

    curves_written = []
    perf_rows = []
    for name, weekly in strategies.items():
        if weekly is None or weekly.dropna().empty:
            continue
        curve_path = write_equity_curve(out_root / name / "equity_curve.csv", weekly)
        curves_written.append(curve_path)
        perf_rows.append({"strategy": name, **perf_summary(weekly)})

    pd.DataFrame(perf_rows).sort_values("sharpe", ascending=False).to_csv(out_root / "weekly_perf_summary.csv", index=False)
    if not wf_summary.empty:
        wf_summary.to_csv(out_root / "walkforward_summary.csv", index=False)

    # Promotion gates vs full grid (same machinery as ridge alpha).
    thresholds = GateThresholds()
    gate_rows = []
    grid_pattern = "*/equity_curve.csv"
    for curve in curves_written:
        outcome = run_gates(
            candidate_curve=curve,
            grid_dir=out_root,
            grid_pattern=grid_pattern,
            thresholds=thresholds,
            factors_csv=None,
        )
        gate_rows.append(
            {
                "strategy": curve.parent.name,
                "passed": outcome.passed,
                "reasons": " | ".join(outcome.reasons),
                **outcome.metrics,
            }
        )

    gates_df = pd.DataFrame(gate_rows).sort_values("sharpe_per_period", ascending=False, na_position="last")
    gates_df.to_csv(out_root / "promotion_gates.csv", index=False)

    summary = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "panel": str(args.panel),
        "n_strategies": len(curves_written),
        "n_passed_promotion": int(gates_df["passed"].sum()) if not gates_df.empty else 0,
        "best_sharpe_weekly": perf_rows[0] if perf_rows else {},
        "fingerprint": make_fingerprint(config={"panel": str(args.panel), "run_id": run_id}),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(json.dumps(summary, indent=2, default=str))
    print("\nTop weekly Sharpe:")
    print(pd.DataFrame(perf_rows).sort_values("sharpe", ascending=False).head(8).to_string(index=False))
    print("\nPromotion gates:")
    print(gates_df[["strategy", "passed", "dsr", "pbo", "sharpe_per_period", "alpha_tstat_hac", "reasons"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
