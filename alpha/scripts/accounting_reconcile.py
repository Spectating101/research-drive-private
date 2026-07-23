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

from src.research.accounting_reconciliation import reconcile_accounting, write_reconciliation_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile investment accounting artifacts.")
    parser.add_argument("--target-weights", type=Path)
    parser.add_argument("--orders", type=Path)
    parser.add_argument("--fills", type=Path)
    parser.add_argument("--positions", type=Path)
    parser.add_argument("--equity-ledger", type=Path, default=ROOT / "backtests/outputs/alpha_paper/ledger.csv")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "backtests/outputs/alpha_paper/scorecard_latest.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/accounting_reconciliation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = reconcile_accounting(
        target_weights_path=args.target_weights,
        orders_path=args.orders,
        fills_path=args.fills,
        positions_path=args.positions,
        equity_ledger_path=args.equity_ledger,
        scorecard_path=args.scorecard,
    )
    paths = write_reconciliation_report(report, args.out_dir)
    print(json.dumps(report if args.json else paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
