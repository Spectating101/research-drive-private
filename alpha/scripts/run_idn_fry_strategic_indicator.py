#!/usr/bin/env python3
"""Strategic fry indicator gap audit + tier stack."""

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

from idn_fry_strategic_indicator_lib import build_strategic_indicator_report  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry strategic indicator research").parse_args()
    report = build_strategic_indicator_report()
    compact = {
        "pop_rate_reconciliation": report["pop_rate_reconciliation"],
        "data_gaps_headline": report["data_gap_inventory"]["headline"],
        "priority_data_lanes": report["data_gap_inventory"]["priority_order"],
        "recommended_tier": report["strategic_indicator_tiers"]["recommended_operational"],
        "broker_queue_size": report["broker_backfill_queue_size"],
        "collection_roadmap": report["collection_roadmap"],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
