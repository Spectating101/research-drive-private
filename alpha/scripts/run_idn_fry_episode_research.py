#!/usr/bin/env python3
"""Fry episode study — day-by-day move sorting + trigger→pop paths.

Not mean-5d hold returns. Sorts each calendar day's movers cross-sectionally,
walks fry episodes day-by-day, measures pop paths from trigger.

Output:
  data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet
  data_lake/research_panels/idn_fry_episode/fry_episode_days.parquet
  data_lake/research_panels/idn_fry_episode/fry_episodes.parquet
  data_lake/research_panels/idn_fry_episode/daily_calendar_heat.parquet
  data_lake/research_panels/idn_fry_episode/summary.json
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

from idn_fry_episode_lib import build_fry_episode_research  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Fry episode / daily move-sort research")
    ap.add_argument("--panel", type=Path, default=None, help="Override daily features parquet")
    ap.add_argument(
        "--extend-from",
        default=None,
        help="Build multi-year panel from idx_all (e.g. 2019-07-01); overrides --panel",
    )
    args = ap.parse_args()
    summary = build_fry_episode_research(args.panel, extend_from=args.extend_from)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
