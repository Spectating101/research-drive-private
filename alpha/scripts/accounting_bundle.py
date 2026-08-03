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

from src.research.accounting_bundle import build_accounting_bundle, write_accounting_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a canonical accounting bundle for a strategy run.")
    parser.add_argument("--strategy", default="alpha_eventproxy_cfg12")
    parser.add_argument("--run-id", default="current_alpha")
    parser.add_argument("--as-of")
    parser.add_argument("--target-weights", type=Path)
    parser.add_argument("--target-signal", type=Path, default=ROOT / "backtests/outputs/signals/alpha_live_signal.json")
    parser.add_argument("--orders", type=Path)
    parser.add_argument("--fills", type=Path)
    parser.add_argument("--positions", type=Path)
    parser.add_argument("--equity-ledger", type=Path, default=ROOT / "backtests/outputs/alpha_paper/ledger.csv")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "backtests/outputs/alpha_paper/scorecard_latest.json")
    parser.add_argument("--safety-config", type=Path, default=ROOT / "config/execution_safety.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/accounting_bundle")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    bundle = build_accounting_bundle(
        repo=ROOT,
        strategy=args.strategy,
        run_id=args.run_id,
        as_of=args.as_of,
        target_weights_path=args.target_weights,
        target_signal_path=args.target_signal,
        orders_path=args.orders,
        fills_path=args.fills,
        positions_path=args.positions,
        equity_ledger_path=args.equity_ledger,
        scorecard_path=args.scorecard,
        safety_config_path=args.safety_config,
    )
    paths = write_accounting_bundle(bundle, args.out_dir)
    summary = {
        "status": bundle.get("status"),
        "complete": bundle.get("complete"),
        "missing_artifacts": bundle.get("missing_artifacts", []),
        "out": paths["latest_json"],
    }
    print(json.dumps(bundle if args.json else summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
