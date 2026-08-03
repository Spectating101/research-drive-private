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

from src.research.alpha_idea_jobs import generate_idea_validation_jobs
from src.research.alpha_idea_queue import IDEA_COLUMNS, idea_queue_report, init_idea_queue, promote_idea, upsert_idea


DEFAULT_QUEUE = ROOT / "config" / "alpha_idea_queue.csv"


def _fields(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"expected key=value, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Alpha idea queue lifecycle.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("init")
    c.add_argument("--path", type=Path, default=DEFAULT_QUEUE)
    c.add_argument("--overwrite", action="store_true")

    c = sub.add_parser("add")
    c.add_argument("--path", type=Path, default=DEFAULT_QUEUE)
    c.add_argument("--field", action="append", required=True, help="column=value")

    c = sub.add_parser("promote")
    c.add_argument("--path", type=Path, default=DEFAULT_QUEUE)
    c.add_argument("--idea-id", required=True)
    c.add_argument("--status", required=True)
    c.add_argument("--validation-artifact", default="")
    c.add_argument("--notes", default="")

    c = sub.add_parser("report")
    c.add_argument("--path", type=Path, default=DEFAULT_QUEUE)

    c = sub.add_parser("generate-jobs")
    c.add_argument("--path", type=Path, default=DEFAULT_QUEUE)
    c.add_argument("--panel", type=Path, default=ROOT / "data_lake/daily_alpha_panel.csv")
    c.add_argument("--out-root", type=Path, default=ROOT / "backtests/outputs/investment_cockpit/idea_jobs")
    c.add_argument("--include-status", action="append", help="repeatable status; default validation-ready statuses")
    c.add_argument("--horizon-days", type=int, default=21)
    c.add_argument("--top-n", type=int, default=10)

    args = parser.parse_args()
    if args.cmd == "init":
        print(init_idea_queue(args.path, overwrite=args.overwrite))
    elif args.cmd == "add":
        row = _fields(args.field)
        unknown = sorted(set(row) - set(IDEA_COLUMNS))
        if unknown:
            raise SystemExit(f"unknown columns: {unknown}")
        print(upsert_idea(args.path, row))
    elif args.cmd == "promote":
        print(promote_idea(args.path, args.idea_id, args.status, validation_artifact=args.validation_artifact, notes=args.notes))
    elif args.cmd == "report":
        print(json.dumps(idea_queue_report(args.path), indent=2, sort_keys=True))
    elif args.cmd == "generate-jobs":
        statuses = set(args.include_status) if args.include_status else None
        report = generate_idea_validation_jobs(
            queue_csv=args.path,
            repo=ROOT,
            panel_csv=args.panel,
            out_root=args.out_root,
            include_statuses=statuses,
            horizon_days=args.horizon_days,
            top_n=args.top_n,
        )
        print(json.dumps({"out": str(args.out_root / "jobs.json"), "n_jobs": report["n_jobs"], "n_runnable": report["n_runnable"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
