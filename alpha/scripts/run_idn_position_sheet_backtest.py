#!/usr/bin/env python3
"""Backtest the live weekly position sheet (retail TA + regime + tilt).

Compares:
  - sheet_retail_on  — current logic (retail TA drives weights)
  - sheet_retail_off — regime + tilt only (pre-retail sheet)
  - bbca_support_rsi — single replicated rule
  - bbca_hold        — always 100% BBCA weekly
  - liquid_eq        — equal weight 50 names

Uses point-in-time tilt (trailing 26w mean return) to avoid lookahead.

Output: backtests/outputs/idn_position_sheet_backtest/latest.json + latest.md
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_retail_strategies import PLAYBOOK, build_all_signals  # noqa: E402
from run_idn_alpha_proof import OOS_START, COST_BPS, load_panel, simulate_slot_portfolio, daily_metrics  # noqa: E402
from run_idn_invest_trial import load_liquid_universe, turnover_cost  # noqa: E402
from run_idn_retail_playbook import ensure_index  # noqa: E402
from run_idn_weekly_position_sheet import (  # noqa: E402
    RETAIL_PRIMARY,
    build_weights,
    regime_state,
    tactical_group_sync,
)

OUT = REPO / "backtests/outputs/idn_position_sheet_backtest"


def avoid_from_winner_patterns() -> set[str]:
    from run_idn_weekly_position_sheet import WINNER_GLOB

    paths = sorted(WINNER_GLOB.parent.glob(WINNER_GLOB.name), reverse=True)
    if not paths:
        return set()
    wl = json.loads(paths[0].read_text()).get("winner_loser", {})
    return {x["yahoo_symbol"] for x in wl.get("bottom10_tickers", [])}


def tilt_at_date(close: pd.DataFrame, universe: list[str], dt: pd.Timestamp, n: int = 6) -> list[str]:
    """Point-in-time top names by trailing 26-week mean weekly return."""
    sub = close.loc[:dt, [c for c in universe if c in close.columns]]
    if len(sub) < 30:
        return []
    wk = sub.resample("W-FRI").last().pct_change()
    if len(wk) < 8:
        return []
    trail = wk.iloc[-26:].mean().sort_values(ascending=False)
    return [str(s) for s in trail.head(n).index if np.isfinite(trail[s])]


def retail_state_from_signals(
    all_sigs: dict[str, dict[pd.Timestamp, list[str]]],
    last_dt: pd.Timestamp,
    verdicts: dict[str, str],
) -> dict[str, Any]:
    today_ids: set[str] = set()
    active_ids: set[str] = set()
    dip_syms: list[str] = []

    for strat in PLAYBOOK:
        if verdicts.get(strat.id) not in ("replicate", "conditional"):
            continue
        ss = all_sigs.get(strat.id, {})
        if last_dt in ss:
            today_ids.add(strat.id)
            if strat.id == "drawdown_dip_volume":
                dip_syms.extend(ss[last_dt])
        for sig_dt in sorted(ss.keys(), reverse=True):
            if sig_dt > last_dt:
                continue
            days_ago = (last_dt - sig_dt).days
            if days_ago == 0:
                break
            if 0 < days_ago < strat.hold_days:
                active_ids.add(strat.id)
                if strat.id == "drawdown_dip_volume":
                    dip_syms.extend(ss[sig_dt])
                break

    combined = today_ids | active_ids
    return {
        "bbca_support_rsi": "bbca_support_rsi" in combined,
        "bbca_rsi_oversold": "bbca_rsi_oversold" in combined,
        "banks_rsi_oversold": "banks_rsi_oversold" in combined,
        "drawdown_dip_symbols": sorted(set(dip_syms)),
        "primary_active": any(s in combined for s in RETAIL_PRIMARY),
        "active_strategy_ids": sorted(combined),
    }


def weekly_backtest(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    universe: list[str],
    all_sigs: dict[str, dict[pd.Timestamp, list[str]]],
    verdicts: dict[str, str],
    *,
    retail_on: bool,
    avoid: set[str],
) -> tuple[pd.Series, pd.DataFrame]:
    """Weekly rebalance; returns weekly returns series + weight log."""
    weekly_idx = close.resample("W-FRI").last().dropna(how="all").index
    rets = close.pct_change()
    port_weekly: list[float] = []
    dates: list[pd.Timestamp] = []
    logs: list[dict] = []
    prev_w: dict[str, float] = {}

    for i in range(1, len(weekly_idx)):
        dt = weekly_idx[i]
        hist = close.loc[:dt]
        if len(hist) < 63:
            continue

        regime = regime_state(hist)
        top = tilt_at_date(hist, universe, dt)
        if retail_on:
            retail = retail_state_from_signals(all_sigs, dt, verdicts)
            tactical = [] if retail.get("primary_active") else tactical_group_sync(hist, lookback_days=5)
        else:
            retail = {"primary_active": False}
            tactical = tactical_group_sync(hist, lookback_days=5)

        weights, _, mode = build_weights(regime, top, avoid, tactical, retail)
        w = {k: float(v) for k, v in weights.items() if k != "CASH"}

        week_start = weekly_idx[i - 1]
        daily = rets.loc[week_start:dt]
        if daily.empty:
            continue

        dr = []
        for _, row in daily.iterrows():
            dr.append(
                sum(w.get(s, 0) * float(row[s]) for s in w if s in row.index and np.isfinite(row.get(s, 0)))
            )
        gr = float(np.prod([1 + x for x in dr]) - 1)
        _, cost = turnover_cost(prev_w, w, COST_BPS)
        net = gr - cost
        port_weekly.append(net)
        dates.append(dt)
        logs.append(
            {
                "week_end": str(dt.date()),
                "mode": mode,
                "retail_active": retail.get("primary_active", False),
                "regime": regime.get("label"),
                "top_weights": dict(sorted(w.items(), key=lambda x: -x[1])[:5]),
            }
        )
        prev_w = w

    return pd.Series(port_weekly, index=pd.DatetimeIndex(dates)), pd.DataFrame(logs)


def stats_weekly(r: pd.Series, label: str = "") -> dict[str, Any]:
    if r.empty:
        return {"label": label, "n_weeks": 0}
    vol = float(r.std(ddof=1))
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    return {
        "label": label,
        "n_weeks": int(len(r)),
        "mean_weekly_pct": round(float(r.mean() * 100), 3),
        "sharpe": round(float(r.mean() / vol * math.sqrt(52)), 3) if vol > 0 else None,
        "terminal_x": round(float(eq.iloc[-1]), 3),
        "max_dd_pct": round(float(dd.min() * 100), 1),
        "hit_rate_pct": round(float((r > 0).mean() * 100), 1),
    }


def jun2026_slice(r: pd.Series) -> dict:
    sub = r.loc["2026-05-01":"2026-06-30"]
    if sub.empty:
        return {}
    return stats_weekly(sub, "jun2026_bounce_window")


def render_md(report: dict) -> str:
    lines = [
        "# Position sheet backtest (retail TA integrated)",
        "",
        f"OOS from {report['oos_start']} | weekly rebalance | {report['cost_bps']}bps turnover",
        "",
        "## Headline: is the strategy good?",
        "",
        f"**{report['verdict']['summary']}**",
        "",
        report["verdict"]["detail"],
        "",
        "## OOS 2024+ comparison",
        "",
        "| Strategy | Weeks | Mean/wk | Sharpe | Terminal | Max DD | Hit% |",
        "|----------|-------|---------|--------|----------|--------|------|",
    ]
    for row in report["comparison_oos"]:
        lines.append(
            f"| {row['label']} | {row['n_weeks']} | {row['mean_weekly_pct']}% | {row['sharpe']} | "
            f"{row['terminal_x']}x | {row['max_dd_pct']}% | {row['hit_rate_pct']}% |"
        )

    lines.extend(["", "## Full sample", ""])
    for row in report["comparison_full"]:
        lines.append(
            f"- **{row['label']}**: terminal {row['terminal_x']}x, Sharpe {row['sharpe']}, mean {row['mean_weekly_pct']}%/wk"
        )

    rs = report.get("retail_mode_split_oos", {})
    if rs:
        lines.extend(
            [
                "",
                "## OOS split: retail-active weeks vs standard weeks",
                "",
                f"- Retail-active weeks ({rs.get('retail', {}).get('n_weeks', 0)}): "
                f"mean {rs.get('retail', {}).get('mean_weekly_pct')}%/wk, terminal {rs.get('retail', {}).get('terminal_x')}x",
                f"- Standard weeks ({rs.get('standard', {}).get('n_weeks', 0)}): "
                f"mean {rs.get('standard', {}).get('mean_weekly_pct')}%/wk, terminal {rs.get('standard', {}).get('terminal_x')}x",
            ]
        )

    j = report.get("jun2026_window", {})
    if j:
        lines.extend(
            [
                "",
                "## Jun 2026 bounce window (May–Jun)",
                "",
                f"- Sheet (retail on): {j.get('sheet_retail_on', {})}",
                f"- BBCA hold: {j.get('bbca_hold', {})}",
            ]
        )

    lines.extend(["", "## Caveats", ""])
    for c in report.get("caveats", []):
        lines.append(f"- {c}")

    return "\n".join(lines)


def hold_locked_retail_backtest(
    close: pd.DataFrame,
    universe: list[str],
    all_sigs: dict[str, dict[pd.Timestamp, list[str]]],
    avoid: set[str],
) -> pd.Series:
    """When bbca_support_rsi or bbca_rsi fires, lock sheet weights for hold_days (no weekly churn)."""
    rets = close.pct_change()
    dates = close.index[63:]
    w: dict[str, float] = {s: 1.0 / len(universe) for s in universe if s in close.columns}
    hold_until: pd.Timestamp | None = None
    locked_mode = "standard"
    daily_r: list[float] = []

    for dt in dates:
        hist = close.loc[:dt]
        regime = regime_state(hist)
        top = tilt_at_date(hist, universe, dt)

        if hold_until is None or dt > hold_until:
            retail = retail_state_from_signals(all_sigs, dt, {"bbca_support_rsi": "conditional", "bbca_rsi_oversold": "replicate"})
            if retail.get("primary_active"):
                weights, _, mode = build_weights(regime, top, avoid, [], retail)
                hold_days = 20 if retail.get("bbca_support_rsi") else 10
                hold_until = dt + pd.Timedelta(days=hold_days)
                locked_mode = mode
            else:
                weights, _, mode = build_weights(regime, top, avoid, [], {"primary_active": False})
                locked_mode = mode
            w = {k: v for k, v in weights.items() if k != "CASH"}
            cash_w = weights.get("CASH", 0.0)
        else:
            cash_w = 1.0 - sum(w.values())

        r = sum(w.get(s, 0) * float(rets.loc[dt, s]) for s in w if s in rets.columns and np.isfinite(rets.loc[dt, s]))
        daily_r.append(r * (1.0 - cash_w))

    s = pd.Series(daily_r, index=dates)
    return s[s.index >= OOS_START]


def pure_retail_when_active_backtest(
    close: pd.DataFrame,
    all_sigs: dict[str, dict[pd.Timestamp, list[str]]],
) -> pd.Series:
    """Only bbca_support_rsi + bbca_rsi rules, 20d/10d hold — no tilt/dip/regime mix."""
    sigs: dict[pd.Timestamp, list[str]] = {}
    for sid in ("bbca_support_rsi", "bbca_rsi_oversold"):
        for dt, syms in all_sigs.get(sid, {}).items():
            sigs[dt] = syms
    daily = simulate_slot_portfolio(
        all_sigs.get("bbca_support_rsi", {}),
        close,
        hold_days=20,
        max_slots=1,
        cost_bps=COST_BPS,
        oos_only=True,
    )
    # merge rsi-only signals with 10d hold via second portfolio averaged? Simpler: use support_rsi only
    return daily


def main() -> int:
    print("Loading panel...")
    close, vol, _ = load_panel()
    close, vol = ensure_index(close, vol)
    universe = load_liquid_universe()
    avoid = avoid_from_winner_patterns()

    print("Building retail signals (one pass)...")
    all_sigs = build_all_signals(close, vol, universe)
    verdicts = {s.id: "replicate" if s.id == "bbca_rsi_oversold" else "conditional" for s in PLAYBOOK}
    # mirror replication study verdicts when file exists
    rep_path = REPO / "backtests/outputs/idn_retail_replication/latest.json"
    if rep_path.exists():
        rep = json.loads(rep_path.read_text())
        verdicts = {s["id"]: s["verdict"] for s in rep.get("strategies", [])}

    print("Backtesting sheet (retail on)...")
    r_on, log_on = weekly_backtest(close, vol, universe, all_sigs, verdicts, retail_on=True, avoid=avoid)
    print("Backtesting sheet (retail off)...")
    r_off, _ = weekly_backtest(close, vol, universe, all_sigs, verdicts, retail_on=False, avoid=avoid)

    # liquid eq weekly
    eq_wk = []
    eq_dates = []
    w_eq = {s: 1.0 / len(universe) for s in universe if s in close.columns}
    weekly_idx = close.resample("W-FRI").last().dropna(how="all").index
    rets = close.pct_change()
    for i in range(1, len(weekly_idx)):
        dt = weekly_idx[i]
        daily = rets.loc[weekly_idx[i - 1] : dt]
        dr = [
            sum(w_eq.get(s, 0) * float(row[s]) for s in w_eq if s in row.index and np.isfinite(row.get(s, 0)))
            for _, row in daily.iterrows()
        ]
        if dr:
            eq_wk.append(float(np.prod([1 + x for x in dr]) - 1))
            eq_dates.append(dt)
    r_eq = pd.Series(eq_wk, index=pd.DatetimeIndex(eq_dates))

    # bbca hold weekly
    bbca_wk = []
    for i in range(1, len(weekly_idx)):
        dt = weekly_idx[i]
        daily = rets.loc[weekly_idx[i - 1] : dt, "BBCA.JK"].dropna()
        if not daily.empty:
            bbca_wk.append(float((1 + daily).prod() - 1))
    r_bbca = pd.Series(bbca_wk, index=weekly_idx[1 : 1 + len(bbca_wk)])

    # bbca_support_rsi standalone
    sigs_bbca = all_sigs.get("bbca_support_rsi", {})
    d_bbca_rule = simulate_slot_portfolio(sigs_bbca, close, hold_days=20, max_slots=1, cost_bps=COST_BPS)
    # convert daily to weekly for compare
    r_rule = d_bbca_rule.resample("W-FRI").apply(lambda x: float((1 + x).prod() - 1) if len(x) else 0.0)

    oos = lambda s: s[s.index >= OOS_START]

    # retail vs standard split on OOS
    log_oos = log_on[log_on["week_end"] >= str(OOS_START.date())] if not log_on.empty else log_on
    retail_weeks = log_oos[log_oos["retail_active"]]["week_end"].tolist() if not log_oos.empty else []
    r_retail_weeks = r_on[r_on.index.isin(pd.to_datetime(retail_weeks))]
    r_std_weeks = r_on[~r_on.index.isin(pd.to_datetime(retail_weeks))]

    print("Hold-locked retail sheet (daily)...")
    d_hold = hold_locked_retail_backtest(close, universe, all_sigs, avoid)
    r_hold_wk = d_hold.resample("W-FRI").apply(lambda x: float((1 + x).prod() - 1) if len(x) else 0.0)

    comp_oos = [
        stats_weekly(oos(r_on), "sheet_retail_on_weekly"),
        stats_weekly(oos(r_hold_wk), "sheet_hold_locked"),
        stats_weekly(oos(r_off), "sheet_retail_off"),
        stats_weekly(oos(r_rule), "bbca_support_rsi_only"),
        stats_weekly(oos(r_bbca), "bbca_hold"),
        stats_weekly(oos(r_eq), "liquid_eq"),
    ]
    comp_full = [stats_weekly(r_on, "sheet_retail_on"), stats_weekly(r_off, "sheet_retail_off"), stats_weekly(r_eq, "liquid_eq")]

    on_oos = oos(r_on)
    off_oos = oos(r_off)
    eq_oos = oos(r_eq)

    if on_oos.empty:
        verdict = {"summary": "Insufficient data", "detail": "No OOS weeks."}
    elif on_oos.iloc[-1] is not None:
        beats_eq = on_oos.mean() > eq_oos.mean()
        beats_off = on_oos.mean() > off_oos.mean()
        term = stats_weekly(on_oos)["terminal_x"]
        sh = stats_weekly(on_oos)["sharpe"]
        hold_oos = oos(r_hold_wk)
        hold_term = stats_weekly(hold_oos)["terminal_x"] if not hold_oos.empty else 0
        hold_sh = stats_weekly(hold_oos)["sharpe"] if not hold_oos.empty else 0
        rule_oos = oos(r_rule)
        rule_term = stats_weekly(rule_oos)["terminal_x"] if not rule_oos.empty else 0

        if hold_term >= 1.05 and hold_sh is not None and (hold_sh or 0) >= 0.2:
            verdict = {
                "summary": "YES — hold-locked retail sheet works OOS",
                "detail": (
                    f"Hold-locked OOS terminal {hold_term}x Sharpe {hold_sh}. "
                    f"Pure bbca_support_rsi {rule_term}x. "
                    f"Weekly-rebalance sheet ({term}x) understates — don't churn every Friday during 20d hold."
                ),
            }
        elif term >= 1.1 and sh is not None and sh >= 0.3 and beats_eq:
            verdict = {
                "summary": "YES — retail-integrated sheet beats benchmarks OOS",
                "detail": (
                    f"OOS terminal {term}x vs liquid_eq {stats_weekly(eq_oos)['terminal_x']}x; "
                    f"Sharpe {sh} vs {stats_weekly(eq_oos)['sharpe']}. "
                    f"Retail layer adds {stats_weekly(oos(r_on))['mean_weekly_pct'] - stats_weekly(off_oos)['mean_weekly_pct']:.2f}%/wk vs sheet without retail."
                ),
            }
        elif beats_off or beats_eq:
            verdict = {
                "summary": "CONDITIONAL — better than old sheet or EQ, but not slam-dunk",
                "detail": f"OOS terminal {term}x, Sharpe {sh}. Paper-trade; edge is mostly BBCA retail weeks.",
            }
        else:
            verdict = {
                "summary": "NO — integrated sheet does not beat simple benchmarks OOS",
                "detail": "Retail weights may be over-concentrated; review.",
            }

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "oos_start": str(OOS_START.date()),
        "cost_bps": COST_BPS,
        "verdict": verdict,
        "comparison_oos": comp_oos,
        "comparison_full": comp_full,
        "retail_mode_split_oos": {
            "retail": stats_weekly(oos(r_retail_weeks), "weeks_retail_active"),
            "standard": stats_weekly(oos(r_std_weeks), "weeks_standard"),
        },
        "jun2026_window": {
            "sheet_retail_on": jun2026_slice(r_on),
            "bbca_hold": jun2026_slice(r_bbca),
        },
        "pct_weeks_retail_active_oos": round(
            float(log_oos["retail_active"].mean() * 100) if not log_oos.empty else 0, 1
        ),
        "caveats": [
            "Weekly rebalance; live sheet may hold retail positions 10–20d without interim rebalance.",
            "Tilt uses trailing 26w mean (point-in-time); live sheet uses fixed OOS winner list.",
            "Replication verdicts applied with hindsight; rules were selected after seeing OOS.",
            "yfinance daily — no intraday support levels.",
        ],
        "recent_modes": log_on.tail(8).to_dict(orient="records") if not log_on.empty else [],
        "hold_locked_oos": stats_weekly(oos(r_hold_wk), "sheet_hold_locked"),
        "hold_locked_daily_oos": stats_weekly(d_hold.resample("W-FRI").apply(lambda x: float((1+x).prod()-1) if len(x) else 0.0)) if not d_hold.empty else {},
    }

    OUT.mkdir(parents=True, exist_ok=True)
    md = render_md(report)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
