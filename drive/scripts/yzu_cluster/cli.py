#!/usr/bin/env python3
"""YZU Cluster CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.research_data_mcp.bootstrap import create_stack


def main() -> int:
    parser = argparse.ArgumentParser(description="YZU Cluster control plane")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("components", help="Show wired components")
    sub.add_parser("stats", help="Job queue stats")

    jobs = sub.add_parser("jobs", help="List jobs")
    jobs.add_argument("--status", default="")
    jobs.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="Show one job")
    show.add_argument("job_id")

    submit = sub.add_parser("submit", help="Submit JSON plan from file or stdin")
    submit.add_argument("--title", default="YZU job")
    submit.add_argument("--plan", type=Path, help="JSON plan file")
    submit.add_argument("--approve", action="store_true")
    submit.add_argument(
        "--ops",
        action="store_true",
        help="Mark submit as trusted ops/controller (_ops_internal); required for non-generic job types",
    )

    approve = sub.add_parser("approve", help="Approve pending job")
    approve.add_argument("job_id")

    worker = sub.add_parser("worker-once", help="Run one worker tick")

    queue = sub.add_parser("queue", help="List collection queue tasks")
    queue.add_argument("--all", action="store_true")

    sched = sub.add_parser("schedules", help="List schedules")

    run_sched = sub.add_parser("run-schedule", help="Trigger schedule now")
    run_sched.add_argument("schedule_id")
    run_sched.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    stack = create_stack()
    orch = stack.orchestrator
    jobs_svc = stack.jobs

    if args.cmd == "components":
        print(json.dumps(orch.components(), indent=2))
        return 0
    if args.cmd == "stats":
        print(json.dumps(orch.stats(), indent=2))
        return 0
    if args.cmd == "jobs":
        rows = jobs_svc.list(args.limit, status=args.status)["jobs"]
        print(json.dumps(rows, indent=2))
        return 0
    if args.cmd == "show":
        print(json.dumps(jobs_svc.get(args.job_id), indent=2))
        return 0
    if args.cmd == "submit":
        if args.plan:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
        else:
            plan = json.loads(sys.stdin.read() or "{}")
        request = {"source": "yzu_cli"}
        if args.ops:
            request["_ops_internal"] = True
        job = jobs_svc.submit(args.title, plan, request, auto_approve=args.approve)["job"]
        if args.approve and job["status"] == "pending_approval":
            job = jobs_svc.approve(job["id"])
        print(json.dumps(job, indent=2))
        return 0
    if args.cmd == "approve":
        print(json.dumps(jobs_svc.approve(args.job_id), indent=2))
        return 0
    if args.cmd == "worker-once":
        print(json.dumps(jobs_svc.tick() or {"status": "idle"}, indent=2))
        return 0
    if args.cmd == "queue":
        print(json.dumps(orch.queue_tasks(runnable_only=not args.all), indent=2))
        return 0
    if args.cmd == "schedules":
        print(json.dumps(orch.schedules(), indent=2))
        return 0
    if args.cmd == "run-schedule":
        print(json.dumps(jobs_svc.run_schedule(args.schedule_id, dry_run=args.dry_run), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
