#!/usr/bin/env python3
"""Backend download CLI — source and fetch data without UI or chat LLM.

Examples:
  python scripts/research_data_mcp/procure_download.py url \\
    'https://www.sec.gov/files/company_tickers.json'

  python scripts/research_data_mcp/procure_download.py doi 10.5281/zenodo.7545157

  python scripts/research_data_mcp/procure_download.py search 'ocean temperature zenodo' --pick 1

  python scripts/research_data_mcp/procure_download.py message \\
    'download https://www.sec.gov/files/company_tickers.json into the lab library'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_data_mcp.procurement_constants import DOWNLOADABLE_VIA


def _wait_job(gateway: Any, job_id: str, *, ticks: int = 100, sleep: float = 0.2) -> dict[str, Any]:
    for _ in range(ticks):
        gateway.jobs.tick()
        job = gateway.get_yzu_job(job_id)
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(sleep)
    return gateway.get_yzu_job(job_id)


def _files_from_job(gateway: Any, job: dict[str, Any]) -> list[dict[str, Any]]:
    from scripts.research_data_mcp.procurement_delivery import procured_files_from_job

    return procured_files_from_job(gateway, job)


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        status = payload.get("status", "unknown")
        print(f"status: {status}")
        if payload.get("error"):
            print(f"error: {payload['error']}")
        for row in payload.get("files") or []:
            print(f"  file: {row.get('path')} ({row.get('bytes', 0)} bytes)")
        if payload.get("handle"):
            print(f"handle: {payload['handle']}")
        if payload.get("campaign_id"):
            print(f"campaign: {payload['campaign_id']}")
        if payload.get("job_id"):
            print(f"job: {payload['job_id']}")
    return 0 if payload.get("status") == "completed" else 1


def download_url(gateway: Any, url: str, *, title: str = "") -> dict[str, Any]:
    from scripts.research_data_mcp.scrape_plan import plan_for_url

    plan = plan_for_url(url.strip(), title=title or f"Download {url[:60]}")
    plan = gateway.orchestrator.validate_plan(plan)
    if plan.get("validation_error"):
        return {"status": "failed", "error": plan["validation_error"], "url": url}
    submitted = gateway.jobs.submit(plan.get("title", "Download"), plan, {"cli": True}, auto_approve=True)
    job = submitted.get("job") or {}
    job_id = str(job.get("id") or "")
    if not job_id:
        return {"status": "failed", "error": "job not submitted", "url": url}
    job = _wait_job(gateway, job_id)
    files = _files_from_job(gateway, job) if job.get("status") == "completed" else []
    return {
        "status": job.get("status", "unknown"),
        "url": url,
        "job_id": job_id,
        "job_type": plan.get("job_type"),
        "files": files,
        "error": job.get("error"),
        "destination": plan.get("destination"),
    }


def download_doi(gateway: Any, doi: str) -> dict[str, Any]:
    try:
        out = gateway.collect_datacite_doi(doi.strip(), auto_execute=True)
    except Exception as exc:
        return {"status": "failed", "doi": doi, "error": str(exc)}
    if out.get("blocked"):
        return {
            "status": "blocked",
            "doi": doi,
            "error": out.get("message") or (out.get("gate") or {}).get("blocked_reason"),
            "gate": out.get("gate"),
        }
    card = out.get("dataset_card") or {}
    job = out.get("job") or {}
    files: list[dict[str, Any]] = []
    if job.get("id"):
        files = _files_from_job(gateway, job) if job.get("status") == "completed" else []
    primary = card.get("primary_file") or {}
    if primary.get("path") and not files:
        files = [{"name": primary.get("name"), "path": primary.get("path"), "bytes": primary.get("bytes", 0)}]
    return {
        "status": "completed" if card.get("handle") or files else str(job.get("status") or "unknown"),
        "doi": doi,
        "campaign_id": out.get("campaign_id"),
        "job_id": job.get("id"),
        "handle": card.get("handle"),
        "files": files,
        "reused": bool(out.get("reused")),
    }


def download_search(gateway: Any, query: str, *, pick: int = 1) -> dict[str, Any]:
    from scripts.research_data_mcp.procurement_search import smart_search

    found = smart_search(gateway, query, limit=8)
    candidates = found.get("candidates") or []
    downloadable = [c for c in candidates if c.get("collect_via") in DOWNLOADABLE_VIA]
    # Prefer runnable infrastructure (queue/local) over external DOI when scores are close.
    via_rank = {"queue": 0, "local_open": 1, "http_manifest": 2, "datacite": 3, "huggingface": 4, "spectator": 5, "web_scrape": 6, "magic": 9}
    downloadable.sort(
        key=lambda c: (
            via_rank.get(str(c.get("collect_via") or ""), 8),
            -float(c.get("score") or 0),
        )
    )
    if not downloadable:
        return {
            "status": "failed",
            "query": query,
            "error": "no downloadable candidates — try a DOI, direct URL, or: procure_download.py message 'source ... for me'",
            "candidates": [{"index": c.get("index"), "title": c.get("title"), "collect_via": c.get("collect_via")} for c in candidates[:6]],
        }
    if pick < 1 or pick > len(downloadable):
        pick = 1
    choice = downloadable[pick - 1]
    via = str(choice.get("collect_via") or "")
    if via == "datacite" and choice.get("doi"):
        out = download_doi(gateway, str(choice["doi"]))
        out["picked"] = {"index": choice.get("index"), "title": choice.get("title"), "via": via}
        return out
    if via == "http_manifest" and choice.get("url"):
        out = download_url(gateway, str(choice["url"]), title=str(choice.get("title") or ""))
        out["picked"] = {"index": choice.get("index"), "title": choice.get("title"), "via": via}
        return out
    if via == "queue" and choice.get("dataset_id"):
        plan = {
            "job_type": "collection_queue_task",
            "task_id": str(choice.get("dataset_id") or choice.get("task_id")),
            "launchable": True,
            "title": str(choice.get("title") or "queue task"),
        }
        submitted = gateway.jobs.submit(plan["title"], plan, {"cli": True}, auto_approve=True)
        job = _wait_job(gateway, str((submitted.get("job") or {}).get("id")))
        return {
            "status": job.get("status", "unknown"),
            "query": query,
            "job_id": job.get("id"),
            "picked": {"index": choice.get("index"), "title": choice.get("title"), "via": via},
            "error": job.get("error"),
            "result": job.get("result"),
        }
    return {
        "status": "failed",
        "query": query,
        "error": f"candidate #{choice.get('index')} via {via} needs chat/acquire pipeline",
        "picked": choice,
    }


def download_message(gateway: Any, message: str) -> dict[str, Any]:
    plan = gateway.planner.plan_immediate_collect(message, {})
    if plan and plan.get("launchable"):
        if plan.get("datacite_doi") or plan.get("job_type") == "http_manifest":
            if plan.get("datacite_doi"):
                return download_doi(gateway, str(plan["datacite_doi"]))
            url = str(plan.get("url") or (plan.get("items") or [{}])[0].get("url") or "")
            if url:
                return download_url(gateway, url, title=str(plan.get("title") or ""))
        submitted = gateway.jobs.submit(
            str(plan.get("title") or "Collect"),
            plan,
            {"cli": True, "message": message},
            auto_approve=True,
        )
        job = _wait_job(gateway, str((submitted.get("job") or {}).get("id")))
        files = _files_from_job(gateway, job) if job.get("status") == "completed" else []
        return {
            "status": job.get("status", "unknown"),
            "message": message,
            "job_id": job.get("id"),
            "job_type": plan.get("job_type"),
            "files": files,
            "error": job.get("error"),
        }

    from scripts.research_data_mcp.procurement_equipment_bridge import plan_collect_goal, submit_collect_plan

    planned = plan_collect_goal(gateway, message, full_message=message)
    plan = planned.get("plan")
    if not plan or not planned.get("launchable"):
        return {
            "status": "failed",
            "message": message,
            "error": planned.get("validation_error")
            or "no launchable plan — use Research Drive chat (Composer + MCP) or yzu_submit_job(plan_json)",
            "candidates": planned.get("candidates") or [],
        }
    submitted = submit_collect_plan(
        gateway,
        plan,
        context={"cli": True, "message": message, "search_goal": message},
        auto_approve=True,
        goal=message,
    )
    job = _wait_job(gateway, str((submitted.get("job") or {}).get("id")))
    files = _files_from_job(gateway, job) if job.get("status") == "completed" else []
    return {
        "status": job.get("status", "unknown"),
        "message": message,
        "job_id": job.get("id"),
        "job_type": plan.get("job_type"),
        "files": files,
        "error": job.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download / procure research data (backend CLI)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("url", help="Download a direct HTTP(S) file URL")
    p_url.add_argument("url")

    p_doi = sub.add_parser("doi", help="Collect a DataCite / Zenodo DOI")
    p_doi.add_argument("doi")

    p_search = sub.add_parser("search", help="Search catalogs and download best match")
    p_search.add_argument("query")
    p_search.add_argument("--pick", type=int, default=1, help="1-based index among downloadable hits")

    p_topic = sub.add_parser("topic", help="Natural-language data need → search + download best runnable source")
    p_topic.add_argument("query")
    p_topic.add_argument("--pick", type=int, default=1)

    p_msg = sub.add_parser("message", help="Natural language collect (URL/DOI fast paths, else plan+job)")
    p_msg.add_argument("message")

    args = parser.parse_args()
    from scripts.research_data_mcp.bootstrap import create_stack

    gateway = create_stack(ROOT).gateway

    if args.cmd == "url":
        payload = download_url(gateway, args.url)
    elif args.cmd == "doi":
        payload = download_doi(gateway, args.doi)
    elif args.cmd == "search":
        payload = download_search(gateway, args.query, pick=args.pick)
    elif args.cmd == "topic":
        payload = download_search(gateway, args.query, pick=args.pick)
        payload["mode"] = "topic"
    else:
        payload = download_message(gateway, args.message)

    return _emit(payload, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
