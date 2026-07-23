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

from src.research.investment_enforcement import run_investment_enforcement_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the investment enforcement cycle.")
    parser.add_argument("--registry", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/candidates/registry.csv")
    parser.add_argument("--decision-log", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/frozen_decisions.csv")
    parser.add_argument("--panel", type=Path, default=ROOT / "data_lake/daily_alpha_panel.csv")
    parser.add_argument("--thesis-register", type=Path, default=ROOT / "config/thesis_register.csv")
    parser.add_argument("--capability-map", type=Path, default=ROOT / "config/investment_capability_map.json")
    parser.add_argument("--equity-ledger", type=Path, default=ROOT / "backtests/outputs/alpha_paper/ledger.csv")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "backtests/outputs/alpha_paper/scorecard_latest.json")
    parser.add_argument("--target-signal", type=Path, default=ROOT / "backtests/outputs/signals/alpha_live_signal.json")
    parser.add_argument("--target-weights", type=Path)
    parser.add_argument("--safety-config", type=Path, default=ROOT / "config/execution_safety.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports/investment_enforcement")
    parser.add_argument("--horizon-days", type=int, default=21)
    parser.add_argument("--as-of", help="Optional evaluation date for frozen decisions.")
    parser.add_argument("--exclude-blocked", action="store_true", help="Only freeze paper/deployable candidates.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_investment_enforcement_cycle(
        repo=ROOT,
        registry_csv=args.registry,
        decision_log=args.decision_log,
        panel_csv=args.panel,
        thesis_register=args.thesis_register,
        capability_map=args.capability_map,
        equity_ledger=args.equity_ledger,
        scorecard=args.scorecard,
        out_dir=args.out_dir,
        target_signal=args.target_signal,
        target_weights=args.target_weights,
        safety_config=args.safety_config,
        horizon_days=args.horizon_days,
        as_of=args.as_of,
        include_blocked=not args.exclude_blocked,
    )
    summary = {
        "status": report.get("status"),
        "passed": report.get("passed"),
        "warnings": report.get("warnings", []),
        "out": str(args.out_dir / "latest.json"),
    }
    print(json.dumps(report if args.json else summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
