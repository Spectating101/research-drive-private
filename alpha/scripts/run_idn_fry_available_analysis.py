#!/usr/bin/env python3
"""Analyze fry using only on-disk collected data (structural, attention, broker)."""

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

from idn_fry_frame_lib import build_available_data_report  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    report = build_available_data_report()
    summary = {
        "structural_coverage_pct": report["meta"]["structural_coverage_pct"],
        "broker_coverage_pct": report["meta"]["broker_coverage_pct"],
        "rank_deciles_oos": report.get("rank_deciles_oos"),
        "live_watchlist_top": report.get("live_watchlist_top"),
        "output": str(REPO / "data_lake/research_panels/idn_fry_episode/fry_available_data_report.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
