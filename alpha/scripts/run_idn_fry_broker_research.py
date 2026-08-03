#!/usr/bin/env python3
"""Join fry triggers with broker-summary cache; measure lift and emit report."""

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

from idn_fry_broker_lib import build_fry_broker_report  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry broker lift research").parse_args()
    report = build_fry_broker_report()
    compact = {
        "coverage_pct": report["meta"]["coverage_pct"],
        "n_with_broker": report["meta"]["n_with_broker"],
        "baseline_broker_subset": report["broker_lift_analysis"].get("broker_subset_baseline_pop_pct"),
        "top_patterns": (report["broker_lift_analysis"].get("patterns") or [])[:5],
        "composite_rules": report["broker_lift_analysis"].get("composite_rules"),
        "interpretation": report["interpretation"],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
