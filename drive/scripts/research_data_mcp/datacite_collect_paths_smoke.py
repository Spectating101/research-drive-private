#!/usr/bin/env python3
"""Live smoke: one-click UI path + legacy agent tool path for DataCite procurement."""

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

from scripts.research_data_mcp.bootstrap import create_stack

DEFAULT_DOI = "10.5281/zenodo.7545157"
DEFAULT_QUERY = "FaIR calibration climate"
DEFAULT_REPORT = ROOT / "docs/status/generated/datacite_collect_paths_latest.json"


def _post(api: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{api}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode())


def run_smoke(*, api: str, doi: str, query: str, report_path: Path) -> dict:
    report: dict = {"steps": [], "ok": False}
    stack = create_stack(ROOT)
    tools = stack.tools

    def step(name: str, ok: bool, **detail: object) -> None:
        row = {"step": name, "ok": ok, **detail}
        report["steps"].append(row)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}: {detail or ''}")

    # --- Agent path (MCP tools) ---
    search = tools.datacite_search(query=query, created="2023", page_size=8)
    rows = search.get("rows") or []
    step("agent_datacite_search", bool(rows), hits=len(rows))

    picked_doi = doi
    for row in rows:
        if "zenodo" in str(row.get("url") or ""):
            picked_doi = str(row["doi"])
            break
    step("agent_pick_doi", bool(picked_doi), doi=picked_doi)

    resolved = tools.datacite_resolve_repository(picked_doi)
    files = resolved.get("files") or []
    step("agent_resolve_repository", bool(files), repository=resolved.get("repository"), files=len(files))

    agent_out = tools.datacite_collect_doi(picked_doi, auto_execute=True)
    agent_job = agent_out.get("job") or {}
    agent_cid = agent_out.get("campaign_id")
    step(
        "agent_collect_doi",
        agent_job.get("status") == "completed" or agent_out.get("executed"),
        status=agent_job.get("status"),
        campaign_id=agent_cid,
        phase=agent_out.get("phase"),
    )

    arts_agent = stack.gateway.list_campaign_artifacts(agent_cid) if agent_cid else {"artifact_count": 0}
    step("agent_artifacts", arts_agent.get("artifact_count", 0) > 0, count=arts_agent.get("artifact_count"))

    # --- One-click UI path (HTTP) ---
    try:
        one_click = _post(
            api,
            "/library/datacite/collect",
            {"doi": picked_doi, "auto_execute": True},
        )
        ui_job = one_click.get("job") or {}
        ui_cid = one_click.get("campaign_id")
        step(
            "ui_one_click_collect",
            ui_job.get("status") == "completed" or one_click.get("executed"),
            status=ui_job.get("status"),
            campaign_id=ui_cid,
            file=one_click.get("plan", {}).get("datacite_file"),
        )
        arts_ui = stack.gateway.list_campaign_artifacts(ui_cid) if ui_cid else {"artifact_count": 0}
        step("ui_artifacts", arts_ui.get("artifact_count", 0) > 0, count=arts_ui.get("artifact_count"))

        if arts_ui.get("artifacts"):
            rel = arts_ui["artifacts"][0]["path"]
            q = urllib.parse.quote(rel, safe="/")
            with urllib.request.urlopen(f"{api}/library/campaigns/{ui_cid}/download?path={q}", timeout=60) as resp:
                body = resp.read(200)
            step("ui_download", len(body) > 20, bytes=len(body))
    except Exception as exc:
        step("ui_one_click_collect", False, error=str(exc))
        step("ui_artifacts", False)
        step("ui_download", False)

    # --- Direct DataCite collect (replaces removed /library/magic) ---
    try:
        collected = _post(
            api,
            "/library/datacite/collect",
            {"doi": picked_doi, "auto_execute": True},
        )
        step(
            "datacite_collect_doi",
            bool(collected.get("job", {}).get("id")) or collected.get("executed"),
            job_status=(collected.get("job") or {}).get("status"),
            doi=picked_doi,
        )
    except Exception as exc:
        step("datacite_collect_doi", False, error=str(exc))

    core_steps = {
        "agent_datacite_search",
        "agent_resolve_repository",
        "agent_collect_doi",
        "agent_artifacts",
        "ui_one_click_collect",
        "ui_artifacts",
    }
    report["ok"] = all(row["ok"] for row in report["steps"] if row["step"] in core_steps)
    report["doi"] = picked_doi
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="DataCite one-click + agent collect smoke")
    parser.add_argument("--api", default="http://127.0.0.1:8765")
    parser.add_argument("--doi", default=DEFAULT_DOI)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print("=" * 70)
    print("DATACITE COLLECT PATHS SMOKE")
    print("=" * 70)
    report = run_smoke(api=args.api, doi=args.doi, query=args.query, report_path=args.report)
    print(f"\nSCORE: {'PASS' if report['ok'] else 'FAIL'}  doi={report.get('doi')}")
    print(f"Report: {args.report}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
