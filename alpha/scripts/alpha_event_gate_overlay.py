#!/usr/bin/env python3
"""
Event-gated overlay for monthly alpha weights.

Main idea:
- Baseline: use monthly alpha weights (from positions.csv), forward-filled to daily.
- During dislocation regimes: temporarily override with a rebound/event sleeve.
- After dislocation cools: revert to baseline alpha automatically.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def load_panel(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    need = {"Instrument", "Date", "Price_Close"}
    if not need.issubset(df.columns):
        raise ValueError(f"Panel must include columns: {sorted(need)}")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Instrument", "Price_Close"]).sort_values(["Instrument", "Date"])
    return df


def wide(panel: pd.DataFrame, col: str) -> pd.DataFrame:
    return (
        panel.pivot_table(index="Date", columns="Instrument", values=col, aggfunc="last")
        .sort_index()
        .dropna(axis=0, how="all")
    )


def infer_cash_ticker(cols: List[str], user_cash: Optional[str]) -> Optional[str]:
    if user_cash and user_cash in cols:
        return user_cash
    for c in ["CASH", "BIL", "SHV", "SGOV"]:
        if c in cols:
            return c
    return None


def max_drawdown(eq: pd.Series) -> float:
    x = eq.astype(float)
    dd = x / x.cummax() - 1.0
    return float(dd.min())


def sharpe_daily(r: pd.Series) -> float:
    x = r.dropna().astype(float)
    if len(x) < 20:
        return float("nan")
    mu = float(x.mean())
    sd = float(x.std(ddof=1))
    if not np.isfinite(sd) or sd <= 1e-12:
        return float("nan")
    return float(mu / sd * math.sqrt(252.0))


def cagr(eq: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = float((end - start).days) / 365.25
    if years <= 0:
        return float("nan")
    s = float(eq.iloc[0])
    e = float(eq.iloc[-1])
    if s <= 0:
        return float("nan")
    return float((e / s) ** (1.0 / years) - 1.0)


def build_dislocation_gate(
    close: pd.DataFrame,
    volume: Optional[pd.DataFrame],
    benchmark: str,
    *,
    ret_z_on: float,
    ret_z_off: float,
    dvz_on: float,
    dvz_off: float,
    min_on_days: int,
    calm_off_days: int,
) -> pd.Series:
    idx = close.index
    if benchmark not in close.columns:
        raise ValueError(f"benchmark {benchmark} missing from panel")

    px = close[benchmark].astype(float).ffill()
    ret = px.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    vol20 = ret.rolling(20, min_periods=15).std(ddof=1).replace(0.0, np.nan)
    zret = (ret / vol20).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-20.0, 20.0)

    if volume is not None and benchmark in volume.columns:
        dv = (px * volume[benchmark].astype(float).reindex(idx).fillna(0.0)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        ldv = np.log1p(dv.clip(lower=0.0))
        mu = ldv.rolling(60, min_periods=30).mean()
        sd = ldv.rolling(60, min_periods=30).std(ddof=1).replace(0.0, np.nan)
        dvz = ((ldv - mu) / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-20.0, 20.0)
    else:
        dvz = pd.Series(0.0, index=idx)

    raw_on = (zret.abs() >= float(ret_z_on)) & (dvz >= float(dvz_on))
    raw_calm = (zret.abs() <= float(ret_z_off)) & (dvz <= float(dvz_off))

    gate = pd.Series(False, index=idx)
    on = False
    on_len = 0
    calm_len = 0
    for d in idx:
        if not on:
            if bool(raw_on.loc[d]):
                on = True
                on_len = 1
                calm_len = 0
        else:
            on_len += 1
            if bool(raw_calm.loc[d]):
                calm_len += 1
            else:
                calm_len = 0
            if on_len >= int(min_on_days) and calm_len >= int(calm_off_days):
                on = False
                on_len = 0
                calm_len = 0
        gate.loc[d] = on
    return gate


def score_event_rebound(close: pd.DataFrame, volume: Optional[pd.DataFrame], dt: pd.Timestamp, assets: List[str]) -> pd.Series:
    px = close[assets].loc[:dt].ffill()
    if len(px.index) < 260:
        return pd.Series(dtype=float)
    last = px.iloc[-1]
    ret21 = px.pct_change(21).iloc[-1]
    ret63 = px.pct_change(63).iloc[-1]
    dd21 = (px / px.rolling(21, min_periods=10).max() - 1.0).iloc[-1]
    up = (last > px.rolling(200, min_periods=120).mean().iloc[-1]).astype(float)

    dvz = pd.Series(0.0, index=assets)
    flow_only = pd.Series(0.0, index=assets)
    if volume is not None:
        vol = volume[assets].loc[:dt].fillna(0.0)
        dv = (px * vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        ldv = np.log1p(dv.clip(lower=0.0))
        mu = ldv.rolling(60, min_periods=30).mean()
        sd = ldv.rolling(60, min_periods=30).std(ddof=1).replace(0.0, np.nan)
        dvz_d = ((ldv - mu) / sd).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        dvz = dvz_d.iloc[-1]

        dret = px.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        dstd = dret.rolling(21, min_periods=15).std(ddof=1).replace(0.0, np.nan)
        zret = (dret / dstd).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        flow = dvz_d > 2.0
        flow_only = (flow & (zret.abs() < 1.0)).astype(float).rolling(21, min_periods=15).sum().iloc[-1].fillna(0.0)

    # same consensus shape: 70% core + 30% rebound timing
    def zcs(s: pd.Series) -> pd.Series:
        m = float(s.mean())
        sd = float(s.std(ddof=1))
        if not np.isfinite(sd) or sd <= 1e-12:
            return 0.0 * s
        return (s - m) / sd

    core = 1.0 * zcs(ret63.fillna(0.0)) + 0.5 * zcs(ret63.fillna(0.0))
    rebound = 1.0 * zcs((-ret21).fillna(0.0)) + 1.0 * zcs((-dd21).fillna(0.0)) + 0.5 * zcs(dvz) + 0.5 * zcs(flow_only)
    score = 0.7 * core + 0.3 * rebound

    ok = (last >= 5.0) & (up > 0.5) & (ret21 <= -0.03)
    return score.where(ok, np.nan).dropna().sort_values(ascending=False)


def build_daily_alpha_weights(positions_m: pd.DataFrame, daily_index: pd.DatetimeIndex, cols: List[str]) -> pd.DataFrame:
    pm = positions_m.copy()
    pm.index = pd.to_datetime(pm.index)
    pm = pm.sort_index()
    pm = pm.reindex(columns=cols).fillna(0.0)
    w = pm.reindex(daily_index, method="ffill").fillna(0.0)
    return w


def run_overlay(
    close: pd.DataFrame,
    volume: Optional[pd.DataFrame],
    alpha_w_daily: pd.DataFrame,
    gate: pd.Series,
    *,
    cash_ticker: Optional[str],
    backup_mode: str,
    backup_top_n: int,
    event_blend: float,
    defensive_cut: float,
    cost_bps: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    idx = close.index
    cols = list(close.columns)
    ret_d = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out_w = alpha_w_daily.copy()
    logs: List[Dict[str, object]] = []

    risky_cols = [c for c in cols if c != cash_ticker]
    for d in idx:
        if not bool(gate.loc[d]):
            continue
        sc = score_event_rebound(close, volume, d, risky_cols)
        picks = list(sc.index[: int(backup_top_n)])
        mode = str(backup_mode).lower().strip()
        if mode == "defensive_cash":
            w_alpha = alpha_w_daily.loc[d].copy()
            cut = float(np.clip(defensive_cut, 0.0, 1.0))
            w = w_alpha.copy()
            risky_positive = w[risky_cols].clip(lower=0.0)
            reduced = risky_positive * (1.0 - cut)
            delta = float(risky_positive.sum() - reduced.sum())
            w.loc[risky_cols] = reduced.values
            if cash_ticker and cash_ticker in cols:
                w.loc[cash_ticker] = float(w.get(cash_ticker, 0.0)) + delta
            out_w.loc[d] = w
            logs.append({"date": d, "mode": "defensive_cash", "defensive_cut": cut, "delta_to_cash": delta})
            continue

        if not picks:
            continue
        # preserve gross risky from alpha sleeve; fallback to 1.0
        alpha_risky_gross = float(alpha_w_daily.loc[d, risky_cols].clip(lower=0.0).sum())
        risky_gross = max(0.0, min(1.0, alpha_risky_gross if np.isfinite(alpha_risky_gross) and alpha_risky_gross > 0 else 1.0))
        w = pd.Series(0.0, index=cols)
        w.loc[picks] = risky_gross / float(len(picks))
        if cash_ticker and cash_ticker in cols:
            w.loc[cash_ticker] = 1.0 - risky_gross
        b = float(np.clip(event_blend, 0.0, 1.0))
        out_w.loc[d] = (1.0 - b) * alpha_w_daily.loc[d] + b * w
        logs.append({"date": d, "mode": "event_rebound", "n_picks": len(picks), "risky_gross": risky_gross, "picks": ";".join(picks)})

    # strategy returns
    turnover = out_w.diff().abs().sum(axis=1).fillna(0.0)
    cost = (float(cost_bps) / 10000.0) * turnover
    r = (out_w.shift(1).fillna(0.0) * ret_d).sum(axis=1) - cost
    eq = (1.0 + r).cumprod()

    # baseline alpha returns
    to_b = alpha_w_daily.diff().abs().sum(axis=1).fillna(0.0)
    cost_b = (float(cost_bps) / 10000.0) * to_b
    r_b = (alpha_w_daily.shift(1).fillna(0.0) * ret_d).sum(axis=1) - cost_b
    eq_b = (1.0 + r_b).cumprod()

    perf = pd.DataFrame(
        {
            "date": idx,
            "overlay_ret": r.values,
            "overlay_equity": eq.values,
            "baseline_ret": r_b.values,
            "baseline_equity": eq_b.values,
            "gate_on": gate.astype(int).values,
        }
    )
    log_df = pd.DataFrame(logs)
    return perf, log_df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--positions", type=Path, required=True, help="monthly positions.csv from alpha runner")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--cash-ticker", type=str, default="")
    ap.add_argument("--backup-mode", choices=["event_rebound", "defensive_cash"], default="event_rebound")
    ap.add_argument("--backup-top-n", type=int, default=10)
    ap.add_argument("--event-blend", type=float, default=0.35, help="Blend strength on gate days (0=off, 1=full switch).")
    ap.add_argument("--defensive-cut", type=float, default=0.35, help="For defensive_cash mode: cut risky gross by this fraction.")
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--ret-z-on", type=float, default=2.5)
    ap.add_argument("--ret-z-off", type=float, default=1.0)
    ap.add_argument("--dvz-on", type=float, default=1.5)
    ap.add_argument("--dvz-off", type=float, default=0.5)
    ap.add_argument("--min-on-days", type=int, default=5)
    ap.add_argument("--calm-off-days", type=int, default=5)
    args = ap.parse_args()

    panel = load_panel(args.panel)
    close = wide(panel, "Price_Close")
    volume = wide(panel, "Volume") if "Volume" in panel.columns else None

    pos_m = pd.read_csv(args.positions, index_col=0)
    pos_m.index = pd.to_datetime(pos_m.index)
    common_cols = [c for c in pos_m.columns if c in close.columns]
    if not common_cols:
        raise ValueError("No overlapping assets between positions and panel.")
    close = close[common_cols].copy()
    if volume is not None:
        volume = volume.reindex(columns=common_cols)
    pos_m = pos_m[common_cols].copy()

    cash = infer_cash_ticker(common_cols, args.cash_ticker or None)
    alpha_w = build_daily_alpha_weights(pos_m, close.index, common_cols)

    gate = build_dislocation_gate(
        close,
        volume,
        benchmark=str(args.benchmark),
        ret_z_on=float(args.ret_z_on),
        ret_z_off=float(args.ret_z_off),
        dvz_on=float(args.dvz_on),
        dvz_off=float(args.dvz_off),
        min_on_days=int(args.min_on_days),
        calm_off_days=int(args.calm_off_days),
    )
    perf, logs = run_overlay(
        close,
        volume,
        alpha_w,
        gate,
        cash_ticker=cash,
        backup_mode=str(args.backup_mode),
        backup_top_n=int(args.backup_top_n),
        event_blend=float(args.event_blend),
        defensive_cut=float(args.defensive_cut),
        cost_bps=float(args.cost_bps),
    )

    start = pd.Timestamp(perf["date"].iloc[0])
    end = pd.Timestamp(perf["date"].iloc[-1])
    eq_o = perf.set_index("date")["overlay_equity"]
    eq_b = perf.set_index("date")["baseline_equity"]
    r_o = perf.set_index("date")["overlay_ret"]
    r_b = perf.set_index("date")["baseline_ret"]

    summary = {
        "start": str(start.date()),
        "end": str(end.date()),
        "benchmark": str(args.benchmark),
        "cash_ticker": cash,
        "gate_days": int(perf["gate_on"].sum()),
        "gate_pct": float(perf["gate_on"].mean()),
        "backup_mode": str(args.backup_mode),
        "event_blend": float(args.event_blend),
        "defensive_cut": float(args.defensive_cut),
        "overlay": {
            "cagr": cagr(eq_o, start, end),
            "sharpe": sharpe_daily(r_o),
            "max_drawdown": max_drawdown(eq_o),
            "final_equity": float(eq_o.iloc[-1]),
        },
        "baseline": {
            "cagr": cagr(eq_b, start, end),
            "sharpe": sharpe_daily(r_b),
            "max_drawdown": max_drawdown(eq_b),
            "final_equity": float(eq_b.iloc[-1]),
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    perf.to_csv(args.out_dir / "equity_curve.csv", index=False)
    logs.to_csv(args.out_dir / "event_switch_log.csv", index=False)

    report = [
        "# Alpha Event Gate Overlay\n\n",
        "## Summary\n\n",
        "```json\n",
        json.dumps(summary, indent=2),
        "\n```\n",
    ]
    (args.out_dir / "report.md").write_text("".join(report))

    print(json.dumps(summary, indent=2))
    print(f"wrote: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
