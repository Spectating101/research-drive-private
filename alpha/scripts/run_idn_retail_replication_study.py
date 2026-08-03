#!/usr/bin/env python3
"""Full replication study for IDX retail / influencer TA strategies.

Produces evidence pack with:
  - Event studies (fwd 5/10/20d) IS vs OOS
  - Portfolio simulation per rule
  - Replication verdict (replicate / conditional / reject)
  - Parameter sensitivity on top rule (BBCA support)
  - Bootstrap 95% CI on OOS mean trade return (top rules)

Output:
  backtests/outputs/idn_retail_replication/latest.json
  backtests/outputs/idn_retail_replication/latest.md
  docs/IDN_RETAIL_REPLICATION.md (generated summary)

Run:
  PYTHONPATH=$PWD:$PWD/scripts python3 scripts/run_idn_retail_replication_study.py
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

from idn_retail_strategies import (  # noqa: E402
    INDEX,
    PLAYBOOK,
    build_all_signals,
    event_study,
    replication_verdict,
)
from run_idn_alpha_proof import (  # noqa: E402
    OOS_START,
    COST_BPS,
    daily_metrics,
    load_panel,
    simulate_equal_weight_monthly,
    simulate_slot_portfolio,
)
from run_idn_retail_playbook import ensure_index  # noqa: E402

OUT = REPO / "backtests/outputs/idn_retail_replication"
DOCS = REPO / "docs/IDN_RETAIL_REPLICATION.md"
IS_END = pd.Timestamp("2023-12-31")
BOOTSTRAP_N = 2000


def portfolio_for_rule(
    rule_id: str,
    signals: dict[pd.Timestamp, list[str]],
    close: pd.DataFrame,
    hold_days: int,
    max_slots: int,
) -> tuple[dict, dict]:
    """Full + OOS-only portfolio metrics."""
    daily_all = simulate_slot_portfolio(
        signals, close, hold_days=hold_days, max_slots=max_slots, cost_bps=COST_BPS, oos_only=False
    )
    daily_oos = simulate_slot_portfolio(
        signals, close, hold_days=hold_days, max_slots=max_slots, cost_bps=COST_BPS, oos_only=True
    )
    oos_slice = daily_all[daily_all.index >= OOS_START] if not daily_all.empty else daily_oos
    return daily_metrics(daily_all), daily_metrics(oos_slice)


def bootstrap_mean_return(daily: pd.Series, n_iter: int = BOOTSTRAP_N, seed: int = 42) -> dict:
    r = daily.dropna()
    if len(r) < 10:
        return {"available": False}
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_iter):
        samp = r.iloc[rng.integers(0, len(r), size=len(r))]
        means.append(float(samp.mean()))
    arr = np.array(means)
    return {
        "available": True,
        "n_days": len(r),
        "mean_daily_pct": round(float(r.mean() * 100), 4),
        "ci95_low_pct": round(float(np.percentile(arr, 2.5) * 100), 4),
        "ci95_high_pct": round(float(np.percentile(arr, 97.5) * 100), 4),
    }


def sensitivity_bbca_support(close: pd.DataFrame, vol: pd.DataFrame) -> list[dict]:
    """Grid on lookback + RSI threshold for BBCA support rule."""
    from api.intelligence.technical_indicators import TechnicalIndicators

    if "BBCA.JK" not in close.columns:
        return []
    px = close["BBCA.JK"]
    r = TechnicalIndicators.calculate_rsi(px)
    rows = []
    for lookback in (40, 60, 90):
        for rsi_max in (30, 35, 40):
            for prox in (0.02, 0.03):
                sigs: dict[pd.Timestamp, list[str]] = {}
                for dt in px.index[lookback:]:
                    loc = px.index.get_loc(dt)
                    last = float(px.loc[dt])
                    low = float(px.iloc[loc - lookback : loc + 1].min())
                    rv = float(r.loc[dt]) if dt in r.index else np.nan
                    if low > 0 and last <= low * (1 + prox) and np.isfinite(rv) and rv < rsi_max:
                        sigs[dt] = ["BBCA.JK"]
                if not sigs:
                    continue
                d_oos = simulate_slot_portfolio(sigs, close, hold_days=20, max_slots=1, cost_bps=COST_BPS)
                m = daily_metrics(d_oos)
                ev = event_study(sigs, close, hold_days_list=(20,), oos_start=OOS_START)
                rows.append(
                    {
                        "lookback": lookback,
                        "rsi_max": rsi_max,
                        "proximity_pct": prox * 100,
                        "n_signals": len(sigs),
                        "oos_terminal_x": m.get("terminal_x"),
                        "oos_sharpe": m.get("sharpe"),
                        "oos_event_20d_mean": ev.get("by_horizon", {}).get("oos_20d", {}).get("mean_pct"),
                    }
                )
    return sorted(rows, key=lambda x: (-(x.get("oos_sharpe") or -99), -(x.get("oos_terminal_x") or 0)))


def render_md(report: dict) -> str:
    lines = [
        "# IDX retail TA replication study",
        "",
        f"Generated: {report['generated_at_utc']}",
        f"OOS start: {report['oos_start']} | Cost: {COST_BPS}bps",
        "",
        "## Replication verdicts",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for k, v in report["verdict_counts"].items():
        lines.append(f"| {k} | {v} |")

    lines.extend(
        [
            "",
            "## Full playbook results (OOS portfolio)",
            "",
            "| Strategy | Jargon | Verdict | n signals | Terminal | Sharpe | Event 5d mean | Hit 5d |",
            "|----------|--------|---------|-----------|----------|--------|---------------|--------|",
        ]
    )
    for row in report["strategies"]:
        ev = row.get("event_study", {}).get("by_horizon", {}).get("oos_5d", {})
        lines.append(
            f"| {row['id']} | {row['retail_jargon'][:30]} | **{row['verdict']}** | "
            f"{row.get('n_signal_days', 0)} | {row.get('oos_portfolio', {}).get('terminal_x', '?'):.3f} | "
            f"{row.get('oos_portfolio', {}).get('sharpe', '?'):.3f} | "
            f"{ev.get('mean_pct', 'n/a')}% | {ev.get('hit_rate_pct', 'n/a')}% |"
        )

    lines.extend(["", "## Replicate — use these", ""])
    for row in report["strategies"]:
        if row["verdict"] == "replicate":
            lines.append(f"- **{row['id']}**: {row['description']}")

    lines.extend(["", "## Conditional — paper only / narrow scope", ""])
    for row in report["strategies"]:
        if row["verdict"] == "conditional":
            lines.append(f"- **{row['id']}**: {row['description']}")

    lines.extend(["", "## Reject — do not systematic trade", ""])
    for row in report["strategies"]:
        if row["verdict"] == "reject":
            lines.append(f"- {row['id']}: {row['retail_jargon']}")

    if report.get("sensitivity_bbca"):
        lines.extend(["", "## BBCA support parameter sensitivity (top 5 OOS Sharpe)", ""])
        for row in report["sensitivity_bbca"][:5]:
            lines.append(
                f"- lookback={row['lookback']}d RSI<{row['rsi_max']} prox={row['proximity_pct']}%: "
                f"Sharpe {row.get('oos_sharpe')}, terminal {row.get('oos_terminal_x')}x, n={row['n_signals']}"
            )

    lines.extend(
        [
            "",
            "## Replication checklist",
            "",
            "1. Run `python3 scripts/run_idn_retail_replication_study.py` weekly after panel refresh.",
            "2. Trade only **replicate** + **conditional** rules; ignore **reject**.",
            "3. Prefer single-name BBCA support+RSI over broad 50-name RSI scans.",
            "4. Event study n<25 → insufficient; do not promote.",
            "5. Wire top rules into `run_idn_weekly_position_sheet.py` (Lane: retail_ta).",
            "",
            "Evidence JSON: `backtests/outputs/idn_retail_replication/latest.json`",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    close, vol, universe = load_panel()
    close, vol = ensure_index(close, vol)
    all_signals = build_all_signals(close, vol, universe)

    bench_daily = simulate_equal_weight_monthly(close, universe)
    bench_oos = daily_metrics(bench_daily[bench_daily.index >= OOS_START])

    strategies_out = []
    for strat in PLAYBOOK:
        sigs = all_signals[strat.id]
        full_m, oos_m = portfolio_for_rule(strat.id, sigs, close, strat.hold_days, strat.max_slots)
        ev = event_study(sigs, close, hold_days_list=(5, 10, 20), oos_start=OOS_START)
        ev_is = event_study(
            {k: v for k, v in sigs.items() if k < OOS_START},
            close,
            hold_days_list=(5, 10, 20),
        )
        daily_oos = simulate_slot_portfolio(
            sigs, close, hold_days=strat.hold_days, max_slots=strat.max_slots, cost_bps=COST_BPS
        )
        boot = bootstrap_mean_return(daily_oos)
        verdict = replication_verdict(oos_m, ev)
        strategies_out.append(
            {
                "id": strat.id,
                "retail_jargon": strat.retail_jargon,
                "description": strat.description,
                "hold_days": strat.hold_days,
                "tags": strat.tags,
                "n_signal_days": len(sigs),
                "full_portfolio": full_m,
                "oos_portfolio": oos_m,
                "event_study": ev,
                "event_study_is": ev_is,
                "bootstrap_oos_daily": boot,
                "verdict": verdict,
            }
        )

    verdict_counts: dict[str, int] = {}
    for s in strategies_out:
        verdict_counts[s["verdict"]] = verdict_counts.get(s["verdict"], 0) + 1

    sensitivity = sensitivity_bbca_support(close, vol)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "oos_start": str(OOS_START.date()),
        "is_end": str(IS_END.date()),
        "universe_size": len(universe),
        "benchmark_oos": bench_oos,
        "verdict_counts": verdict_counts,
        "strategies": strategies_out,
        "sensitivity_bbca": sensitivity,
        "replicate_ids": [s["id"] for s in strategies_out if s["verdict"] == "replicate"],
        "conditional_ids": [s["id"] for s in strategies_out if s["verdict"] == "conditional"],
        "reject_ids": [s["id"] for s in strategies_out if s["verdict"] == "reject"],
        "proof_standard": {
            "min_event_n": 25,
            "replicate_requires": "OOS terminal>=1.05, Sharpe>=0.25, event 5d mean>0, hit>=52%",
            "data": "yfinance daily OHLCV, indonesia_liquid_core",
            "costs_bps": COST_BPS,
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    md = render_md(report)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(md, encoding="utf-8")
    DOCS.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {OUT / 'latest.json'} and {DOCS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
