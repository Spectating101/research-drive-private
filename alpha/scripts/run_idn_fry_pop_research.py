#!/usr/bin/env python3
"""Full-timeline fry pop research — episodes, anatomy, huge winners, pattern catalog.

Runs multi-year daily panel (default 2019+) across full IDX fry pool:
  1. Fry episode FSM (trigger → wait → pop) on extended panel
  2. Trigger anatomy (pre-pop windows, pop vs no-pop profiles)
  3. Fry-only huge-winner pattern mining (20d/30d tails)
  4. Unified fry_pop_pattern_catalog.json for live monitors

Example:
  python alpha/scripts/run_idn_fry_pop_research.py
  python alpha/scripts/run_idn_fry_pop_research.py --extend-from 2019-07-01 --skip-episode
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_fry_pop_research_lib import CATALOG_JSON, REPORT_JSON, run_full_fry_pop_research  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Full-timeline fry pop research")
    ap.add_argument("--extend-from", default="2019-07-01", help="Start date for extended daily panel")
    ap.add_argument(
        "--skip-episode",
        action="store_true",
        help="Reuse fry_episodes.parquet on disk (anatomy + catalog only)",
    )
    args = ap.parse_args()

    report = run_full_fry_pop_research(
        extend_from=str(args.extend_from),
        skip_episode=bool(args.skip_episode),
    )
    compact = {
        "extend_from": args.extend_from,
        "timeline": report.get("episode_summary", {}),
        "n_triggers": report.get("anatomy", {}).get("n_triggers"),
        "pop_rate_pct": report.get("anatomy", {}).get("overall_pop_rate_pct"),
        "top_trigger_patterns": report.get("anatomy", {}).get("top_trigger_patterns"),
        "n_huge_episodes": report.get("huge_winner", {}).get("n_huge_episodes"),
        "top_huge_episodes": report.get("huge_winner", {}).get("top_episodes"),
        "catalog_patterns": report.get("catalog_patterns"),
        "catalog_path": str(CATALOG_JSON),
        "report_path": str(REPORT_JSON),
    }
    print(json.dumps(compact, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
