#!/usr/bin/env python3
"""Library smoke test — exercise ResearchDataGateway without MCP transport.

Runs: catalog browse → advisor → procure (dry-run) → optional GDrive archive plan.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    from scripts.research_data_mcp.env_loader import load_procurement_env

    load_procurement_env(ROOT)


def _tick_until_done(gateway, job_id: str, timeout: float = 300.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = gateway.get_yzu_job(job_id)
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        if job.get("status") == "queued":
            gateway.orchestrator.worker_tick()
        time.sleep(1.5)
    raise TimeoutError(job_id)


def run_smoke(*, execute_jobs: bool, skip_gdrive: bool) -> dict:
    from scripts.research_data_mcp.bootstrap import create_stack

    gateway = create_stack(ROOT).gateway
    report: dict = {"steps": []}

    overview = gateway.library_overview()
    report["steps"].append({"step": "library_overview", "total_datasets": overview["total_datasets"], "ok": True})

    catalog = gateway.procurement_catalog(q="sec equity filings", limit=15)
    report["steps"].append(
        {
            "step": "procurement_catalog",
            "runnable_queue_tasks": catalog["summary"]["runnable_queue_tasks"],
            "gdrive_root": catalog["summary"]["gdrive_root"],
            "ok": catalog["summary"]["runnable_queue_tasks"] > 0,
        }
    )

    wrong = gateway.advise_datasets(
        "US equity SEC EDGAR filings for event study on S&P 500",
        current_dataset_id="gdelt_asia_daily_country_panel",
        limit=5,
    )
    sec_recs = [r for r in (wrong.get("recommended") or []) if str(r.get("id", "")).startswith("sec_")]
    report["steps"].append(
        {
            "step": "advise_datasets",
            "verdict": wrong.get("verdict"),
            "message": wrong.get("message"),
            "top_recommendation": (wrong.get("recommended") or [{}])[0],
            "engine": wrong.get("engine"),
            "ok": bool(sec_recs)
            and wrong.get("verdict") in {"good_fit", "partial_fit", "wrong_fit"},
        }
    )

    components = gateway.cluster_components()
    report["steps"].append({"step": "cluster_components", "job_types": len(components["allowed_job_types"]), "ok": True})

    api_port = int(os.getenv("YZU_API_PORT", "8765"))
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{api_port}/library/extensions/tools", timeout=5) as resp:
            ext = json.loads(resp.read().decode("utf-8"))
        report["steps"].append(
            {
                "step": "http_extensions",
                "tool_count": ext.get("count"),
                "ok": int(ext.get("count") or 0) >= 30,
            }
        )
    except Exception as exc:
        report["steps"].append({"step": "http_extensions", "error": str(exc), "ok": False})

    if execute_jobs:
        submitted = gateway.submit_yzu_job(
            {
                "job_type": "collection_queue_batch",
                "only": ["sec_company_tickers"],
                "dry_run": True,
                "launchable": True,
                "timeout_seconds": 120,
            },
            title="smoke: queue dry-run",
            auto_approve=True,
        )
        job = submitted["job"]
        assert job
        finished = _tick_until_done(gateway, job["id"], timeout=120)
        report["steps"].append(
            {
                "step": "procure_dry_run",
                "job_id": job["id"],
                "status": finished["status"],
                "ok": finished["status"] == "completed",
            }
        )

        real = gateway.submit_yzu_job(
            {
                "job_type": "collection_queue_task",
                "task_id": "sec_company_tickers",
                "launchable": True,
                "timeout_seconds": 300,
            },
            title="smoke: sec_company_tickers live",
            auto_approve=True,
        )
        real_job = real["job"]
        assert real_job
        real_finished = _tick_until_done(gateway, real_job["id"], timeout=300)
        promotion = (real_finished.get("result") or {}).get("registry_promotion") or []
        query = gateway.query_dataset("sec_company_tickers", {"fields": "0.ticker"})
        if not (query.get("rows") or []):
            from scripts.research_data_mcp.registry_hydrate import ensure_dataset_hydrated

            hydrate = ensure_dataset_hydrated(ROOT, "sec_company_tickers")
            if not hydrate.get("ok") and not hydrate.get("skipped"):
                import subprocess

                sec_out = ROOT / "data_lake/sec/company_tickers.json"
                subprocess.run(
                    [
                        str(ROOT / ".venv/bin/python"),
                        str(ROOT / "scripts/sec_fetch_company_tickers.py"),
                        "--out",
                        str(sec_out),
                    ],
                    cwd=ROOT,
                    check=False,
                    timeout=120,
                )
            query = gateway.query_dataset("sec_company_tickers", {"fields": "0.ticker"})
        report["steps"].append(
            {
                "step": "procure_sec_live",
                "job_id": real_job["id"],
                "status": real_finished["status"],
                "registry_promotion": promotion,
                "query_returned": len(query.get("rows") or []),
                "ok": real_finished["status"] == "completed"
                and bool(promotion)
                and len(query.get("rows") or []) >= 1,
            }
        )
    else:
        report["steps"].append({"step": "procure_dry_run", "skipped": True, "ok": True})
        report["steps"].append({"step": "procure_sec_live", "skipped": True, "ok": True})

    tickers = ROOT / "data_lake/sec/company_tickers.json"
    if not skip_gdrive and tickers.exists() and shutil.which("rclone"):
        archive = gateway.archive_to_gdrive(
            "data_lake/sec/company_tickers.json",
            remote_suffix="sec/company_tickers.json",
            auto_approve=True,
        )
        job = archive.get("job")
        if job:
            finished = _tick_until_done(gateway, job["id"], timeout=600)
            report["steps"].append(
                {
                    "step": "archive_gdrive",
                    "job_id": job["id"],
                    "status": finished["status"],
                    "ok": finished["status"] == "completed",
                }
            )
        else:
            report["steps"].append({"step": "archive_gdrive", "error": archive.get("error"), "ok": False})
    else:
        report["steps"].append(
            {
                "step": "archive_gdrive",
                "skipped": True,
                "reason": "RESEARCH_LIBRARY_SMOKE_SKIP_GDRIVE or missing rclone/artifact",
                "ok": True,
            }
        )

    report["passed"] = all(step.get("ok") for step in report["steps"])
    return report


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Research data library smoke test")
    parser.add_argument("--no-execute", action="store_true", help="Skip live job execution")
    parser.add_argument("--skip-gdrive", action="store_true", help="Skip rclone archive step")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if os.getenv("RESEARCH_LIBRARY_SMOKE_SKIP_GDRIVE"):
        args.skip_gdrive = True

    report = run_smoke(execute_jobs=not args.no_execute, skip_gdrive=args.skip_gdrive)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for step in report["steps"]:
            mark = "✓" if step.get("ok") else "✗"
            name = step["step"]
            extra = {k: v for k, v in step.items() if k not in {"step", "ok"}}
            print(f"  {mark} {name} {extra}")
        print(f"\n{'PASSED' if report['passed'] else 'FAILED'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
