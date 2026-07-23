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

from src.research.thesis_report import build_thesis_report, write_thesis_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate thesis register report.")
    parser.add_argument("--register", type=Path, default=ROOT / "config" / "thesis_register.csv")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "thesis_register")
    parser.add_argument("--stale-days", type=int, default=45)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_thesis_report(args.register, stale_days=args.stale_days)
    paths = write_thesis_report(report, args.out_dir)
    print(json.dumps(report if args.json else paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
