#!/usr/bin/env python3
"""YZU Cluster integration audit — verify scattered components work together.

No DeepSeek required. Exercises config cross-refs, API surface, and safe job paths.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)


def _get(url: str, timeout: float = 15.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: float = 30.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_job(base: str, job_id: str, *, timeout: float = 300.0, poll: float = 2.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _get(f"{base}/yzu/jobs/{job_id}")
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(poll)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


def _approve_job(base: str, job_id: str) -> dict[str, Any]:
    return _post(f"{base}/yzu/jobs/{job_id}/approve", {})


class AuditResult:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": "ok", "detail": detail})

    def warn(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "warn", "detail": detail})

    def fail(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "fail", "detail": detail})

    def summary(self) -> dict[str, Any]:
        counts = {"ok": 0, "warn": 0, "fail": 0}
        for row in self.checks:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"counts": counts, "checks": self.checks, "passed": counts["fail"] == 0}


def audit_config(result: AuditResult) -> None:
    yzu = json.loads((ROOT / "config/yzu_cluster.json").read_text(encoding="utf-8"))
    queue = json.loads((ROOT / "config/data_collection_queue.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "config/research_query_registry.json").read_text(encoding="utf-8"))

    result.ok("config/yzu_cluster.json", f"pools={list(yzu['worker_pools'].keys())}")

    pipeline_ids = set(yzu.get("pipelines", {}))
    for sched in yzu.get("schedules", []):
        jt = (sched.get("plan") or {}).get("job_type")
        if jt and jt not in yzu.get("agent", {}).get("allowed_job_types", []):
            result.fail("schedule job_type", f"{sched.get('id')}: {jt} not in allowed_job_types")

    runnable = [t for t in queue.get("tasks", []) if t.get("enabled") and not t.get("credential_required")]
    result.ok("collection_queue runnable", f"{len(runnable)} public tasks")

    reg_ids = {d.get("dataset_id") for d in registry.get("datasets", [])}
    if "collection_queue_status" not in reg_ids:
        result.warn("registry", "collection_queue_status missing from registry")
    else:
        result.ok("registry collection_queue_status", "queryable ops dataset present")

    inv = Path(yzu["worker_pools"]["windows_lab"]["inventory"])
    if inv.exists():
        import csv

        with inv.open(encoding="utf-8-sig", newline="") as handle:
            joined = sum(1 for row in csv.DictReader(handle) if row.get("status") == "joined")
        result.ok("windows inventory", f"{joined} joined workers")
    else:
        result.warn("windows inventory", f"missing: {inv}")

    shards = ROOT / "scripts/data_catalog/datacite_y2025_parallel_shards.list"
    if shards.exists():
        n = sum(1 for line in shards.read_text().splitlines() if line.strip() and not line.startswith("#"))
        result.ok("datacite shard list", f"{n} shards defined")
    else:
        result.fail("datacite shard list", "missing shards file")


def audit_api(base: str, result: AuditResult) -> None:
    try:
        health = _get(f"{base}/health")
    except Exception as exc:
        result.fail("API /health", str(exc))
        return
    if health.get("status") == "ok":
        result.ok("API /health", base)
    else:
        result.fail("API /health", str(health))

    components = _get(f"{base}/yzu/components")
    if components.get("allowed_job_types"):
        result.ok("API /yzu/components", f"{len(components['allowed_job_types'])} job types")
    else:
        result.fail("API /yzu/components", "empty")

    tasks = _get(f"{base}/yzu/queue/tasks")
    runnable = [t for t in tasks.get("tasks", []) if t.get("runnable")]
    if runnable:
        result.ok("API /yzu/queue/tasks", f"{len(runnable)} runnable")
    else:
        result.fail("API /yzu/queue/tasks", "no runnable tasks")

    datasets = _get(f"{base}/datasets")
    n = len(datasets.get("datasets", []))
    result.ok("API /datasets", f"{n} registry datasets")

    status = _get(f"{base}/yzu/status")
    jobs = status.get("jobs", {})
    result.ok("API /yzu/status", f"jobs={jobs}")

    acq = _get(f"{base}/yzu/acquisitions")
    if len(acq.get("acquisitions", [])) >= 3:
        result.ok("API /yzu/acquisitions", f"{len(acq['acquisitions'])} pipelines tracked")
    else:
        result.warn("API /yzu/acquisitions", "few acquisition rows")

    library_jobs = _get(f"{base}/library/jobs?limit=5")
    if isinstance(library_jobs.get("jobs"), list):
        result.ok("library/jobs", f"{len(library_jobs['jobs'])} recent job(s)")
    else:
        result.warn("library/jobs", "unexpected response shape")


def audit_job_path(base: str, result: AuditResult, *, execute: bool) -> None:
    if not execute:
        result.warn("job execution", "skipped (--no-execute)")
        return

    # 1. source_probe — procurement connector, no worker pool
    probe = _post(
        f"{base}/yzu/jobs",
        {
            "title": "integration: source_probe",
            "auto_approve": True,
            "plan": {"job_type": "source_probe", "url": "https://www.sec.gov/files/company_tickers.json", "launchable": True},
        },
    )
    probe = _wait_job(base, probe["id"], timeout=60)
    connector_id = (probe.get("result") or {}).get("connector_id")
    if probe["status"] == "completed" and connector_id:
        result.ok("job source_probe", connector_id)
    else:
        result.fail("job source_probe", probe.get("error") or probe["status"])

    # 2. collection_queue_batch dry-run — validates queue runner wiring
    batch = _post(
        f"{base}/yzu/jobs",
        {
            "title": "integration: queue dry-run",
            "auto_approve": True,
            "plan": {
                "job_type": "collection_queue_batch",
                "only": ["sec_company_tickers"],
                "dry_run": True,
                "launchable": True,
                "timeout_seconds": 120,
            },
        },
    )
    batch = _wait_job(base, batch["id"], timeout=120)
    if batch["status"] == "completed":
        result.ok("job collection_queue_batch dry_run", batch.get("result", {}).get("only", ""))
    elif batch["status"] == "failed":
        err = str(batch.get("error") or "").lower()
        if "powershell" in err or "parsererror" in err or "unexpectedtoken" in err:
            result.warn("job collection_queue_batch dry_run", "windows_lab PowerShell argv quoting — run on optiplex pool")
        else:
            result.fail("job collection_queue_batch dry_run", batch.get("error") or batch["status"])

    # 3. harvest_shard status — local read-only, no restart
    shards_file = ROOT / "scripts/data_catalog/datacite_y2025_parallel_shards.list"
    local_shard = None
    for line in shards_file.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        shard, host, *_ = line.split("|", 3)
        if host == "local":
            local_shard = shard
            break
    if local_shard:
        hs = _post(
            f"{base}/yzu/jobs",
            {
                "title": "integration: harvest status",
                "auto_approve": True,
                "plan": {"job_type": "harvest_shard", "shard": local_shard, "action": "status", "launchable": True},
            },
        )
        hs = _wait_job(base, hs["id"], timeout=60)
        if hs["status"] == "completed":
            result.ok("job harvest_shard status", local_shard)
        else:
            result.fail("job harvest_shard status", hs.get("error") or hs["status"])
    else:
        result.warn("job harvest_shard status", "no local shard in list")

    # 4. plan validation only — scraper, pipeline, archive
    orch = subprocess.run(
        [sys.executable, "-c", "from scripts.yzu_cluster.orchestrator import YzuOrchestrator; o=YzuOrchestrator(); print(o.validate_plan({'job_type':'scraper_run','script_key':'cake_board','launchable':True}))"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if orch.returncode == 0 and "validation_error" not in orch.stdout:
        result.ok("plan scraper_run", "cake_board allowlisted")
    else:
        result.fail("plan scraper_run", orch.stderr or orch.stdout)

    engine_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from pathlib import Path; from scripts.yzu_cluster.spectator_engine import SpectatorEngine; "
            "root=Path('.').resolve(); cfg=json.loads((root/'config/yzu_cluster.json').read_text()); "
            "e=SpectatorEngine(root,cfg); print('optiplex', e.probe_pool('optiplex')); print('order', ','.join(e.pool_order({'job_type':'scraper_run'})))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if engine_probe.returncode == 0 and "optiplex True" in engine_probe.stdout:
        result.ok("spectator_engine optiplex", engine_probe.stdout.strip().split("\n")[-1])
    elif engine_probe.returncode == 0:
        result.warn("spectator_engine optiplex", "run scripts/yzu_cluster/install_spectator_engine.sh on controller")
    else:
        result.fail("spectator_engine probe", engine_probe.stderr or engine_probe.stdout)

    bad = subprocess.run(
        [sys.executable, "-c", "from scripts.yzu_cluster.orchestrator import YzuOrchestrator; o=YzuOrchestrator(); p=o.validate_plan({'job_type':'registered_pipeline','pipeline_id':'missing','launchable':True}); print(p.get('launchable'))"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if bad.stdout.strip() == "False":
        result.ok("plan registered_pipeline guard", "rejects unknown pipeline")
    else:
        result.fail("plan registered_pipeline guard", bad.stdout + bad.stderr)

    # 5. BigQuery dry-run — cost guard only, no row fetch
    bq = _post(
        f"{base}/yzu/jobs",
        {
            "title": "integration: bigquery dry-run",
            "auto_approve": True,
            "plan": {
                "job_type": "bigquery_query",
                "sql_file": "sql/bigquery/usdt/01_daily_usdt_flows_recent.sql",
                "dry_run": True,
                "launchable": True,
            },
        },
    )
    bq = _wait_job(base, bq["id"], timeout=120)
    if bq["status"] == "completed":
        within = (bq.get("result") or {}).get("within_guard")
        result.ok("job bigquery_query dry_run", f"within_guard={within}")
    elif bq["status"] == "failed":
        err = str(bq.get("error") or "").lower()
        if "credentials" in err or "project is required" in err or "google" in err:
            result.warn("job bigquery_query dry_run", "no Google ADC — set GOOGLE_APPLICATION_CREDENTIALS")
        else:
            result.fail("job bigquery_query dry_run", bq.get("error") or bq["status"])

    # 6. Scraper lane — generic_url_scrape on example.com (manual approve)
    scrape = _post(
        f"{base}/yzu/jobs",
        {
            "title": "integration: generic scrape",
            "auto_approve": True,
            "plan": {
                "job_type": "scraper_run",
                "script_key": "generic_url_scrape",
                "url": "https://example.com",
                "launchable": True,
                "timeout_seconds": 120,
            },
        },
    )
    scrape_id = scrape["id"]
    if scrape.get("status") == "pending_approval":
        scrape = _approve_job(base, scrape_id)
    scrape = _wait_job(base, scrape_id, timeout=180)
    if scrape["status"] == "completed":
        result.ok("job scraper_run example.com", (scrape.get("result") or {}).get("pool", "done"))
    elif scrape["status"] == "failed":
        detail = str(scrape.get("error") or "")[:200]
        if "spectator" in detail.lower() or "playwright" in detail.lower():
            result.warn("job scraper_run example.com", detail)
        else:
            result.fail("job scraper_run example.com", detail)
    else:
        result.warn("job scraper_run example.com", scrape.get("status", "timeout"))


def main() -> int:
    parser = argparse.ArgumentParser(description="YZU Cluster integration audit")
    parser.add_argument("--api", default="http://127.0.0.1:8765", help="API base URL")
    parser.add_argument("--no-execute", action="store_true", help="Skip live job execution")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    result = AuditResult()
    audit_config(result)
    try:
        audit_api(args.api, result)
        audit_job_path(args.api, result, execute=not args.no_execute)
    except urllib.error.URLError as exc:
        result.fail("API reachability", str(exc))

    report = result.summary()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report["checks"]:
            mark = {"ok": "✓", "warn": "!", "fail": "✗"}[row["status"]]
            detail = f" — {row['detail']}" if row.get("detail") else ""
            print(f"  {mark} {row['name']}{detail}")
        c = report["counts"]
        print(f"\n{ c['ok']} ok, {c['warn']} warn, {c['fail']} fail")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
