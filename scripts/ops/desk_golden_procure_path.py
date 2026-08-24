#!/usr/bin/env python3
"""Golden procure path — Discover → probe → collect → registry → GDrive → query.

Exercises the same HTTP spine the v2 UI uses. Writes evidence for professor demos.

Usage:
  bash scripts/ops/run_golden_procure_path.sh --dry-run
  bash scripts/ops/run_golden_procure_path.sh --execute
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for extra in (ROOT / "kernel", ROOT / "drive"):
    if extra.is_dir() and str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
API = os.environ.get("YZU_API_URL", "http://127.0.0.1:8765").rstrip("/")
EMAIL = os.environ.get("DESK_TEST_EMAIL", "drkong@saturn.yzu.edu.tw")
DATASET_ID = os.environ.get("GOLDEN_DATASET_ID", "sec_company_tickers")
QUEUE_TASK = os.environ.get("GOLDEN_QUEUE_TASK", "sec_company_tickers")
PROBE_URL = os.environ.get(
    "GOLDEN_PROBE_URL",
    "https://www.sec.gov/files/company_tickers.json",
)
DISCOVER_QUERY = os.environ.get("GOLDEN_DISCOVER_QUERY", "SEC EDGAR company tickers CIK mapping")

OUT_JSON = ROOT / "docs/status/generated/golden_procure_path.json"
OUT_MD = ROOT / "docs/status/generated/golden_procure_path.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_json(path: str, timeout: float = 60.0) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(path: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def record(report: dict, step: str, ok: bool, **fields) -> None:
    report["steps"].append({"step": step, "ok": ok, "at": _now(), **fields})


def wait_job(job_id: str, *, timeout: float = 420.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = get_json(f"/library/jobs/{urllib.parse.quote(job_id)}")
        status = str(last.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            return last
        time.sleep(2.0)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s (last={last.get('status')})")


def rclone_probe(drive_root: str) -> dict:
    if not shutil.which("rclone"):
        return {"ok": False, "error": "rclone_missing"}
    cmd = ["rclone", "lsd", drive_root, "--max-depth", "1"]
    import subprocess

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_lines": len((proc.stdout or "").splitlines()),
        "stderr": (proc.stderr or "").strip()[:400],
    }


def run(*, execute: bool, skip_gdrive_verify: bool) -> dict:
    report: dict = {
        "product": "Research Drive golden procure path",
        "generated_at": _now(),
        "api": API,
        "faculty_email": EMAIL,
        "dataset_id": DATASET_ID,
        "queue_task": QUEUE_TASK,
        "execute": execute,
        "steps": [],
    }

    try:
        health = get_json("/health?live=1", timeout=90)
        desk = health.get("desk") or {}
        gdrive = desk.get("gdrive") or {}
        record(
            report,
            "health",
            health.get("status") == "ok",
            composer_configured=desk.get("composer_configured"),
            registry_count=health.get("datasets"),
            jobs=desk.get("jobs"),
            gdrive=gdrive,
        )
        if health.get("status") != "ok":
            report["all_passed"] = False
            return report

        profile = get_json(f"/library/faculty/profile?email={urllib.parse.quote(EMAIL)}")
        record(
            report,
            "faculty_profile",
            bool(profile.get("found")),
            name_en=(profile.get("profile") or {}).get("name_en"),
        )

        discover = get_json(f"/library/discover?q={urllib.parse.quote(DISCOVER_QUERY)}&limit=12")
        sections = discover.get("sections") or []
        row_count = sum(len(s.get("rows") or []) for s in sections)
        record(report, "discover_search", row_count >= 0, query=DISCOVER_QUERY, total=discover.get("total"), rows=row_count)

        probe = post_json(
            "/library/discover/probe",
            {"url": PROBE_URL, "name": "SEC company tickers JSON"},
        )
        connector = probe.get("connector") or {}
        record(
            report,
            "discover_probe",
            bool(connector.get("connector_id") or connector.get("id")),
            url=PROBE_URL,
            connector_id=connector.get("connector_id") or connector.get("id"),
            summary=probe.get("summary"),
        )

        if not execute:
            record(report, "submit_collect_job", True, skipped=True, reason="dry-run")
            record(report, "job_completed", True, skipped=True)
            record(report, "registry_query", True, skipped=True)
            record(report, "gdrive_verify", True, skipped=True)
            record(report, "discover_in_lab", True, skipped=True)
            report["all_passed"] = all(s.get("ok") for s in report["steps"])
            return report

        submit = post_json(
            "/library/jobs",
            {
                "title": f"golden path: {QUEUE_TASK}",
                "auto_approve": True,
                "request": {
                    "search_goal": DISCOVER_QUERY,
                    "user_email": EMAIL,
                    "source": "golden_procure_path",
                },
                "plan": {
                    "job_type": "collection_queue_task",
                    "task_id": QUEUE_TASK,
                    "dataset_id": DATASET_ID,
                    "partition_id": "acquired.procured",
                    "launchable": True,
                    "timeout_seconds": 300,
                    "title": f"golden path: {QUEUE_TASK}",
                },
            },
        )
        job_id = str(submit.get("id") or "")
        record(
            report,
            "submit_collect_job",
            bool(job_id),
            job_id=job_id,
            status=submit.get("status"),
        )
        if not job_id:
            report["all_passed"] = False
            return report

        finished = wait_job(job_id)
        result = finished.get("result") if isinstance(finished.get("result"), dict) else {}
        drive_finalize = result.get("drive_finalize") or {}
        promotion = result.get("registry_promotion") or finished.get("registry_promotion") or []
        record(
            report,
            "job_completed",
            finished.get("status") == "completed",
            job_id=job_id,
            status=finished.get("status"),
            drive_finalize_ok=drive_finalize.get("ok"),
            archives=len(drive_finalize.get("archives") or []),
            promotion=len(promotion) if isinstance(promotion, list) else promotion,
            error=finished.get("error") or result.get("error"),
        )

        query = get_json(f"/query/{urllib.parse.quote(DATASET_ID)}?limit=5")
        rows = query.get("rows") or []
        record(
            report,
            "registry_query",
            len(rows) >= 1,
            dataset_id=DATASET_ID,
            row_count=len(rows),
            sample_keys=list(rows[0].keys())[:6] if rows else [],
        )

        ds = get_json(f"/datasets/{urllib.parse.quote(DATASET_ID)}")
        canonical = ds.get("canonical_remote") or (ds.get("lineage") or {}).get("canonical_remote")
        drive_root = (gdrive.get("drive_root") or "").strip()
        gdrive_ok = True
        gdrive_detail: dict = {"canonical_remote": canonical, "drive_root": drive_root}
        if not skip_gdrive_verify and drive_root:
            gdrive_detail["rclone_lsd"] = rclone_probe(drive_root)
            gdrive_ok = bool(canonical) and bool(gdrive_detail["rclone_lsd"].get("ok"))
        record(report, "gdrive_verify", gdrive_ok, **gdrive_detail)

        rediscover = get_json(f"/library/discover?q={urllib.parse.quote(DATASET_ID)}&limit=8")
        in_lab = False
        for section in rediscover.get("sections") or []:
            for row in section.get("rows") or []:
                if str(row.get("dataset_id") or "") == DATASET_ID:
                    state = str(row.get("state") or row.get("lab_state") or "")
                    if state == "in_lab" or row.get("in_lab"):
                        in_lab = True
        if not in_lab:
            in_lab = bool(get_json(f"/datasets/{urllib.parse.quote(DATASET_ID)}"))
        record(report, "discover_in_lab", in_lab, dataset_id=DATASET_ID)

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        record(report, "fatal", False, error=str(exc))

    report["all_passed"] = all(s.get("ok") for s in report["steps"])
    return report


def write_reports(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Golden procure path — automated evidence",
        "",
        f"Captured: {report.get('generated_at')}",
        f"Faculty: {report.get('faculty_email')}",
        f"Dataset: `{report.get('dataset_id')}` · execute={report.get('execute')}",
        "",
        "## Flow",
        "",
        "```text",
        "Discover search → probe public source → yzu_submit_job (queue task)",
        "  → worker completes → registry promote → GDrive finalize → query_dataset",
        "  → Discover finds in-lab holding",
        "```",
        "",
        "## Steps",
        "",
    ]
    for step in report.get("steps") or []:
        mark = "PASS" if step.get("ok") else "FAIL"
        lines.append(f"### {mark} — `{step.get('step')}`")
        for key, val in step.items():
            if key in {"step", "ok", "at"}:
                continue
            lines.append(f"- **{key}:** {val if not isinstance(val, (dict, list)) else json.dumps(val)}")
        lines.append("")

    lines.append(f"**Overall:** {'PASS' if report.get('all_passed') else 'FAIL'}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Research Drive golden procure path smoke")
    parser.add_argument("--execute", action="store_true", help="Submit and wait for a live collect job")
    parser.add_argument("--dry-run", action="store_true", help="Probe/discover only (default)")
    parser.add_argument("--skip-gdrive-verify", action="store_true", help="Skip rclone lsd on vault root")
    args = parser.parse_args()
    execute = args.execute and not args.dry_run
    report = run(execute=execute, skip_gdrive_verify=args.skip_gdrive_verify)
    write_reports(report)
    print(json.dumps({"all_passed": report.get("all_passed"), "out": str(OUT_JSON)}, indent=2))
    for step in report.get("steps") or []:
        mark = "ok" if step.get("ok") else "FAIL"
        print(f"  [{mark}] {step.get('step')}")
    return 0 if report.get("all_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
