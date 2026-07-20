#!/usr/bin/env python3
"""Triage pending_approval jobs — approve safe types, optionally cancel stale."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# resolve() follows scripts/ → drive/scripts/, so parents[2] is drive/ not repo.
_HERE = Path(__file__).resolve()
ROOT = next(
    (p for p in _HERE.parents if (p / "kernel" / "sharpe_kernel").is_dir()),
    _HERE.parents[3],
)
for extra in (ROOT, ROOT / "kernel", ROOT / "drive"):
    p = str(extra)
    if extra.is_dir() and p not in sys.path:
        sys.path.insert(0, p)

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)

from scripts.research_data_mcp.procurement_auto_approve import should_auto_approve_plan
from scripts.yzu_cluster.orchestrator import YzuOrchestrator


def _noise_reason(job: dict) -> str:
    """Return cancel reason for known backlog noise, else empty string."""
    plan = job.get("plan") or {}
    job_type = str(plan.get("job_type") or "")
    title = str(job.get("title") or "").lower()
    url = str(plan.get("url") or "").lower()

    if job_type == "scraper_run" and (
        plan.get("script_key") == "generic_url_scrape" and "example.com" in url
        or title.startswith("integration:")
    ):
        return "integration_scrape"
    if job_type == "collection_queue_batch":
        return "duplicate_batch"
    # Remote workers only claim http_manifest; these sit forever as denied_job_type.
    if job_type == "synthesis_execute":
        return "denied_job_type_remote_worker"
    jid = str(job.get("id") or "")
    if job_type == "source_probe" and jid.startswith("probe-no-promotion"):
        return "fixture_probe_no_promotion"
    if job_type == "http_manifest" and (
        jid.startswith("archive-before-promote") or jid.startswith("missing-manifest-")
    ):
        return "fixture_http_manifest_stuck"
    if job_type == "harvest_shard" and str(plan.get("action") or "") in {"restart", "harvest"}:
        return "destructive_shard_action"
    if job_type == "collection_queue_task" and str(plan.get("task_id") or "").startswith("gdelt_gkg_asia_monthly_backlog"):
        return "heavy_gdelt_duplicate"
    if job_type == "registered_pipeline" and plan.get("pipeline_id") == "collection_queue":
        return "redundant_pipeline"
    return ""


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-safe", action="store_true", help="Approve jobs matching auto-approve policy")
    parser.add_argument("--cancel-noise", action="store_true", help="Cancel integration dupes, stale batches, and risky shard restarts")
    parser.add_argument("--cancel-stale-days", type=int, default=0, help="Cancel pending jobs older than N days (0=off)")
    parser.add_argument("--recover-stale-hours", type=float, default=0, help="Fail running jobs older than N hours (0=off)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    if not args.approve_safe and not args.cancel_stale_days and not args.cancel_noise and not args.recover_stale_hours:
        parser.error("specify --approve-safe, --cancel-noise, --recover-stale-hours, and/or --cancel-stale-days")

    orch = YzuOrchestrator(ROOT)
    pending = orch.store.list(args.limit, status="pending_approval")
    now = datetime.now(UTC)
    approved = 0
    cancelled = 0
    skipped = 0
    recovered = 0
    report: list[dict] = []

    cancelled_ids: set[str] = set()

    if args.recover_stale_hours:
        from scripts.yzu_cluster.recover_stale_jobs import _parse_ts as parse_job_ts

        for job in orch.store.list(args.limit):
            if job.get("status") != "running":
                continue
            updated = parse_job_ts(job.get("updated_at"))
            if not updated:
                continue
            age_h = (now - updated).total_seconds() / 3600.0
            if age_h < args.recover_stale_hours:
                continue
            jid = str(job["id"])
            if not args.dry_run:
                orch.store.update(jid, "failed", error=f"stale running recovered ({age_h:.1f}h)")
                orch.store.event(jid, "error", "stale running recovered via triage")
            recovered += 1
            report.append({"id": jid, "action": "fail_stale_running", "age_hours": round(age_h, 2)})

    if args.cancel_noise:
        # Drain queued/running/pending jobs that remote workers will never claim.
        for job in orch.store.list(args.limit):
            status = str(job.get("status") or "")
            if status not in {"queued", "running", "pending_approval"}:
                continue
            reason = _noise_reason(job)
            if not reason:
                continue
            jid = str(job.get("id") or "")
            row = {
                "id": jid,
                "job_type": (job.get("plan") or {}).get("job_type"),
                "title": job.get("title"),
                "status": status,
                "action": "cancel",
                "reason": reason,
            }
            if not args.dry_run:
                # orchestrator.cancel only accepts pending/queued
                if status == "running":
                    orch.store.update(jid, "failed", error=f"triage noise: {reason}")
                    orch.store.event(jid, "error", f"cancelled noise while running ({reason})")
                else:
                    orch.cancel(jid)
            cancelled += 1
            cancelled_ids.add(jid)
            report.append(row)

    for job in pending:
        jid = str(job.get("id") or "")
        if jid in cancelled_ids:
            continue
        plan = job.get("plan") or {}
        created = _parse_ts(job.get("created_at"))
        age_days = (now - created).days if created else 0
        row = {"id": jid, "job_type": plan.get("job_type"), "title": job.get("title"), "age_days": age_days}

        if args.cancel_stale_days and age_days >= args.cancel_stale_days:
            row["action"] = "cancel"
            if not args.dry_run:
                orch.cancel(jid)
            cancelled += 1
            report.append(row)
            continue

        if args.approve_safe:
            if should_auto_approve_plan(plan, ROOT, orchestrator=orch):
                row["action"] = "approve"
                if not args.dry_run:
                    orch.approve(jid)
                approved += 1
            else:
                row["action"] = "skip"
                skipped += 1
            report.append(row)

    out = {
        "pending_total": len(pending),
        "approved": approved,
        "cancelled": cancelled,
        "skipped": skipped,
        "recovered_stale_running": recovered,
        "dry_run": args.dry_run,
        "sample": report[:20],
    }
    out_path = ROOT / "docs/status/generated/pending_triage_latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
