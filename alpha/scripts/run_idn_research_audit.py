#!/usr/bin/env python3
"""Audit Indonesia research evidence chain — per-lane how/why/verdict.

Loads all IDN artifact JSONs, checks freshness, runs regime-sleeve OOS backtest,
writes backtests/outputs/idn_research_audit/latest.json + latest.md.

Example:
  python scripts/run_idn_research_audit.py
  python scripts/run_idn_research_audit.py --backtest-only
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

from idn_research_evidence import ARTIFACTS, LANES, gather_metrics, latest_winner_patterns_path  # noqa: E402
from run_idn_weekly_position_sheet import (  # noqa: E402
    CORE_BANKS,
    INDEX_PROXY,
    build_weights,
    load_panel,
    regime_state,
    tactical_group_sync,
)

from idn_eval_splits import OOS_FRAC_DEFAULT, time_cutoff  # noqa: E402

OUT = REPO / "backtests/outputs/idn_research_audit"


def _lane_verdicts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    horse = metrics.get("winner_horse_race_oos", {})
    inv = metrics.get("invest_trial_oos", {})
    alpha = metrics

    # Regime — pending backtest; heuristic
    rows.append(
        {
            "lane": "regime_ihsg",
            "status": "heuristic_unvalidated",
            "summary": "IHSG dd/bounce rules drive core sleeve sizing; see regime_backtest in audit output.",
            "evidence_for": ["Jun 2026 washout→recovery matched live IHSG +12.5% bounce off 20d low"],
            "evidence_against": ["EIDO regime model failed historically (markets/indonesia_run)"],
        }
    )

    bbca = inv.get("bbca_hold", {})
    banks = horse.get("banks_top3", {})
    rows.append(
        {
            "lane": "core_banks",
            "status": "weak_oos",
            "summary": (
                f"bbca_hold OOS Sharpe {bbca.get('sharpe', '?'):.2f}; "
                f"banks_top3 OOS terminal {banks.get('terminal_x', '?'):.2f}x"
                if isinstance(bbca.get("sharpe"), (int, float))
                else "bbca_hold OOS negative"
            ),
            "evidence_for": ["Jun 2026 BBCA +9.7% session during index bounce", "Low turnover, liquid names"],
            "evidence_against": [
                f"bbca_hold OOS mean weekly {bbca.get('mean_weekly_pct', 0):.2f}%"
                if bbca
                else "no invest trial data",
                "banks_top3 OOS Sharpe negative in horse race",
            ],
            "metrics": {"bbca_hold": bbca, "banks_top3": banks},
        }
    )

    comm = horse.get("commodity_proxy_top3", {})
    mom4b = horse.get("mom4_bottom5", {})
    rows.append(
        {
            "lane": "oos_winner_tilt",
            "status": "descriptive_only",
            "summary": (
                f"Top OOS names +{metrics.get('oos_top3_mean_weekly_pct', [])}%/wk descriptive; "
                f"commodity_proxy_top3 OOS terminal {comm.get('terminal_x', '?'):.2f}x"
            ),
            "evidence_for": [
                "JPFA/ANTM/ADRO top mean weekly 2024+",
                f"commodity_proxy_top3 OOS Sharpe {comm.get('sharpe', '?'):.2f}",
                f"mom4_bottom5 (contrarian) OOS terminal {mom4b.get('terminal_x', '?'):.2f}x — momentum inverted",
            ],
            "evidence_against": [
                "No DSR/PBO on tilt portfolio",
                "mom4_top5 OOS terminal 0.48x — chasing momentum fails",
                "news_risk in winner table is country broadcast (not ticker-specific)",
            ],
            "metrics": {"commodity_proxy_top3": comm, "mom4_bottom5": mom4b},
        }
    )

    gs = metrics.get("event_group_sync_2plus", {})
    ags = alpha.get("alpha_group_sync_2plus", {})
    rows.append(
        {
            "lane": "tactical_group_sync",
            "status": "event_study_only",
            "summary": (
                f"Event study +{gs.get('mean_fwd_5d_pct', '?')}% fwd-5d (n={gs.get('n', '?')}); "
                f"portfolio sim terminal {ags.get('terminal_x', '?'):.2f}x"
            ),
            "evidence_for": [
                f"group_sync_2plus hit rate {gs.get('hit_rate_pct', '?')}%",
                "Broker data does not weaken sync2 bucket",
            ],
            "evidence_against": [
                f"Portfolio Sharpe {ags.get('sharpe', '?')} — barely beats benchmark",
                "Tiny sample; Apr-2025 theme cluster",
                "2025-H2/2026 test window had zero sync2 sessions until Jun 2026",
            ],
            "metrics": {"event_study": gs, "portfolio": ags},
        }
    )

    ridge = horse.get("ridge_news_top5") or inv.get("top5", {})
    off_map = {
        "off_news_ridge_top5": ("ridge_news_top5", ridge),
        "off_spike_chase": ("alpha_spike_chase_10pct", alpha.get("alpha_spike_chase_10pct", {})),
        "off_mom20_breakout": ("alpha_mom20_breakout", alpha.get("alpha_mom20_breakout", {})),
        "off_broker_accdist": ("broker", metrics.get("broker_acc_alone", {})),
        "off_quiet_volume": ("alpha_quiet_volume_build", alpha.get("alpha_quiet_volume_build", {})),
    }
    for lane_id, (key, data) in off_map.items():
        if lane_id == "off_broker_accdist":
            status, summary = "killed", f"verdict={metrics.get('broker_pattern_verdict')}; Acc-alone fwd {data.get('mean_fwd_5d_pct')}% (n={data.get('n_with_fwd')})"
        elif isinstance(data, dict) and "sharpe" in data:
            status = "killed"
            summary = f"Sharpe {data.get('sharpe', 0):.2f}, terminal {data.get('terminal_x', 0):.2f}x"
        elif isinstance(data, dict) and "sharpe_weekly" in data:
            status = "killed"
            summary = f"OOS Sharpe {data.get('sharpe_weekly', 0):.2f}, mean weekly {data.get('mean_weekly_pct', 0):.2f}%"
        else:
            status = "killed"
            summary = LANES[lane_id].get("kill_if", "failed OOS")
        rows.append(
            {
                "lane": lane_id,
                "status": status,
                "summary": summary,
                "evidence_against": [LANES[lane_id].get("kill_if", "")],
                "metrics": data,
            }
        )

    return rows


def backtest_regime_sleeve(close: pd.DataFrame) -> dict[str, Any]:
    """Weekly rebalance using position-sheet rules; OOS from 2024."""
    wp_path = latest_winner_patterns_path()
    if not wp_path:
        return {"error": "no winner_patterns JSON"}
    wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wl = wp.get("winner_loser", wp)
    top6 = [x["yahoo_symbol"] for x in wl.get("top10_tickers", [])[:6]]
    avoid = {x["yahoo_symbol"] for x in wl.get("bottom10_tickers", [])}

    weekly_idx = close.resample("W-FRI").last().dropna(how="all")
    rets = close.pct_change()
    port_rets: list[float] = []
    eq_rets: list[float] = []
    dates: list[pd.Timestamp] = []
    prev_w: dict[str, float] = {}

    universe_cols = [c for c in close.columns if c.endswith(".JK")]

    for i, dt in enumerate(weekly_idx.index):
        if i == 0:
            continue
        hist = close.loc[:dt]
        if len(hist) < 22 or INDEX_PROXY not in hist.columns:
            continue
        regime = regime_state(hist)
        tactical = tactical_group_sync(hist, lookback_days=5)
        weights, _, _ = build_weights(regime, top6, avoid, tactical, {"primary_active": False})
        w = {k: v for k, v in weights.items() if k != "CASH"}

        week_start = weekly_idx.index[i - 1]
        week_end = dt
        daily = rets.loc[week_start:week_end]
        if daily.empty:
            continue
        # daily portfolio return
        dr = []
        for d, row in daily.iterrows():
            r = sum(w.get(s, 0) * row.get(s, 0) for s in w if s in row.index and np.isfinite(row.get(s, 0)))
            dr.append(r)
        if not dr:
            continue
        pr = float(np.prod([1 + x for x in dr]) - 1)
        er = float(np.nanmean([row[universe_cols].mean() for _, row in daily.iterrows() if universe_cols]))
        port_rets.append(pr)
        eq_rets.append(er)
        dates.append(week_end)

    s = pd.Series(port_rets, index=pd.DatetimeIndex(dates))
    e = pd.Series(eq_rets, index=pd.DatetimeIndex(dates))
    oos_start = time_cutoff(s.index, oos_frac=OOS_FRAC_DEFAULT)
    oos = s.index >= oos_start
    so = s[oos]
    eo = e[oos]

    def stats(r: pd.Series) -> dict:
        if r.empty:
            return {}
        vol = float(r.std(ddof=1))
        return {
            "n_weeks": len(r),
            "mean_weekly_pct": round(float(r.mean() * 100), 3),
            "sharpe": round(float(r.mean() / vol * math.sqrt(52)), 3) if vol > 0 else None,
            "terminal_x": round(float((1 + r).prod()), 3),
            "hit_pct": round(float((r > 0).mean() * 100), 1),
        }

    return {
        "full_sample": stats(s),
        "oos_from_2024": stats(so),
        "benchmark_liquid_eq_weekly": stats(eo),
        "note": "Uses current winner list for all history (lookahead bias on tilt names). Regime rules are point-in-time.",
    }


def check_artifacts() -> list[dict]:
    rows = []
    for name, path in ARTIFACTS.items():
        rows.append(
            {
                "name": name,
                "path": str(path),
                "exists": path.exists(),
                "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
                if path.exists()
                else None,
            }
        )
    return rows


def render_md(report: dict) -> str:
    lines = [
        "# Indonesia research audit",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "## Lane verdicts",
        "",
        "| Lane | Status | Summary |",
        "|------|--------|---------|",
    ]
    for row in report["lane_verdicts"]:
        lines.append(f"| {row['lane']} | {row['status']} | {row['summary']} |")

    lines.extend(["", "## Regime sleeve backtest", ""])
    rb = report.get("regime_backtest", {})
    for k, v in rb.items():
        if isinstance(v, dict):
            lines.append(f"**{k}:** n={v.get('n_weeks')} weeks, mean={v.get('mean_weekly_pct')}%, Sharpe={v.get('sharpe')}, terminal={v.get('terminal_x')}x")

    lines.extend(["", "## Artifact freshness", ""])
    for a in report["artifacts"]:
        flag = "OK" if a["exists"] else "MISSING"
        lines.append(f"- [{flag}] `{a['name']}` — {a['path']}")

    lines.extend(
        [
            "",
            "## How to refresh",
            "",
            "```bash",
            "python scripts/run_idn_alpha_proof.py",
            "python scripts/run_idn_winner_patterns.py",
            "python scripts/run_idn_spike_pattern_mining.py",
            "python scripts/run_idn_research_audit.py",
            "python scripts/run_idn_weekly_position_sheet.py",
            "```",
            "",
            "Full how/why: `docs/IDN_RESEARCH.md`",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest-only", action="store_true")
    args = ap.parse_args()

    metrics = gather_metrics()
    artifacts = check_artifacts()
    lane_verdicts = _lane_verdicts(metrics)

    regime_backtest: dict[str, Any] = {}
    if not args.backtest_only:
        close, _ = load_panel()
        regime_backtest = backtest_regime_sleeve(close)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "lane_verdicts": lane_verdicts,
        "regime_backtest": regime_backtest,
        "artifacts": artifacts,
        "lanes_doc": LANES,
        "gaps": [
            "Winner tilt uses fixed top-6 list in regime backtest (mild lookahead on tilt sleeve)",
            "Regime rules not optimized — thresholds are hand-set",
            "No transaction cost in regime backtest",
            "news_risk in winner_patterns is country-level broadcast, not per-ticker",
            "Weekly position sheet has <2 weeks paper ledger",
            "Promotion gates: indonesia_lab 0/5 strategies pass DSR",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(render_md(report))
    print(f"\nWrote {OUT / 'latest.md'}")

    missing = [a for a in artifacts if not a["exists"] and a["name"] not in ("position_sheet",)]
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
