#!/usr/bin/env python3
"""Winner-first IDX research — identify big 20d gains, reverse-engineer pre-entry patterns.

Starts from outcomes (reward_20d >= 20%), not from pre-built rules. Uses:
  - turnaround daily_features (2022–2026, full feature stack)
  - optional extended price panel back to 2019 via idx_all merge

Outputs:
  backtests/outputs/idn_big_winner_reverse/latest.json
  backtests/outputs/idn_big_winner_reverse/latest.md

Example:
  python alpha/scripts/run_idn_big_winner_reverse_engineer.py
  python alpha/scripts/run_idn_big_winner_reverse_engineer.py --extend-from 2019-07-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_big_winner_reverse_lib import (  # noqa: E402
    BIG_WIN_PCT,
    build_extended_panel,
    run_reverse_engineer,
)

OUT = REPO / "backtests/outputs/idn_big_winner_reverse"


def render_md(report: dict) -> str:
    lines = [
        "# IDX big-winner reverse engineering",
        "",
        f"**Generated:** {report['generated_at_utc']}",
        f"**Timeline:** {report['date_min']} → {report['date_max']} | "
        f"**Rows:** {report['panel_rows']:,} | **Symbols:** {report['symbols']}",
        "",
        "## Method (winner-first)",
        "",
        f"1. Label **big win** = forward 20d return ≥ **{BIG_WIN_PCT}%**",
        "2. De-duplicate to non-overlapping episode entries (20d gap per symbol)",
        "3. Mine pre-entry features vs baseline; rank by **lift** (conditional rate / base rate)",
        "4. Validate patterns on last 25% of timeline (OOS holdout)",
        "",
        f"- Baseline big-win rate: **{report['baseline_big_win_rate_pct']}%**",
        f"- Deduped winner episodes: **{report['n_deduped_episodes']:,}**",
        "",
        "## Panel coverage",
        "",
    ]
    for tier, n in (report.get("panel_tiers") or {}).items():
        lines.append(f"- `{tier}`: {n:,} rows")
    lines.extend(["", "## Stable mechanisms (train + OOS lift ≥ 1.1×)", ""])
    if not report.get("mechanisms"):
        lines.append("_No patterns passed stability filter — see ranked patterns in JSON._")
    for m in report.get("mechanisms", [])[:12]:
        lines.append(
            f"- **{m['pattern']}** — {m['mechanism']} "
            f"(OOS lift {m.get('oos_lift')}×, OOS mean 20d {m.get('oos_mean_reward_20d_pct')}%, n_oos={m.get('n_oos')})"
        )

    lines.extend(["", "## Winner vs same-day control (mean delta)", ""])
    lines.append("| Feature | Δ winner−control | Days |")
    lines.append("|---------|------------------|------|")
    for row in (report.get("winner_vs_control") or [])[:10]:
        lines.append(f"| {row['feature']} | {row['mean_delta']:+.4f} | {row['n_days']} |")

    lines.extend(["", "## Top 20d winner episodes (deduped)", ""])
    lines.append("| Date | Symbol | Type | 20d % | RSI | DD60 | Bandar | Regime |")
    lines.append("|------|--------|------|-------|-----|------|--------|--------|")
    for e in (report.get("top_episodes") or [])[:15]:
        lines.append(
            f"| {e.get('date','')} | {e.get('yahoo_symbol','')} | {e.get('name_type','')} | "
            f"{e.get('reward_20d_pct',0):.1f}% | {e.get('rsi14','—')} | "
            f"{(e.get('dd_60d') or 0)*100:.1f}% | {e.get('bandar_lite_label','')} | {e.get('ihsg_regime','')} |"
        )

    lines.extend(
        [
            "",
            "## How to use",
            "",
            "- Patterns here are **hypothesis generators** — wire only after OOS lift holds on your hold horizon.",
            "- Compare with `backtests/outputs/idn_turnaround/signal_eval.json` (rule-forward eval).",
            "- Retail sheet should prefer **narrow** compounder/support rules over broad RSI scans.",
            "",
            f"OOS cutoff: {report.get('split_meta', {}).get('cutoff', '—')}",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--extend-from",
        default="2019-07-01",
        help="Backfill price-derived features before 2022 turnaround panel (default: 2019-07-01)",
    )
    ap.add_argument("--no-extend", action="store_true", help="Use turnaround panel only (2022+)")
    args = ap.parse_args(argv)

    if args.no_extend:
        import pandas as pd

        path = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
        panel = pd.read_parquet(path)
        panel["date"] = pd.to_datetime(panel["date"])
        panel["panel_tier"] = "turnaround_full"
    else:
        panel = build_extended_panel(str(args.extend_from))

    report = run_reverse_engineer(panel)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["extend_from"] = None if args.no_extend else str(args.extend_from)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")

    print(render_md(report))
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
