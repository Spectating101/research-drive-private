#!/usr/bin/env python3
"""Taiwan focused-market alpha research on expanded panel.

Horse-races: regime core, mom63, semi sleeve, group_sync, equal liquid.
Writes backtests/outputs/taiwan_alpha_research/latest.{json,md}
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

PANEL = REPO / "data_lake/markets/yfinance_asia/taiwan_expanded_daily_panel.parquet"
GROUPS = REPO / "config/markets/taiwan_stock_groups.json"
OUT = REPO / "backtests/outputs/taiwan_alpha_research"
COST_BPS = 20.0


def load_close() -> pd.DataFrame:
    df = pd.read_parquet(PANEL)
    cols = {c.lower(): c for c in df.columns}
    inst, date = cols["instrument"], cols["date"]
    close_c = cols.get("close") or cols.get("price_close")
    long = pd.DataFrame({
        "symbol": df[inst].astype(str),
        "date": pd.to_datetime(df[date]),
        "close": pd.to_numeric(df[close_c], errors="coerce"),
    }).dropna()
    return long.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()


def cost(prev: pd.Series, cur: pd.Series) -> float:
    idx = prev.index.union(cur.index)
    return float((prev.reindex(idx).fillna(0) - cur.reindex(idx).fillna(0)).abs().sum()) * (COST_BPS / 10000.0)


def run_bt(close: pd.DataFrame, weight_fn: Callable, oos_start: str, rebalance: str = "W-FRI") -> dict[str, Any]:
    rets = close.pct_change().fillna(0.0)
    # weekly rebalance marks
    marks = close.resample(rebalance).last().dropna(how="all").index
    marks = marks[marks >= pd.Timestamp(oos_start)]
    if len(marks) < 20:
        return {"ok": False, "reason": "short"}
    equity = 1.0
    curve = []
    prev_w = pd.Series(0.0, index=close.columns)
    daily_dates = close.index[close.index >= pd.Timestamp(oos_start)]
    # map each day to last rebalance weights
    w_by_day = {}
    for m in marks:
        hist = close.loc[:m]
        if len(hist) < 80:
            continue
        w = weight_fn(hist).reindex(close.columns).fillna(0.0)
        s = float(w.sum())
        if s > 0:
            w = w / s
        # apply cost on rebalance day
        equity *= 1.0 - cost(prev_w, w)
        prev_w = w
        w_by_day[m] = w
    if not w_by_day:
        return {"ok": False, "reason": "no_weights"}
    # daily mark with forward-filled weekly weights
    w_sched = pd.DataFrame(w_by_day).T.sort_index()
    w_daily = w_sched.reindex(daily_dates, method="ffill").shift(1).fillna(0.0)
    for dt in daily_dates:
        if dt not in w_daily.index:
            continue
        w = w_daily.loc[dt]
        equity *= 1.0 + float((w * rets.loc[dt]).sum())
        curve.append(equity)
    if len(curve) < 40:
        return {"ok": False, "reason": "thin"}
    ser = pd.Series(curve)
    r = ser.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    ann = float(ser.iloc[-1] ** (252 / len(ser)) - 1.0)
    mdd = float((ser / ser.cummax() - 1.0).min())
    return {
        "ok": True,
        "sharpe": round(sharpe, 3),
        "ann_return": round(ann, 4),
        "max_dd": round(mdd, 4),
        "terminal": round(float(ser.iloc[-1]), 4),
        "n_days": len(ser),
        "oos_start": oos_start,
    }


def main() -> int:
    close = load_close()
    groups = json.loads(GROUPS.read_text(encoding="utf-8"))
    core = [t for t in groups.get("liquid_core", []) if t in close.columns]
    semis = [t for t in groups["groups"]["semiconductors"]["tickers"] if t in close.columns]
    fin = [t for t in groups["groups"]["financials"]["tickers"] if t in close.columns]
    bench = groups.get("benchmark_etf", "0050.TW")

    def equal_core(hist):
        cols = [c for c in core if c in hist.columns]
        w = pd.Series(0.0, index=hist.columns)
        if cols:
            w.loc[cols] = 1.0 / len(cols)
        return w

    def semi_sleeve(hist):
        cols = [c for c in semis if c in hist.columns]
        w = pd.Series(0.0, index=hist.columns)
        if cols:
            w.loc[cols] = 1.0 / len(cols)
        return w

    def mom63(hist):
        if len(hist) < 70:
            return equal_core(hist)
        mom = hist.iloc[-1] / hist.iloc[-64] - 1.0
        mom = mom.replace([np.inf, -np.inf], np.nan).dropna()
        top = mom.nlargest(5).index
        w = pd.Series(0.0, index=hist.columns)
        w.loc[top] = 0.2
        return w

    def regime_core(hist):
        bcol = bench if bench in hist.columns else (core[0] if core else hist.columns[0])
        s = hist[bcol].dropna()
        if len(s) < 80:
            return equal_core(hist)
        last = float(s.iloc[-1])
        dd = last / float(s.iloc[-63:].max()) - 1.0
        bounce = last / float(s.iloc[-20:].min()) - 1.0
        if dd <= -0.10 and bounce < 0.08:
            sleeve = list(dict.fromkeys(core[:4] + semis[:3]))
            cash = 0.15
        elif bounce >= 0.12:
            sleeve = core[:3]
            cash = 0.40
        else:
            sleeve = core[:5]
            cash = 0.20
        sleeve = [c for c in sleeve if c in hist.columns]
        w = pd.Series(0.0, index=hist.columns)
        if sleeve:
            w.loc[sleeve] = (1.0 - cash) / len(sleeve)
        return w

    def group_sync_tilt(hist):
        """Equal core + overweight names with peer sync in last 5d."""
        w = equal_core(hist)
        rets = hist.pct_change()
        bump = pd.Series(0.0, index=hist.columns)
        for g in groups["groups"].values():
            tickers = [t for t in g["tickers"] if t in hist.columns]
            for dt in hist.index[-5:]:
                up = []
                for t in tickers:
                    r = float(rets.loc[dt, t]) if dt in rets.index else 0.0
                    if r >= 0.08:
                        up.append(t)
                if len(up) >= 2:
                    for t in up:
                        bump[t] += 1.0
        if bump.sum() > 0:
            bump = bump / bump.sum() * 0.30
            w = w * 0.70 + bump
        return w

    strats = {
        "equal_liquid_core": equal_core,
        "semi_sleeve": semi_sleeve,
        "mom63_top5": mom63,
        "regime_core": regime_core,
        "group_sync_tilt": group_sync_tilt,
    }
    oos = "2024-01-01"
    results = {k: run_bt(close, fn, oos) for k, fn in strats.items()}
    ranked = sorted([(k, v) for k, v in results.items() if v.get("ok")], key=lambda x: x[1]["sharpe"], reverse=True)
    best = ranked[0][0] if ranked else None
    verdict = "candidate_alpha" if ranked and ranked[0][1]["sharpe"] >= 0.6 else "research_continue"
    if ranked and ranked[0][1]["max_dd"] < -0.35:
        verdict = "research_continue_dd"

    report = {
        "market": "taiwan",
        "oos_start": oos,
        "best_strategy": best,
        "verdict": verdict,
        "horse_race": results,
        "ranked": [k for k, _ in ranked],
        "n_instruments": int(close.shape[1]),
        "as_of": str(close.index[-1].date()),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Taiwan alpha research",
        "",
        f"- as_of: `{report['as_of']}` · best: **{best}** · verdict: `{verdict}`",
        f"- OOS from `{oos}` · n={close.shape[1]} names",
        "",
        "| Strategy | Sharpe | Ann | MaxDD | Terminal |",
        "|----------|-------:|----:|------:|---------:|",
    ]
    for name, m in sorted(results.items(), key=lambda x: -(x[1].get("sharpe") or -99)):
        if not m.get("ok"):
            lines.append(f"| {name} | — | — | — | {m.get('reason')} |")
        else:
            lines.append(f"| {name} | {m['sharpe']:.2f} | {m['ann_return']:.1%} | {m['max_dd']:.1%} | {m['terminal']:.2f}× |")
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print((OUT / "latest.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
