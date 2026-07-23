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

from src.research.capability_audit import audit_capabilities, write_report


DEFAULT_CONFIG = ROOT / "config" / "investment_capability_map.json"
DEFAULT_OUT = ROOT / "reports" / "investment_capabilities"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit stock-investment platform capabilities and external-project learnings.")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true", help="print report JSON to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_capabilities(args.repo, args.config)
    paths = write_report(report, args.out_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
