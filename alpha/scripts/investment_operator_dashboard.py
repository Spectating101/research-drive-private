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

from src.research.operator_dashboard import build_operator_dashboard, write_operator_dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the stock-investment operator dashboard report.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/investment_operator")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_operator_dashboard(ROOT)
    paths = write_operator_dashboard(report, args.out_dir)
    print(json.dumps(report if args.json else {"status": report.get("status"), "warnings": report.get("warnings", []), "out": paths["json"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
