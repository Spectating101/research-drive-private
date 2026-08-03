#!/usr/bin/env python3
"""Harder Taiwan OOS stress: walk-forward folds + cost grid vs equal core.

Does not treat a single 2024+ bull Sharpe as investable. Writes
backtests/outputs/taiwan_alpha_stress/.
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
OUT = REPO / "backtests/outputs/taiwan_alpha_stress"


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


def cost(prev: pd.Series, cur: pd.Series, bps: float) -> float:
    idx = prev.index.union(cur.index)
    return float((prev.reindex(idx).fillna(0) - cur.reindex(idx).fillna(0)).abs().sum()) * (bps / 10000.0)


def run_bt(
    close: pd.DataFrame,
    weight_fn: Callable,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp | None,
    cost_bps: float,
    rebalance: str = "W-FRI",
) -> dict[str, Any]:
    rets = close.pct_change().fillna(0.0)
    marks = close.resample(rebalance).last().dropna(how="all").index
    marks = marks[marks >= start]
    daily = close.index[close.index >= start]
    if end is not None:
        marks = marks[marks <= end]
        daily = daily[daily <= end]
    if len(marks) < 8 or len(daily) < 40:
        return {"ok": False, "reason": "short"}

    equity = 1.0
    curve = []
    prev_w = pd.Series(0.0, index=close.columns)
    w_by = {}
    for m in marks:
        hist = close.loc[:m]
        if len(hist) < 80:
            continue
        w = weight_fn(hist).reindex(close.columns).fillna(0.0)
        s = float(w.sum())
        if s > 0:
            w = w / s
        equity *= 1.0 - cost(prev_w, w, cost_bps)
        prev_w = w
        w_by[m] = w
    if not w_by:
        return {"ok": False, "reason": "no_w"}
    w_sched = pd.DataFrame(w_by).T.sort_index()
    w_daily = w_sched.reindex(daily, method="ffill").shift(1).fillna(0.0)
    for dt in daily:
        equity *= 1.0 + float((w_daily.loc[dt] * rets.loc[dt]).sum())
        curve.append(equity)
    if len(curve) < 30:
        return {"ok": False, "reason": "thin"}
    ser = pd.Series(curve)
    r = ser.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    ann = float(ser.iloc[-1] ** (252 / max(len(ser), 1)) - 1.0)
    mdd = float((ser / ser.cummax() - 1.0).min())
    return {
        "ok": True,
        "sharpe": round(sharpe, 3),
        "ann_return": round(ann, 4),
        "max_dd": round(mdd, 4),
        "terminal": round(float(ser.iloc[-1]), 4),
        "n_days": len(ser),
    }


def make_strats(close: pd.DataFrame, groups: dict) -> dict[str, Callable]:
    core = [t for t in groups.get("liquid_core", []) if t in close.columns]
    semis = [t for t in groups.get("groups", {}).get("semiconductors", {}).get("tickers", []) if t in close.columns]
    bench = groups.get("benchmark_etf", "0050.TW")

    def equal_core(hist):
        cols = [c for c in core if c in hist.columns] or list(hist.columns[:8])
        w = pd.Series(0.0, index=hist.columns)
        w.loc[cols] = 1.0 / len(cols)
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
        w = equal_core(hist)
        rets = hist.pct_change()
        bump = pd.Series(0.0, index=hist.columns)
        for g in groups.get("groups", {}).values():
            tickers = [t for t in g.get("tickers", []) if t in hist.columns]
            for dt in hist.index[-5:]:
                up = [t for t in tickers if float(rets.loc[dt, t]) >= 0.08]
                if len(up) >= 2:
                    for t in up:
                        bump[t] += 1.0
        if bump.sum() > 0:
            bump = bump / bump.sum() * 0.30
            w = w * 0.70 + bump
        return w

    def mom63(hist):
        if len(hist) < 70:
            return equal_core(hist)
        mom = (hist.iloc[-1] / hist.iloc[-64] - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        top = mom.nlargest(5).index
        w = pd.Series(0.0, index=hist.columns)
        w.loc[top] = 0.2
        return w

    return {
        "equal_liquid_core": equal_core,
        "regime_core": regime_core,
        "group_sync_tilt": group_sync_tilt,
        "mom63_top5": mom63,
    }


def main() -> int:
    close = load_close()
    groups = json.loads(GROUPS.read_text(encoding="utf-8"))
    strats = make_strats(close, groups)

    # Walk-forward: 3 contiguous OOS folds over last ~4y
    end = close.index[-1]
    folds = [
        ("2023H2", pd.Timestamp("2023-07-01"), pd.Timestamp("2023-12-31")),
        ("2024", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31")),
        ("2025+", pd.Timestamp("2025-01-01"), end),
    ]
    cost_grid = [20.0, 40.0, 80.0]

    fold_results: dict[str, dict[str, Any]] = {}
    for fname, start, fend in folds:
        fold_results[fname] = {}
        for sname, fn in strats.items():
            fold_results[fname][sname] = run_bt(close, fn, start=start, end=fend, cost_bps=20.0)

    cost_results: dict[str, dict[str, Any]] = {}
    for bps in cost_grid:
        cost_results[str(int(bps))] = {}
        for sname, fn in strats.items():
            cost_results[str(int(bps))][sname] = run_bt(
                close, fn, start=pd.Timestamp("2024-01-01"), end=None, cost_bps=bps
            )

    # Score: mean Sharpe across folds; require beat equal_core on majority of folds
    summary = {}
    for sname in strats:
        sh = []
        beats = 0
        for fname, _a, _b in folds:
            m = fold_results[fname].get(sname) or {}
            eq = fold_results[fname].get("equal_liquid_core") or {}
            if m.get("ok"):
                sh.append(m["sharpe"])
                if eq.get("ok") and m["sharpe"] > eq["sharpe"] + 0.05:
                    beats += 1
        mean_sh = float(np.mean(sh)) if sh else None
        cost80 = (cost_results.get("80") or {}).get(sname) or {}
        summary[sname] = {
            "mean_fold_sharpe": round(mean_sh, 3) if mean_sh is not None else None,
            "folds_ok": len(sh),
            "beats_equal_folds": beats,
            "cost80_sharpe": cost80.get("sharpe"),
            "cost80_max_dd": cost80.get("max_dd"),
        }

    # Verdict: group_sync must beat equal on >=2 folds AND survive 80bps with sharpe>=0.4
    gs = summary.get("group_sync_tilt") or {}
    if (
        (gs.get("beats_equal_folds") or 0) >= 2
        and (gs.get("cost80_sharpe") or -9) >= 0.4
        and (gs.get("mean_fold_sharpe") or -9) >= 0.5
    ):
        verdict = "stress_pass_candidate"
    elif (gs.get("mean_fold_sharpe") or -9) >= 0.5 and (gs.get("beats_equal_folds") or 0) >= 1:
        verdict = "stress_mixed_keep_research"
    else:
        verdict = "stress_fail_demote_to_beta"

    # Relative edge vs equal at 20bps 2024+
    edge = {}
    for sname in strats:
        a = (cost_results.get("20") or {}).get(sname) or {}
        b = (cost_results.get("20") or {}).get("equal_liquid_core") or {}
        if a.get("ok") and b.get("ok"):
            edge[sname] = round(a["sharpe"] - b["sharpe"], 3)

    report = {
        "market": "taiwan",
        "as_of": str(close.index[-1].date()),
        "verdict": verdict,
        "summary": summary,
        "sharpe_edge_vs_equal_20bps": edge,
        "folds": fold_results,
        "cost_grid_2024plus": cost_results,
        "note": "Walk-forward + cost stress. Bull market inflates absolute Sharpes; relative edge matters.",
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Taiwan alpha stress test",
        "",
        f"- as_of: `{report['as_of']}` · verdict: **`{verdict}`**",
        f"- group_sync mean fold Sharpe: {gs.get('mean_fold_sharpe')} · beats equal on {gs.get('beats_equal_folds')}/3 folds",
        f"- group_sync @ 80bps: Sharpe {gs.get('cost80_sharpe')} MaxDD {gs.get('cost80_max_dd')}",
        "",
        "## Fold Sharpes (20bps)",
        "",
        "| Strategy | 2023H2 | 2024 | 2025+ | Mean | Beats EQ |",
        "|----------|-------:|-----:|------:|-----:|---------:|",
    ]
    for sname in strats:
        cells = []
        for fname, _, _ in folds:
            m = fold_results[fname][sname]
            cells.append(f"{m['sharpe']:.2f}" if m.get("ok") else "—")
        s = summary[sname]
        lines.append(
            f"| {sname} | {cells[0]} | {cells[1]} | {cells[2]} | {s.get('mean_fold_sharpe')} | {s.get('beats_equal_folds')} |"
        )
    lines += ["", "## Cost grid 2024+ (Sharpe)", "", "| Strategy | 20bps | 40bps | 80bps |", "|----------|------:|------:|------:|"]
    for sname in strats:
        row = [sname]
        for b in ("20", "40", "80"):
            m = cost_results[b][sname]
            row.append(f"{m['sharpe']:.2f}" if m.get("ok") else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", f"Edge vs equal @20bps: `{edge}`", ""]
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print((OUT / "latest.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
