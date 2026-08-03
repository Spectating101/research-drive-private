#!/usr/bin/env python3
"""Explore OOS winner/loser patterns across the full IDX tradable universe + rule horse race."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
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
sys.path.insert(0, str(REPO / "scripts"))

from quant_ai.pipeline import SHOCKS  # noqa: E402
from idn_eval_splits import time_cutoff  # noqa: E402
from idn_panel_lib import load_research_universe  # noqa: E402
from run_idn_invest_trial import pick_holdings, turnover_cost  # noqa: E402

BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
OUT = REPO / "backtests/outputs/idn_invest/patterns"
TARGET = "fwd_return_1w"
OOS_FRAC = 0.25


@dataclass
class StratPerf:
    name: str
    n_weeks: int
    mean_weekly_pct: float
    hit_pct: float
    sharpe: float
    terminal_x: float
    beat_eq_pct: float


def perf_weekly(r: pd.Series, eq_weekly: pd.Series | None = None) -> StratPerf:
    r = r.dropna()
    if r.empty:
        return StratPerf("?", 0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    vol = float(r.std(ddof=1))
    beat = float((r > eq_weekly.reindex(r.index)).mean() * 100) if eq_weekly is not None else float("nan")
    return StratPerf(
        name="",
        n_weeks=len(r),
        mean_weekly_pct=float(r.mean() * 100),
        hit_pct=float((r > 0).mean() * 100),
        sharpe=float(r.mean() / vol * math.sqrt(52)) if vol > 0 else float("nan"),
        terminal_x=float((1 + r).prod()),
        beat_eq_pct=beat,
    )


def load_panel(symbols: list[str]) -> pd.DataFrame:
    b = pd.read_parquet(BROADCAST)
    b["week_end"] = pd.to_datetime(b["week_end"])
    b = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(symbols))].copy()
    b = b.sort_values(["yahoo_symbol", "week_end"])
    # Momentum / reversal features from realized returns
    for col, win in [("mom_4w", 4), ("mom_12w", 12), ("rev_1w", 1)]:
        if col == "rev_1w":
            b[col] = b.groupby("yahoo_symbol")["return_1w"].shift(1)
        else:
            b[col] = (
                b.groupby("yahoo_symbol")["return_1w"]
                .rolling(win, min_periods=max(2, win // 2))
                .sum()
                .reset_index(level=0, drop=True)
                .shift(1)
            )
    shock_cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in b.columns]
    b["news_risk_sum"] = b[shock_cols].fillna(0).sum(axis=1)
    b["news_risk_z"] = b.groupby("week_end")["news_risk_sum"].transform(
        lambda x: (x - x.mean()) / x.std(ddof=0) if x.std(ddof=0) > 0 else 0.0
    )
    return b


def oos_mask(df: pd.DataFrame) -> pd.Series:
    cut = time_cutoff(df["week_end"], oos_frac=OOS_FRAC)
    return df["week_end"] >= cut


def winner_loser_tables(df: pd.DataFrame) -> dict:
    oos = df[oos_mask(df)]
    per_ticker = (
        oos.groupby("yahoo_symbol")
        .agg(
            mean_1w=(TARGET, "mean"),
            vol_1w=(TARGET, "std"),
            weeks=(TARGET, "count"),
            mean_mom4=("mom_4w", "mean"),
            mean_mom12=("mom_12w", "mean"),
            mean_news_risk=("news_risk_sum", "mean"),
        )
        .sort_values("mean_1w", ascending=False)
    )
    top = per_ticker.head(20).reset_index().to_dict(orient="records")
    bottom = per_ticker.tail(20).reset_index().to_dict(orient="records")
    return {
        "top20_tickers": top,
        "bottom20_tickers": bottom,
        "top10_tickers": top[:10],
        "bottom10_tickers": bottom[:10],
        "news_risk_note": (
            "mean_news_risk is country-level broadcast shock sum (IDN), identical across tickers — "
            "not ticker-attributed news. Do not use for stock selection."
        ),
    }


def cross_sectional_correlations(df: pd.DataFrame) -> list[dict]:
    oos = df[oos_mask(df)]
    feats = ["mom_4w", "mom_12w", "rev_1w", "news_risk_sum", "mean_tone_weighted", "return_1w"]
    feats += [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in oos.columns]
    rows = []
    for week, g in oos.groupby("week_end"):
        sub = g[feats + [TARGET]].dropna()
        if len(sub) < 15:
            continue
        for f in feats:
            if f not in sub.columns:
                continue
            c = sub[f].corr(sub[TARGET])
            if np.isfinite(c):
                rows.append({"week_end": week, "feature": f, "corr": float(c)})
    if not rows:
        return []
    wk = pd.DataFrame(rows)
    agg = (
        wk.groupby("feature")["corr"]
        .agg(["mean", "std", "count", lambda s: float((s > 0).mean())])
        .reset_index()
    )
    agg.columns = ["feature", "mean_corr", "std_corr", "n_weeks", "pct_positive_weeks"]
    agg = agg.sort_values("mean_corr", key=abs, ascending=False)
    return agg.head(15).to_dict(orient="records")


def simulate_rules(df: pd.DataFrame, cost_bps: float = 25.0) -> list[dict]:
    """Weekly cross-sectional rules — all use only past info at week_end."""
    weeks = sorted(df["week_end"].dropna().unique())
    oos_cut = time_cutoff(df["week_end"], oos_frac=OOS_FRAC)
    strategies: dict[str, list[float]] = {k: [] for k in [
        "liquid_eq", "mom4_top5", "mom12_top5", "mom4_top5_low_news",
        "mom4_bottom5", "low_vol_top5", "banks_top3", "commodity_proxy_top3",
    ]}
    prev_w: dict[str, dict[str, float]] = {k: {} for k in strategies}

    banks = {"BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BBTN.JK", "BRIS.JK", "ARTO.JK"}
    commodities = {"ADRO.JK", "PTBA.JK", "ITMG.JK", "ANTM.JK", "INCO.JK", "MDKA.JK", "PGAS.JK", "MEDC.JK", "BYAN.JK"}

    for week in weeks:
        g = df[df["week_end"] == week].dropna(subset=[TARGET])
        if len(g) < 10:
            continue

        def pack_weights(selected: pd.DataFrame) -> dict[str, float]:
            if selected.empty:
                return {}
            w = 1.0 / len(selected)
            return {str(r.yahoo_symbol): w for r in selected.itertuples()}

        def port_return(weights: dict[str, float]) -> float:
            if not weights:
                return 0.0
            m = g.set_index("yahoo_symbol")[TARGET]
            return float(sum(weights[s] * m.get(s, 0.0) for s in weights if s in m.index))

        picks = {
            "liquid_eq": pack_weights(g),
            "mom4_top5": pack_weights(g.dropna(subset=["mom_4w"]).nlargest(5, "mom_4w")),
            "mom12_top5": pack_weights(g.dropna(subset=["mom_12w"]).nlargest(5, "mom_12w")),
            "mom4_top5_low_news": pack_weights(
                g.dropna(subset=["mom_4w"]).nlargest(10, "mom_4w").nsmallest(5, "news_risk_sum")
            ),
            "mom4_bottom5": pack_weights(g.dropna(subset=["mom_4w"]).nsmallest(5, "mom_4w")),
            "low_vol_top5": {},
        }
        g2 = g.dropna(subset=["vol_12w"])
        if len(g2) >= 5:
            picks["low_vol_top5"] = pack_weights(g2.nsmallest(5, "vol_12w"))

        gb = g[g["yahoo_symbol"].isin(banks)].dropna(subset=[TARGET])
        picks["banks_top3"] = pack_weights(gb.nlargest(3, "mom_4w") if "mom_4w" in gb.columns else gb.head(3))

        gc = g[g["yahoo_symbol"].isin(commodities)].dropna(subset=["mom_4w"])
        picks["commodity_proxy_top3"] = pack_weights(gc.nlargest(3, "mom_4w"))

        for name, w in picks.items():
            gr = port_return(w)
            if week >= oos_cut:
                _, cost = turnover_cost(prev_w[name], w, cost_bps)
                strategies[name].append(gr - cost)
            prev_w[name] = w

    eq_s = pd.Series(strategies["liquid_eq"], dtype=float)
    out = []
    for name, rets in strategies.items():
        s = pd.Series(rets, dtype=float)
        p = perf_weekly(s, eq_s if name != "liquid_eq" else None)
        p.name = name
        out.append(asdict(p) | {"name": name})
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--universe",
        choices=["liquid", "tradable", "merged"],
        default="tradable",
        help="Symbol universe (default: full tradable ~635 names)",
    )
    args = ap.parse_args()

    symbols = load_research_universe(mode=args.universe)
    df = load_panel(symbols)
    # 12w vol per symbol
    df["vol_12w"] = (
        df.groupby("yahoo_symbol")["return_1w"]
        .rolling(12, min_periods=6)
        .std()
        .reset_index(level=0, drop=True)
        .shift(1)
    )

    OUT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    oos_cut = time_cutoff(df["week_end"], oos_frac=OOS_FRAC)
    report = {
        "run_id": run_id,
        "oos_frac": OOS_FRAC,
        "oos_start": str(oos_cut.date()),
        "universe_mode": args.universe,
        "universe_size": len(symbols),
        "winner_loser": winner_loser_tables(df),
        "cross_sectional_correlations": cross_sectional_correlations(df),
        "strategy_horse_race_oos": simulate_rules(df),
    }

    # Load ridge top5 from cache for comparison
    cache = REPO / "backtests/outputs/idn_invest/_latest_preds_cache.csv"
    if cache.exists():
        preds = pd.read_csv(cache, parse_dates=["week_end"])
        preds = preds[preds.week_end >= oos_cut]
        rets = []
        prev: dict[str, float] = {}
        eq = []
        for week, g in preds.groupby("week_end"):
            w5 = pick_holdings(g, "top5", 5)
            weq = pick_holdings(g, "liquid_eq", 5)
            m = g.set_index("yahoo_symbol")
            r5 = sum(w5.get(s, 0) * m.loc[s, TARGET] for s in w5 if s in m.index)
            req = g[TARGET].mean()
            _, cost = turnover_cost(prev, w5, 25.0)
            rets.append(r5 - cost)
            eq.append(req)
            prev = w5
        s = pd.Series(rets)
        eqs = pd.Series(eq)
        p = perf_weekly(s, eqs)
        report["strategy_horse_race_oos"].append(
            asdict(p)
            | {"name": "ridge_news_top5", "beat_eq_pct": float((s > eqs).mean() * 100)}
        )

    out_path = OUT / f"winner_patterns_{run_id}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== OOS ticker winners/losers (mean weekly fwd 1w) ===")
    for row in report["winner_loser"]["top10_tickers"][:8]:
        print(f"  {row['yahoo_symbol']:10} {row['mean_1w']*100:+5.2f}%/wk  mom4={row.get('mean_mom4',0)*100:+.1f}%")
    print("  ...")
    for row in report["winner_loser"]["bottom10_tickers"][-5:]:
        print(f"  {row['yahoo_symbol']:10} {row['mean_1w']*100:+5.2f}%/wk")

    print("\n=== Cross-sectional signal (avg weekly corr with NEXT week return, OOS) ===")
    for row in report["cross_sectional_correlations"][:8]:
        print(
            f"  {row['feature']:28} mean_corr={row['mean_corr']:+.3f}  "
            f"positive weeks {row['pct_positive_weeks']*100:.0f}%"
        )

    print(f"\n=== Strategy horse race OOS (net ~25bps turnover) ===")
    print(f"{'strategy':22} | {'wk%':>6} | {'hit':>4} | {'sharpe':>6} | {'$1→':>5} | {'beat_EQ':>7}")
    print("-" * 65)
    for row in sorted(report["strategy_horse_race_oos"], key=lambda x: x.get("terminal_x", 0), reverse=True):
        print(
            f"{row['name']:22} | {row['mean_weekly_pct']:+5.2f}% | {row['hit_pct']:4.0f}% | "
            f"{row['sharpe']:6.2f} | {row['terminal_x']:5.2f}x | {row.get('beat_eq_pct', float('nan')):6.0f}%"
        )

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
