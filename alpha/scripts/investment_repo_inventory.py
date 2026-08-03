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

from src.research.repo_inventory import build_repo_inventory, write_repo_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Build non-destructive repo pruning/rearrangement inventory.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/repo_inventory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_repo_inventory(ROOT)
    paths = write_repo_inventory(report, args.out_dir)
    summary = {
        "n_files": report["n_files"],
        "categories": report["category_counts"],
        "dispositions": report["disposition_counts"],
        "out": paths["json"],
    }
    print(json.dumps(report if args.json else summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
