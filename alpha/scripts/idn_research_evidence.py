"""Shared evidence definitions for Indonesia research lanes.

Used by run_idn_research_audit.py and run_idn_weekly_position_sheet.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

ARTIFACTS = {
    "alpha_proof": REPO / "backtests/outputs/idn_alpha_proof/latest.json",
    "spike_patterns": REPO / "backtests/outputs/idn_spike_explainer/pattern_mining_latest.json",
    "broker_validation": REPO / "backtests/outputs/idn_broker_spike_validation/latest.json",
    "broker_pattern_alpha": REPO / "backtests/outputs/idn_broker_pattern_alpha/latest.json",
    "invest_trial": REPO / "backtests/outputs/idn_invest/20260612T035255Z/strategy_summary.json",
    "winner_patterns": REPO
    / "backtests/outputs/idn_invest/patterns/winner_patterns_20260612T080407Z.json",
    "position_sheet": REPO / "backtests/outputs/idn_weekly_position_sheet/latest.json",
    "panel_cache": REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet",
}

LANES: dict[str, dict[str, Any]] = {
    "regime_ihsg": {
        "title": "Regime (IHSG drawdown / bounce)",
        "hypothesis": (
            "After deep index drawdown (>10% from 63d high), large-cap banks re-rate with beta; "
            "after extended bounce, reduce risk."
        ),
        "how": (
            "Daily ^JKSE: dd_63 = last/63d_high-1; bounce_20 = last/20d_low-1. "
            "washout: dd<=-10% & bounce<8% → 55% core banks; "
            "recovery: dd<=-10% & bounce>=8% → 45%; "
            "extended: bounce>=12% & 5d ret>=5% → 25% core + more cash."
        ),
        "scripts": ["scripts/run_idn_weekly_position_sheet.py"],
        "confidence_note": "Rules are heuristic; backtest in research audit.",
    },
    "core_banks": {
        "title": "Core banks (BBCA / BBRI / BMRI)",
        "hypothesis": "Liquid large banks capture IDX beta on washout/recovery; MSCI/index weight concentration.",
        "how": "Equal-weight among BBCA, BBRI, BMRI as core sleeve; weight scales with regime.",
        "scripts": ["scripts/run_idn_invest_trial.py", "scripts/run_idn_winner_patterns.py"],
        "kill_if": "OOS banks_top3 or bbca_hold Sharpe persistently negative vs liquid_eq.",
    },
    "oos_winner_tilt": {
        "title": "OOS winner tilt",
        "hypothesis": "Names with highest mean weekly return 2024+ (descriptive) may persist short-term.",
        "how": "Top 6 from winner_patterns JSON, equal split of tilt sleeve; zero weight on bottom-10 avoid list.",
        "scripts": ["scripts/run_idn_winner_patterns.py"],
        "kill_if": "Tilt portfolio not validated; momentum rules (mom4_top5) failed OOS.",
    },
    "tactical_group_sync": {
        "title": "Tactical group_sync (theme names)",
        "hypothesis": "Spike day +2 peers up >=8% in same theme → continuation over 5d.",
        "how": (
            ">=10% single-day move AND >=2 peers from indonesia_stock_groups themes "
            "(barito/coal/nickel) up >=8%; max 3 names, ~8% total sleeve."
        ),
        "scripts": [
            "scripts/run_idn_alpha_proof.py",
            "scripts/idn_spike_explainer.py",
            "scripts/run_idn_spike_pattern_mining.py",
        ],
        "kill_if": "Portfolio simulation group_sync_2plus terminal ~1.0x OOS despite strong event study.",
    },
    "off_news_ridge_top5": {
        "title": "OFF: news ridge top-5 weekly",
        "hypothesis": "News shock ridge ranks weekly picks.",
        "kill_if": "OOS Sharpe -0.93; terminal 0.53x in winner_patterns horse race.",
    },
    "off_spike_chase": {
        "title": "OFF: spike chase 10%",
        "hypothesis": "Buy ARA limit-up days for continuation.",
        "kill_if": "Alpha proof Sharpe -0.30, terminal 0.85x; mean fwd-5d only +0.81% (all spikes).",
    },
    "off_mom20_breakout": {
        "title": "OFF: mom20 breakout",
        "hypothesis": "20d momentum breakout predicts 5d swing returns.",
        "kill_if": "Alpha proof Sharpe -1.34, terminal 0.45x.",
    },
    "off_broker_accdist": {
        "title": "OFF: broker Acc-only",
        "hypothesis": "RapidAPI broker accumulation tag predicts fwd returns.",
        "kill_if": "Broker validation: Acc-without-sync -9.83% fwd (n=3); pattern_alpha verdict no_broker_alpha.",
    },
    "retail_bbca_support_rsi": {
        "title": "Retail: BBCA support + RSI oversold",
        "hypothesis": "Buy BBCA within 2% of 60d low when RSI(14)<35; hold 20d.",
        "how": "Classic influencer support/resistance + RSI — codified in run_idn_retail_playbook.py",
        "scripts": ["scripts/run_idn_retail_playbook.py"],
        "kill_if": "OOS terminal below liquid_eq or Sharpe < 0",
    },
    "off_quiet_volume": {
        "title": "OFF: quiet volume build",
        "hypothesis": "Low vol + rising volume precedes squeeze.",
        "kill_if": "Alpha proof Sharpe -0.59, terminal 0.71x.",
    },
}


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def latest_winner_patterns_path() -> Path | None:
    pat = REPO / "backtests/outputs/idn_invest/patterns/winner_patterns_*.json"
    paths = sorted(pat.parent.glob(pat.name), reverse=True)
    return paths[0] if paths else None


def gather_metrics() -> dict[str, Any]:
    """Pull headline numbers from artifact JSONs."""
    m: dict[str, Any] = {}

    ap = load_json(ARTIFACTS["alpha_proof"])
    if isinstance(ap, dict):
        for row in ap.get("portfolio_results", []):
            name = row.get("name")
            if name:
                m[f"alpha_{name}"] = {
                    "sharpe": row.get("sharpe"),
                    "terminal_x": row.get("terminal_x"),
                    "n_trades": row.get("n_trades"),
                }

    sp = load_json(ARTIFACTS["spike_patterns"])
    if isinstance(sp, dict):
        for tag in sp.get("tag_stats", []):
            if tag.get("tag") == "group_sync_2plus":
                m["event_group_sync_2plus"] = {
                    "n": tag.get("count"),
                    "mean_fwd_5d_pct": tag.get("mean_fwd_5d_pct"),
                    "hit_rate_pct": tag.get("fwd_5d_hit_rate_pct"),
                }

    bv = load_json(ARTIFACTS["broker_validation"])
    if isinstance(bv, dict):
        m["broker_validation_verdict"] = bv.get("verdict")
        for b in bv.get("event_study_fwd5d", []):
            if b.get("bucket") == "broker_Acc_not_sync2":
                m["broker_acc_alone"] = b

    bpa = load_json(ARTIFACTS["broker_pattern_alpha"])
    if isinstance(bpa, dict):
        m["broker_pattern_verdict"] = bpa.get("verdict")
        m["broker_incremental_r2"] = bpa.get("incremental_r2")

    wp_path = latest_winner_patterns_path()
    if wp_path:
        wp = load_json(wp_path)
        if isinstance(wp, dict):
            horse = {r["name"]: r for r in wp.get("strategy_horse_race_oos", [])}
            m["winner_horse_race_oos"] = horse
            top = wp.get("winner_loser", {}).get("top10_tickers", [])
            m["oos_top3_mean_weekly_pct"] = [round(t["mean_1w"] * 100, 2) for t in top[:3]]

    inv = load_json(ARTIFACTS["invest_trial"])
    if isinstance(inv, list):
        oos = {r["strategy"]: r["net"] for r in inv if r.get("sample") == "oos_from2024"}
        m["invest_trial_oos"] = {
            k: {"sharpe": v.get("sharpe_weekly"), "mean_weekly_pct": v.get("mean_weekly_pct")}
            for k, v in oos.items()
        }

    return m
