#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.alpha_idea_queue import idea_queue_report
from src.research.frozen_decisions import decision_report
from src.research.stock_investment_data import data_surface_snapshot, load_thesis_register


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    obj = json.loads(path.read_text())
    return obj if isinstance(obj, dict) else {}


def _read_csv_records(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    return pd.read_csv(path).tail(limit).to_dict(orient="records")


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled read tools for investment agents.")
    sub = parser.add_subparsers(dest="tool", required=True)

    sub.add_parser("capability-status")
    sub.add_parser("data-status")
    sub.add_parser("idea-queue")
    sub.add_parser("decision-report")
    sub.add_parser("accounting-report")
    sub.add_parser("accounting-bundle")
    sub.add_parser("operator-dashboard")

    c = sub.add_parser("candidate-registry")
    c.add_argument("--limit", type=int, default=20)

    c = sub.add_parser("thesis-register")
    c.add_argument("--limit", type=int, default=20)

    c = sub.add_parser("factor-tearsheet")
    c.add_argument("--path", type=Path, required=True)

    args = parser.parse_args()
    if args.tool == "capability-status":
        out = _read_json(ROOT / "reports/investment_capabilities/latest.json")
    elif args.tool == "data-status":
        out = data_surface_snapshot(ROOT)
    elif args.tool == "idea-queue":
        out = idea_queue_report(ROOT / "config/alpha_idea_queue.csv")
    elif args.tool == "decision-report":
        out = decision_report(ROOT / "backtests/outputs/investment_cockpit/frozen_decisions.csv")
    elif args.tool == "accounting-report":
        out = _read_json(ROOT / "reports/accounting_reconciliation/latest.json")
    elif args.tool == "accounting-bundle":
        out = _read_json(ROOT / "reports/accounting_bundle/latest.json")
    elif args.tool == "operator-dashboard":
        out = _read_json(ROOT / "reports/investment_operator/latest.json")
    elif args.tool == "candidate-registry":
        out = {
            "path": "backtests/outputs/investment_cockpit/candidates/registry.csv",
            "rows": _read_csv_records(ROOT / "backtests/outputs/investment_cockpit/candidates/registry.csv", args.limit),
        }
    elif args.tool == "thesis-register":
        df = load_thesis_register(ROOT / "config/thesis_register.csv")
        out = {"path": "config/thesis_register.csv", "rows": df.tail(args.limit).to_dict(orient="records")}
    elif args.tool == "factor-tearsheet":
        out = _read_json(args.path)
    else:
        raise SystemExit(f"unknown tool: {args.tool}")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
