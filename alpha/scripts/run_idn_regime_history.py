#!/usr/bin/env python3
"""Build long IHSG regime tape (1990+) and bank-sleeve episode stats.

Caches:
  data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet
  data_lake/markets/yfinance_asia/idn_core_banks_daily.parquet

Outputs:
  backtests/outputs/idn_regime_history/latest.json
  backtests/outputs/idn_regime_history/latest.md

Example:
  python scripts/run_idn_regime_history.py
  python scripts/run_idn_regime_history.py --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_regime_lib import (  # noqa: E402
    BANKS_CACHE,
    BANKS_START,
    FORWARD_HORIZONS_DAYS,
    IHSG_CACHE,
    IHSG_START,
    bank_equal_weight_series,
    current_episode_live,
    current_regime,
    deepest_washout_entries,
    episode_entry_forward_stats,
    episode_runs,
    fetch_and_cache,
    label_distribution,
    lane_playbook_summary,
    random_entry_baseline,
    transition_events,
    washout_to_recovery_holds,
)

OUT = REPO / "backtests/outputs/idn_regime_history"


def _era_slices(tape) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for y in range(1990, datetime.now(UTC).year + 1):
        sub = tape[tape.index.year == y]
        if len(sub) < 20:
            continue
        counts = label_distribution(sub)
        washout_days = counts.get("washout", 0)
        out[str(y)] = {
            "trading_days": len(sub),
            "labels": counts,
            "washout_share_pct": round(washout_days / len(sub) * 100, 1),
        }
    return out


def _recent_episodes(tape, label: str, n: int = 8) -> list[dict[str, Any]]:
    eps = [e for e in episode_runs(tape["label"]) if e["label"] == label]
    eps = sorted(eps, key=lambda x: x["start"], reverse=True)[:n]
    return [
        {"start": str(e["start"].date()), "end": str(e["end"].date()), "n_days": e["n_days"]}
        for e in eps
    ]


def _fmt_lane_row(lane: str, stats: dict[str, Any], h: int) -> str:
    s = stats.get(f"fwd_{h}d", {})
    if not s.get("n"):
        return ""
    return (
        f"| {lane} | {h}d | {s['n']} | {s['mean_pct']:+.1f}% | {s['median_pct']:+.1f}% | "
        f"{s['p90_pct']:+.1f}% | {s['max_pct']:+.1f}% | "
        f"{s.get('hit_gt_10pct', 0):.0f}% | {s.get('hit_gt_25pct', 0):.0f}% |"
    )


def render_md(report: dict[str, Any]) -> str:
    cur = report["current"]
    pb = report.get("playbook", {})
    live = report.get("current_episode", {})
    lines = [
        "# Indonesia IHSG regime history",
        "",
        f"**Generated:** {report['generated_utc']}",
        f"**Tape:** {report['tape']['start']} → {report['tape']['end']} ({report['tape']['trading_days']} days)",
        "",
        "## How to read this",
        "",
        "- **Regime lane** = 4w beta filter (washout/recovery/neutral). Not year-hold.",
        "- **Monthly winners:** run `run_idn_monthly_horse_race.py` — ranked by OOS 4w return.",
        "- **Retail TA** fires on events (5–20d holds), flat otherwise.",
        "",
        "## Playbook (auto)",
        "",
    ]
    for _, text in pb.items():
        lines.append(f"- {text}")
    lines.extend(
        [
            "",
            "## Current",
            "",
            f"- **As of:** {cur['as_of']}",
            f"- **Label:** `{cur['label']}` (core sleeve {cur['core_sleeve_pct'] * 100:.0f}%)",
            f"- **DD from 63d high:** {cur['dd_from_63d_high_pct']:.1f}%",
            f"- **Bounce from 20d low:** {cur['bounce_from_20d_low_pct']:.1f}%",
            f"- **5d / 20d:** {cur['ret_5d_pct']:+.1f}% / {cur['ret_20d_pct']:+.1f}%",
        ]
    )
    if live:
        lines.extend(
            [
                "",
                "## Live episode",
                "",
                f"- **Phase:** `{live.get('label')}` since {live.get('start')} ({live.get('n_days')}d)",
            ]
        )
        for k in ("ihsg", "banks_ew", "bbca"):
            v = live.get(f"{k}_since_start_pct")
            if v is not None:
                lines.append(f"- **{k}** since episode start: {v:+.1f}%")

    lines.extend(
        [
            "",
            "## Washout entry — forward returns by lane",
            "",
            "Entry = first day of washout episode. Banks/BBCA stats from 2003+.",
            "",
            "| Lane | Horizon | n | mean | median | p90 | max | hit>10% | hit>25% |",
            "|------|---------|---|------|--------|-----|-----|---------|---------|",
        ]
    )
    wlanes = report["washout_forward"]["lanes"]
    for lane in ("ihsg", "banks_ew", "bbca", "sleeve"):
        for h in FORWARD_HORIZONS_DAYS:
            row = _fmt_lane_row(lane, wlanes.get(lane, {}), h)
            if row:
                lines.append(row)

    lines.extend(
        [
            "",
            "## Washout trough entry (deepest day in episode)",
            "",
            "Often better timing than first washout tick.",
            "",
            "| Lane | Horizon | n | mean | median | p90 | max | hit>10% | hit>25% |",
            "|------|---------|---|------|--------|-----|-----|---------|---------|",
        ]
    )
    trough = report["washout_trough"]
    for lane, key in (("ihsg", "ihsg"), ("banks_ew", "banks_ew"), ("bbca", "bbca")):
        for h in FORWARD_HORIZONS_DAYS:
            stats = trough.get(f"{key}_fwd_{h}d", {})
            if stats.get("n"):
                lines.append(
                    f"| {lane} | {h}d | {stats['n']} | {stats['mean_pct']:+.1f}% | "
                    f"{stats['median_pct']:+.1f}% | {stats['p90_pct']:+.1f}% | {stats['max_pct']:+.1f}% | "
                    f"{stats.get('hit_gt_10pct', 0):.0f}% | {stats.get('hit_gt_25pct', 0):.0f}% |"
                )

    hold = report["washout_to_recovery"]
    lines.extend(
        [
            "",
            "## Washout start → recovery flip (hold through cycle)",
            "",
            f"Cycles: **{hold.get('cycles', 0)}** (bank prices from 2003+)",
            "",
            "| Lane | n | mean | median | p90 | max | hit>25% |",
            "|------|---|------|--------|-----|-----|---------|",
        ]
    )
    for lane in ("ihsg", "banks_ew", "bbca", "sleeve"):
        s = hold.get(lane, {})
        if s.get("n"):
            lines.append(
                f"| {lane} | {s['n']} | {s['mean_pct']:+.1f}% | {s['median_pct']:+.1f}% | "
                f"{s['p90_pct']:+.1f}% | {s['max_pct']:+.1f}% | {s.get('hit_gt_25pct', 0):.0f}% |"
            )

    rnd = report["random_baseline"]["banks_ew"]
    lines.extend(["", "## Random baseline (any-day bank EW)", ""])
    for h in FORWARD_HORIZONS_DAYS:
        s = rnd.get(f"fwd_{h}d", {})
        if s.get("n"):
            lines.append(
                f"- **{h}d:** mean {s['mean_pct']:+.1f}% | median {s['median_pct']:+.1f}% | "
                f"p90 {s['p90_pct']:+.1f}% | max {s['max_pct']:+.1f}%"
            )

    lines.extend(["", "## Recent washout episodes", ""])
    for e in report["recent_washout_episodes"]:
        lines.append(f"- {e['start']} → {e['end']} ({e['n_days']}d)")
    lines.extend(
        [
            "",
            "## Caches",
            "",
            f"- `{IHSG_CACHE.relative_to(REPO)}`",
            f"- `{BANKS_CACHE.relative_to(REPO)}`",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build IHSG regime history tape and episode stats")
    ap.add_argument("--refresh", action="store_true", help="Re-download full history from yfinance")
    args = ap.parse_args()

    tape, banks = fetch_and_cache(refresh=args.refresh)
    washout = episode_entry_forward_stats(tape, banks, "washout")
    recovery = episode_entry_forward_stats(tape, banks, "recovery")
    transitions = transition_events(tape["label"])
    washout_hold = washout_to_recovery_holds(tape, banks)
    washout_trough = deepest_washout_entries(tape, banks)
    random_banks = random_entry_baseline(bank_equal_weight_series(banks))
    live_ep = current_episode_live(tape, banks)

    report: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "tape": {
            "start": str(tape.index.min().date()),
            "end": str(tape.index.max().date()),
            "trading_days": len(tape),
            "ihsg_cache": str(IHSG_CACHE),
            "banks_cache": str(BANKS_CACHE),
            "ihsg_fetch_start": IHSG_START,
            "banks_fetch_start": BANKS_START,
        },
        "current": current_regime(tape),
        "current_episode": live_ep,
        "playbook": lane_playbook_summary(washout, washout_trough, washout_hold, random_banks),
        "label_distribution": label_distribution(tape),
        "transition_count": len(transitions),
        "washout_to_recovery_count": sum(
            1 for t in transitions if t["from"] == "washout" and t["to"] == "recovery"
        ),
        "by_year": _era_slices(tape),
        "washout_forward": washout,
        "recovery_forward": recovery,
        "washout_to_recovery": washout_hold,
        "washout_trough": washout_trough,
        "random_baseline": {"banks_ew": random_banks},
        "recent_washout_episodes": _recent_episodes(tape, "washout"),
        "recent_recovery_episodes": _recent_episodes(tape, "recovery"),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(json.dumps({"ok": True, "current": report["current"], "out": str(OUT / "latest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
