#!/usr/bin/env python3
"""Backtest the usual IDX influencer / retail TA playbook vs our quant lanes.

Rules codify what retail actually says:
  - buy blue chips at support (near N-day low)
  - RSI oversold bounce
  - MA20 pullback / golden cross
  - index washed out → buy banks
  - breakout chase (usually fails — included to show why)

Compares OOS 2024+ to idn_alpha_proof strategies and invest-trial killers.

Output: backtests/outputs/idn_retail_playbook/latest.json + latest.md
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
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

from api.intelligence.technical_indicators import TechnicalIndicators  # noqa: E402
from run_idn_alpha_proof import (  # noqa: E402
    OOS_START,
    COST_BPS,
    HOLD_DAYS,
    MAX_SLOTS,
    daily_metrics,
    load_panel,
    simulate_equal_weight_monthly,
    simulate_slot_portfolio,
)

OUT = REPO / "backtests/outputs/idn_retail_playbook"
BANKS = ["BBCA.JK", "BBRI.JK", "BMRI.JK"]
INDEX = "^JKSE"
BLUE_CHIPS = BANKS + ["TLKM.JK", "ASII.JK"]


@dataclass
class PlaybookRule:
    name: str
    retail_label: str
    description: str


RULES = [
    PlaybookRule(
        "bbca_support_rsi",
        "Buy BBCA at support + RSI oversold",
        "BBCA within 2% of 60d low AND RSI(14)<35 → buy BBCA, hold 20d",
    ),
    PlaybookRule(
        "banks_index_support",
        "Index support → buy banks",
        "IHSG within 3% of 60d low → equal-weight BBCA/BBRI/BMRI, hold 20d",
    ),
    PlaybookRule(
        "bluechip_support_bounce",
        "Blue chip support bounce",
        "Any of BBCA/BBRI/BMRI/TLKM/ASII within 2% of 40d low → buy that name, hold 10d",
    ),
    PlaybookRule(
        "ma20_golden_cross",
        "MA20 golden cross",
        "Price crosses above SMA20 after 5d below → buy, hold 10d",
    ),
    PlaybookRule(
        "rsi30_bounce_liquid",
        "RSI oversold bounce (liquid 50)",
        "RSI(14)<30 on any liquid name → buy, hold 5d (max 5 slots)",
    ),
    PlaybookRule(
        "breakout_20d_high",
        "Breakout resistance (20d high)",
        "Close > 20d high AND vol > 1.5x avg → buy (retail breakout), hold 5d",
    ),
]


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    return TechnicalIndicators.calculate_rsi(close, period)


def build_retail_signals(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    universe: list[str],
) -> dict[str, dict[pd.Timestamp, list[str]]]:
    out: dict[str, dict[pd.Timestamp, list[str]]] = {r.name: {} for r in RULES}
    idx = close[INDEX] if INDEX in close.columns else None

    for dt in close.index[60:]:
        day: dict[str, list[str]] = {r.name: [] for r in RULES}

        if idx is not None and dt in idx.index:
            i_loc = idx.index.get_loc(dt)
            if i_loc >= 60:
                low60 = float(idx.iloc[i_loc - 60 : i_loc + 1].min())
                last_i = float(idx.loc[dt])
                if low60 > 0 and last_i <= low60 * 1.03:
                    day["banks_index_support"].extend(BANKS)

        for sym in universe:
            if sym not in close.columns or dt not in close.index:
                continue
            loc = close.index.get_loc(dt)
            if loc < 60:
                continue
            px = close[sym]
            r = _rsi(px)
            if dt not in r.index or not np.isfinite(r.loc[dt]):
                continue
            rsi_v = float(r.loc[dt])
            last = float(px.loc[dt])
            low40 = float(px.iloc[loc - 40 : loc + 1].min())
            low60 = float(px.iloc[loc - 60 : loc + 1].min())
            high20 = float(px.iloc[loc - 20 : loc].max()) if loc >= 20 else np.nan
            sma20 = float(px.iloc[loc - 19 : loc + 1].mean())
            prev_below = all(float(px.loc[close.index[loc - k]]) < float(px.iloc[loc - 19 - k : loc - k + 1].mean())
                             for k in range(1, 6) if loc - k >= 20)

            if sym == "BBCA.JK" and low60 > 0 and last <= low60 * 1.02 and rsi_v < 35:
                day["bbca_support_rsi"].append(sym)

            if sym in BLUE_CHIPS and low40 > 0 and last <= low40 * 1.02:
                day["bluechip_support_bounce"].append(sym)

            if prev_below and last > sma20:
                day["ma20_golden_cross"].append(sym)

            if rsi_v < 30:
                day["rsi30_bounce_liquid"].append(sym)

            if np.isfinite(high20) and last > high20:
                vt = float(vol.loc[dt, sym]) if sym in vol.columns else np.nan
                vavg = float(vol[sym].iloc[loc - 20 : loc].mean()) if sym in vol.columns else np.nan
                if np.isfinite(vt) and np.isfinite(vavg) and vavg > 0 and vt >= 1.5 * vavg:
                    day["breakout_20d_high"].append(sym)

        for k, v in day.items():
            if v:
                out[k][dt] = sorted(set(v))

    return out


def hold_days_for(name: str) -> int:
    return {"bbca_support_rsi": 20, "banks_index_support": 20, "bluechip_support_bounce": 10}.get(name, HOLD_DAYS)


def jun2026_bbca_postmortem(close: pd.DataFrame) -> dict[str, Any]:
    """Did retail rules fire around the Jun 2026 BBCA bounce?"""
    if "BBCA.JK" not in close.columns or INDEX not in close.columns:
        return {}
    bbca = close["BBCA.JK"].dropna()
    idx = close[INDEX].dropna()
    # scan May-Jun 2026
    window = bbca.loc["2026-05-01":"2026-06-12"]
    signals = []
    for dt in window.index:
        loc = bbca.index.get_loc(dt)
        if loc < 60:
            continue
        last = float(bbca.loc[dt])
        low60 = float(bbca.iloc[loc - 60 : loc + 1].min())
        rsi_v = float(_rsi(bbca).loc[dt])
        near_support = last <= low60 * 1.05
        if near_support or rsi_v < 40:
            signals.append(
                {
                    "date": str(dt.date()),
                    "bbca_close": round(last, 0),
                    "pct_from_60d_low": round((last / low60 - 1) * 100, 1),
                    "rsi14": round(rsi_v, 1),
                    "ret_5d_fwd_pct": round(
                        float(bbca.iloc[min(loc + 5, len(bbca) - 1)] / last - 1) * 100, 1
                    )
                    if loc + 5 < len(bbca)
                    else None,
                }
            )
    ihsg_low = float(idx.loc["2026-05-01":"2026-06-12"].min())
    ihsg_last = float(idx.iloc[-1])
    return {
        "bbca_support_signals_may_jun_2026": signals[:8],
        "ihsg_bounce_off_low_pct": round((ihsg_last / ihsg_low - 1) * 100, 1),
        "note": "Retail 'buy BBCA at support' fires on proximity to 60d low / RSI<35 — not on news or broker data.",
    }


def render_md(report: dict) -> str:
    lines = [
        "# IDX retail / influencer playbook backtest",
        "",
        f"OOS from {OOS_START.date()} | cost {COST_BPS}bps",
        "",
        "## What retail says vs what we tested",
        "",
        "| Rule | Retail jargon | OOS terminal | OOS Sharpe |",
        "|------|---------------|-------------|------------|",
    ]
    for row in report["playbook_results"]:
        lines.append(
            f"| {row['name']} | {row['retail_label']} | {row.get('terminal_x', '?'):.3f}x | {row.get('sharpe', '?'):.3f} |"
        )
    lines.extend(["", "## vs our quant lanes (same OOS window)", ""])
    for row in report.get("quant_comparison", []):
        lines.append(f"- **{row['name']}**: terminal {row.get('terminal_x', '?'):.3f}x, Sharpe {row.get('sharpe', '?')}")

    lines.extend(["", "## Jun 2026 BBCA post-mortem", ""])
    pm = report.get("jun2026_postmortem", {})
    for s in pm.get("bbca_support_signals_may_jun_2026", []):
        lines.append(
            f"- {s['date']}: BBCA {s['bbca_close']}, {s['pct_from_60d_low']:+.1f}% from 60d low, RSI {s['rsi14']}, fwd5d {s.get('ret_5d_fwd_pct')}%"
        )

    lines.extend(
        [
            "",
            "## Why influencers look smarter than our research",
            "",
            "1. **They time one obvious trade** (BBCA at support) — we systematic'd across 50 names.",
            "2. **Survivorship** — nobody posts the support levels that broke.",
            "3. **Our heavy lanes were mostly news/broker/spike** — not classic TA. Those lanes died OOS.",
            "4. **The closest quant rule we had** — `drawdown_squeeze` — IS retail 'buy the dip + volume'. It won alpha_proof.",
            "5. **Regime washout** in the weekly sheet IS index-support → banks. Same playbook, codified late.",
            "",
            "See also: `docs/IDN_RESEARCH.md`",
        ]
    )
    return "\n".join(lines)


def ensure_index(close: pd.DataFrame, vol: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if INDEX in close.columns:
        return close, vol
    from idn_spike_explainer import fetch_history  # noqa: WPS433

    c2, v2 = fetch_history([INDEX], str(close.index.min().date()), str(close.index.max().date()))
    return close.join(c2, how="outer").sort_index(), vol.join(v2, how="outer").sort_index()


def main() -> int:
    close, vol, universe = load_panel()
    close, vol = ensure_index(close, vol)
    signals = build_retail_signals(close, vol, universe)

    results = []
    for rule in RULES:
        sigs = signals[rule.name]
        hd = hold_days_for(rule.name)
        daily = simulate_slot_portfolio(
            sigs, close, hold_days=hd, max_slots=MAX_SLOTS if rule.name != "bbca_support_rsi" else 1, cost_bps=COST_BPS
        )
        m = daily_metrics(daily)
        m["name"] = rule.name
        m["retail_label"] = rule.retail_label
        m["description"] = rule.description
        m["n_signal_days"] = len(sigs)
        results.append(m)

    bench = simulate_equal_weight_monthly(close, universe)
    bench_m = daily_metrics(bench)
    bench_m["name"] = "liquid_eq_monthly"

    # load quant comparison from alpha_proof if present
    quant_cmp = []
    ap_path = REPO / "backtests/outputs/idn_alpha_proof/latest.json"
    if ap_path.exists():
        ap = json.loads(ap_path.read_text())
        for row in ap.get("portfolio_results", []):
            if row["name"] in (
                "drawdown_squeeze",
                "group_sync_2plus",
                "spike_chase_10pct",
                "liquid_eq_monthly",
            ):
                quant_cmp.append(row)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "oos_start": str(OOS_START.date()),
        "playbook_results": results,
        "benchmark": bench_m,
        "quant_comparison": quant_cmp,
        "jun2026_postmortem": jun2026_bbca_postmortem(close),
        "rules": [asdict(r) for r in RULES],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(render_md(report))
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
