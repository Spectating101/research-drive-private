#!/usr/bin/env python3
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
ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.manifest_gates import manifest_gate_report, write_manifest_gate_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check candidate manifests for provenance and promotion evidence.")
    parser.add_argument("--registry", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/candidates/registry.csv")
    parser.add_argument("--decision-log", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/frozen_decisions.csv")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/manifest_gates")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = manifest_gate_report(args.registry, repo=ROOT, decision_log=args.decision_log)
    paths = write_manifest_gate_report(report, args.out_dir)
    print(json.dumps(report if args.json else paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
