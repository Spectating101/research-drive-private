#!/usr/bin/env python3
"""Recover jobs stuck in running state after worker crash."""

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

from scripts.yzu_cluster.orchestrator import YzuOrchestrator


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-hours", type=float, default=2.0, help="Mark running jobs older than N hours as failed")
    parser.add_argument("--requeue", action="store_true", help="Requeue stale jobs instead of failing them")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    orch = YzuOrchestrator(ROOT)
    now = datetime.now(UTC)
    recovered: list[dict] = []
    with orch.store._db() as db:
        running_ids = [row[0] for row in db.execute("SELECT id FROM jobs WHERE status='running'")]
    for jid in running_ids:
        job = orch.store.get(jid)
        if job.get("status") != "running":
            continue
        updated = _parse_ts(job.get("updated_at"))
        if not updated:
            continue
        age_h = (now - updated).total_seconds() / 3600.0
        if age_h < args.stale_hours:
            continue
        jid = str(job["id"])
        row = {"id": jid, "title": job.get("title"), "age_hours": round(age_h, 2)}
        if args.dry_run:
            row["action"] = "requeue" if args.requeue else "fail"
        elif args.requeue:
            orch.store.update(jid, "queued", error="")
            orch.store.event(jid, "warn", f"Requeued after stale running ({age_h:.1f}h)")
            row["action"] = "requeued"
        else:
            msg = f"stale running job recovered after {age_h:.1f}h"
            orch.store.update(jid, "failed", error=msg)
            orch.store.event(jid, "error", msg)
            row["action"] = "failed"
        recovered.append(row)

    out = {"stale_hours": args.stale_hours, "recovered": len(recovered), "jobs": recovered, "dry_run": args.dry_run}
    path = ROOT / "docs/status/generated/stale_jobs_recovered.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
