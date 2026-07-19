#!/usr/bin/env python3
"""DataCite procurement E2E — metadata discovery → repository file → artifacts delivery.

Run (library server on :8765):
  .venv/bin/python scripts/research_data_mcp/datacite_procure_e2e.py

Honest scope:
  - DataCite bulk harvest shards are METADATA-ONLY (jsonl.gz DOI records).
  - User-facing dataset bytes come from the repository behind the DOI (Zenodo, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_data_mcp import datacite_client
from scripts.research_data_mcp.bootstrap import create_stack

DEFAULT_REPORT = ROOT / "docs/status/generated/datacite_procure_e2e_latest.json"


def zenodo_files(landing_url: str, max_bytes: int = 5_000_000) -> list[dict]:
    rec_id = landing_url.rstrip("/").split("/")[-1]
    payload = json.loads(urllib.request.urlopen(f"https://zenodo.org/api/records/{rec_id}", timeout=45).read())
    files = []
    for row in payload.get("files") or []:
        size = int(row.get("size") or 0)
        if size > max_bytes:
            continue
        files.append(
            {
                "key": row.get("key"),
                "size": size,
                "url": (row.get("links") or {}).get("self"),
            }
        )
    return sorted(files, key=lambda f: int(f.get("size") or 0))


def run_e2e(*, api: str, query: str, report_path: Path) -> dict:
    report: dict = {"steps": [], "ok": False}
    stack = create_stack(ROOT)
    gw = stack.gateway

    def step(name: str, ok: bool, **detail: object) -> None:
        row = {"step": name, "ok": ok, **detail}
        report["steps"].append(row)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}: {detail.get('detail', detail)}")

    search = datacite_client.search(query, created="2023", page_size=8)
    rows = search.get("rows") or []
    step("datacite_search", bool(rows), detail=f"{len(rows)} hits total={search.get('total')}")

    doi = landing = ""
    for row in rows:
        if "zenodo" in str(row.get("url") or ""):
            doi, landing = str(row["doi"]), str(row["url"])
            break
    if not doi and rows:
        doi, landing = str(rows[0]["doi"]), str(rows[0].get("url") or "")
    step("pick_doi", bool(doi), doi=doi, landing=landing)

    meta = datacite_client.get_doi(doi)
    step("datacite_get_doi", bool(meta.get("title")), title=meta.get("title"))

    files = zenodo_files(landing) if "zenodo" in landing else []
    chosen = files[0] if files else None
    step("repository_files", bool(chosen), file_count=len(files), chosen=(chosen or {}).get("key"))

    campaign = stack.campaigns.create(f"DataCite E2E: {meta.get('title')}", {"doi": doi, "landing": landing})
    cid = campaign["id"]

    probe = gw.submit_yzu_job(
        {"job_type": "source_probe", "url": landing, "launchable": True, "timeout_seconds": 120},
        title=f"probe {doi}",
        request={"campaign_id": cid},
        auto_approve=True,
    )
    pid = probe["job"]["id"]
    for _ in range(60):
        stack.orchestrator.worker_tick()
        pj = gw.get_yzu_job(pid)
        if pj.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1)
    probe_spec = (pj.get("result") or {}).get("probe") or {}
    step(
        "source_probe_landing",
        pj.get("status") == "completed",
        status=pj.get("status"),
        discovered_files=len(probe_spec.get("discovered_files") or []),
    )

    if not chosen:
        report["ok"] = False
        report["campaign_id"] = cid
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    rec_id = landing.rstrip("/").split("/")[-1]
    collect = gw.submit_yzu_job(
        {
            "job_type": "http_manifest",
            "title": meta.get("title") or doi,
            "connector_id": f"datacite_{doi.replace('/', '_')}",
            "url": landing,
            "items": [{"url": chosen["url"], "filename": chosen["key"]}],
            "destination": f"data_lake/procured/datacite_{rec_id}",
            "launchable": True,
            "timeout_seconds": 300,
        },
        title=f"collect {chosen['key']}",
        request={"campaign_id": cid, "doi": doi},
        auto_approve=True,
    )
    job_id = collect["job"]["id"]
    for _ in range(120):
        stack.orchestrator.worker_tick()
        job = gw.get_yzu_job(job_id)
        if job.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1)
    mat = (job.get("result") or {}).get("materialized") or {}
    step(
        "http_manifest_collect",
        job.get("status") == "completed" and bool(mat.get("files")),
        status=job.get("status"),
        files=[f.get("name") for f in mat.get("files") or []],
        registry_promotion=len((job.get("result") or {}).get("registry_promotion") or []),
    )

    stack.campaigns.update(
        cid,
        phase="ready",
        status="ready",
        payload={"collect_job_ids": [job_id], "probe_job_ids": [pid], "doi": doi},
    )
    arts = gw.list_campaign_artifacts(cid)
    step("artifacts_list", arts.get("artifact_count", 0) > 0, count=arts.get("artifact_count"))

    download_ok = False
    preview = ""
    if arts.get("artifacts"):
        rel = arts["artifacts"][0]["path"]
        q = urllib.parse.quote(rel, safe="/")
        with urllib.request.urlopen(f"{api}/library/campaigns/{cid}/download?path={q}", timeout=60) as resp:
            body = resp.read(400)
        download_ok = len(body) > 40
        preview = body[:100].decode("utf-8", errors="replace")
    step("artifacts_download", download_ok, preview=preview)

    try:
        req = urllib.request.Request(
            f"{api}/library/datacite/collect",
            data=json.dumps({"doi": doi, "auto_execute": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            collected = json.loads(resp.read().decode())
        routed = bool((collected.get("job") or {}).get("id")) or collected.get("executed")
        step(
            "datacite_collect_route",
            routed,
            doi=doi,
            job_status=(collected.get("job") or {}).get("status"),
        )
    except Exception as exc:
        step("datacite_collect_route", False, error=str(exc))

    core_ok = all(row["ok"] for row in report["steps"] if row["step"] != "datacite_collect_route")
    report.update(
        {
            "ok": core_ok,
            "campaign_id": cid,
            "doi": doi,
            "delivery_note": (
                "DataCite API = metadata. Payload files resolved via repository (Zenodo API). "
                "Bulk harvest shards remain metadata-only."
            ),
        }
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="DataCite procure E2E test")
    parser.add_argument("--api", default="http://127.0.0.1:8765")
    parser.add_argument("--query", default="FaIR calibration climate")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print("=" * 70)
    print("DATACITE PROCURE E2E")
    print("=" * 70)
    report = run_e2e(api=args.api, query=args.query, report_path=args.report)
    print(f"\nSCORE: {'PASS' if report['ok'] else 'FAIL'}  campaign={report.get('campaign_id')}")
    print(f"Report: {args.report}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
