#!/usr/bin/env python3
"""Bilateral fry research — pops, sinks, grind paths, playbook."""

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

from idn_fry_bilateral_lib import build_bilateral_research  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry bilateral pop+sink research").parse_args()
    report = build_bilateral_research()
    compact = {
        "outcome_shares": report.get("trigger_outcome_taxonomy", {}).get("outcome_shares_pct"),
        "bilateral_movement": report.get("bilateral_movement"),
        "sink_profile": report.get("sink_day_profile"),
        "separation_insights": report.get("trigger_outcome_taxonomy", {}).get("separation_insights"),
        "playbook": report.get("playbook"),
        "confidence_tiers": report.get("confidence_tiers"),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
