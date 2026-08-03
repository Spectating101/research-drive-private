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

from src.research.frozen_decisions import (
    decision_report,
    evaluate_decisions,
    freeze_decision,
    freeze_from_candidate_registry,
    init_decision_log,
)


DEFAULT_LOG = ROOT / "backtests" / "outputs" / "investment_cockpit" / "frozen_decisions.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and evaluate candidate investment decisions.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("init")
    c.add_argument("--path", type=Path, default=DEFAULT_LOG)
    c.add_argument("--overwrite", action="store_true")

    c = sub.add_parser("freeze")
    c.add_argument("--path", type=Path, default=DEFAULT_LOG)
    c.add_argument("--decision-id", required=True)
    c.add_argument("--strategy", required=True)
    c.add_argument("--as-of", required=True)
    c.add_argument("--horizon-days", type=int, required=True)
    c.add_argument("--weights-path", required=True)
    c.add_argument("--signal-path", default="")
    c.add_argument("--thesis-id", default="")
    c.add_argument("--benchmark", default="SPY")
    c.add_argument("--status-at-decision", default="paper_candidate")

    c = sub.add_parser("evaluate")
    c.add_argument("--path", type=Path, default=DEFAULT_LOG)
    c.add_argument("--panel", type=Path, default=ROOT / "data_lake" / "daily_alpha_panel.csv")
    c.add_argument("--as-of")

    c = sub.add_parser("freeze-from-registry")
    c.add_argument("--path", type=Path, default=DEFAULT_LOG)
    c.add_argument("--registry", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/candidates/registry.csv")
    c.add_argument("--horizon-days", type=int, default=21)
    c.add_argument("--include-status", action="append", help="repeatable status; default paper_candidate/deployable_sleeve")

    c = sub.add_parser("report")
    c.add_argument("--path", type=Path, default=DEFAULT_LOG)

    args = parser.parse_args()
    if args.cmd == "init":
        print(init_decision_log(args.path, overwrite=args.overwrite))
    elif args.cmd == "freeze":
        print(
            freeze_decision(
                args.path,
                decision_id=args.decision_id,
                strategy=args.strategy,
                as_of=args.as_of,
                horizon_days=args.horizon_days,
                weights_path=args.weights_path,
                signal_path=args.signal_path,
                thesis_id=args.thesis_id,
                benchmark=args.benchmark,
                status_at_decision=args.status_at_decision,
            )
        )
    elif args.cmd == "evaluate":
        print(evaluate_decisions(args.path, panel_csv=args.panel, as_of=args.as_of))
    elif args.cmd == "freeze-from-registry":
        statuses = set(args.include_status) if args.include_status else None
        print(
            freeze_from_candidate_registry(
                args.path,
                registry_csv=args.registry,
                horizon_days=args.horizon_days,
                include_statuses=statuses,
            )
        )
    elif args.cmd == "report":
        print(json.dumps(decision_report(args.path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
