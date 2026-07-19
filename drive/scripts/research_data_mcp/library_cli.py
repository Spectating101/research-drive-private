#!/usr/bin/env python3
"""CLI for ResearchDataGateway — library API without MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Research data library CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("overview", help="Library buckets by readiness")
    sub.add_parser("catalog", help="Procurement catalog browse")

    cat = sub.add_parser("catalog-search")
    cat.add_argument("q")

    advise = sub.add_parser("advise", help="Dataset librarian recommendation")
    advise.add_argument("goal")
    advise.add_argument("--current-dataset", default="")
    advise.add_argument("--current-task", default="")

    submit = sub.add_parser("submit-job")
    submit.add_argument("--plan", type=Path, required=True)
    submit.add_argument("--title", default="CLI job")
    submit.add_argument("--approve", action="store_true")

    archive = sub.add_parser("archive")
    archive.add_argument("local_path")
    archive.add_argument("--remote-suffix", default="")
    archive.add_argument("--approve", action="store_true")

    show = sub.add_parser("job")
    show.add_argument("job_id")

    sub.add_parser("components", help="YZU cluster components")
    sub.add_parser("smoke", help="Run library smoke test")

    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from scripts.research_data_mcp.bootstrap import create_stack

    gateway = create_stack(ROOT).gateway

    if args.cmd == "overview":
        payload = gateway.library_overview()
    elif args.cmd == "catalog":
        payload = gateway.procurement_catalog()
    elif args.cmd == "catalog-search":
        payload = gateway.procurement_catalog(q=args.q)
    elif args.cmd == "advise":
        payload = gateway.advise_datasets(
            args.goal,
            current_dataset_id=args.current_dataset,
            current_task_id=args.current_task,
        )
    elif args.cmd == "submit-job":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        payload = gateway.submit_yzu_job(plan, title=args.title, auto_approve=args.approve)
    elif args.cmd == "archive":
        payload = gateway.archive_to_gdrive(args.local_path, remote_suffix=args.remote_suffix, auto_approve=args.approve)
    elif args.cmd == "job":
        payload = gateway.get_yzu_job(args.job_id)
    elif args.cmd == "components":
        payload = gateway.cluster_components()
    elif args.cmd == "smoke":
        from scripts.research_data_mcp.library_smoke import run_smoke

        payload = run_smoke(execute_jobs=True, skip_gdrive=True)
    else:
        raise RuntimeError(args.cmd)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
