#!/usr/bin/env python3
"""Ops diagnostic — score registry/plan/probe paths. Not part of professor product scope.

See docs/DESK_STATUS.md. For smoke: library_smoke.py, procurement_ops_smoke.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DEFAULT = ROOT / "docs/status/generated/sourcing_capability_latest.json"


@dataclass
class ScenarioResult:
    id: str
    category: str
    query: str
    guidance_score: int = 0
    acquisition_score: int = 0
    total: int = 0
    ms: int = 0
    ok: bool = False
    detail: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


def _score_guidance(candidates: list[dict], *, expect_any: list[str]) -> int:
    if not candidates:
        return 0
    blob = json.dumps(candidates, default=str).lower()
    hits = sum(1 for token in expect_any if token.lower() in blob)
    if hits >= 2:
        return 2
    if hits == 1:
        return 1
    return 0


def run_scenario(gw: Any, spec: dict[str, Any], *, execute: bool) -> ScenarioResult:
    sid = str(spec["id"])
    category = str(spec.get("category") or "general")
    query = str(spec.get("query") or "")
    t0 = time.time()
    res = ScenarioResult(id=sid, category=category, query=query)
    kind = str(spec.get("kind") or "local_search")

    try:
        if kind == "query_dataset":
            ds = str(spec["dataset_id"])
            params = dict(spec.get("params") or {})
            out = gw.query_dataset(ds, params)
            rows = list(out.get("rows") or [])
            res.extras["rows"] = len(rows)
            res.guidance_score = 2 if rows else 0
            res.acquisition_score = 3 if len(rows) >= int(spec.get("min_rows", 1)) else (1 if rows else 0)
            res.ok = len(rows) >= int(spec.get("min_rows", 1))
            res.detail = f"rows={len(rows)}"

        elif kind == "local_search":
            from scripts.research_data_mcp.procurement_fast import local_search

            out = local_search(gw, query, limit=int(spec.get("limit", 8)))
            cands = list(out.get("candidates") or [])
            res.extras["candidates"] = len(cands)
            res.extras["index_miss"] = out.get("index_miss")
            expect = list(spec.get("expect_tokens") or [])
            res.guidance_score = _score_guidance(cands, expect_any=expect)
            res.acquisition_score = 0
            res.ok = res.guidance_score >= int(spec.get("min_guidance", 1))
            top = cands[0] if cands else {}
            res.detail = f"cands={len(cands)} top={top.get('title','')[:50]} via={top.get('collect_via')}"

        elif kind == "plan_collect":
            from scripts.research_data_mcp.procurement_equipment_bridge import plan_collect_goal

            out = plan_collect_goal(gw, query, full_message=query)
            plan = out.get("plan") or {}
            res.extras["launchable"] = bool(out.get("launchable"))
            res.extras["job_type"] = plan.get("job_type")
            res.extras["task_id"] = plan.get("task_id")
            res.extras["pipeline_id"] = plan.get("pipeline_id")
            expect = list(spec.get("expect_tokens") or [])
            blob = json.dumps(out, default=str).lower()
            res.guidance_score = 2 if all(t.lower() in blob for t in expect[:2]) else (
                1 if any(t.lower() in blob for t in expect) else 0
            )
            if out.get("launchable"):
                res.acquisition_score = 1
            if execute and out.get("launchable") and spec.get("execute_allowed"):
                from scripts.research_data_mcp.procurement_equipment_bridge import collect_fast_goal

                collected = collect_fast_goal(gw, query, full_message=query, auto_approve=True)
                job = collected.get("job") or {}
                paths = collected.get("paths") or []
                res.extras["job_status"] = job.get("status")
                res.extras["paths"] = paths[:3]
                if paths or job.get("status") == "completed":
                    res.acquisition_score = 3
                    res.ok = True
                elif job.get("id"):
                    res.acquisition_score = 2
                    res.ok = job.get("status") in {"queued", "running", "completed"}
            else:
                res.ok = bool(out.get("launchable")) or res.guidance_score >= int(spec.get("min_guidance", 1))
            res.detail = (
                f"launchable={out.get('launchable')} "
                f"{plan.get('job_type') or ''} {plan.get('task_id') or plan.get('pipeline_id') or ''}"
            ).strip()

        elif kind == "collect_fast":
            from scripts.research_data_mcp.procurement_equipment_bridge import collect_fast_goal

            if not execute:
                from scripts.research_data_mcp.procurement_equipment_bridge import plan_collect_goal

                out = plan_collect_goal(gw, query, full_message=query)
                res.guidance_score = 2 if out.get("launchable") else 0
                res.ok = bool(out.get("launchable"))
                res.detail = f"dry launchable={out.get('launchable')}"
            else:
                out = collect_fast_goal(gw, query, full_message=query, auto_approve=True)
                paths = list(out.get("paths") or [])
                job = out.get("job") or {}
                res.extras["paths"] = paths[:3]
                res.extras["job_status"] = job.get("status")
                res.guidance_score = 2 if out.get("ok") else 0
                res.acquisition_score = 3 if paths else (2 if job.get("status") in {"queued", "running"} else 0)
                res.ok = bool(paths) or job.get("status") in {"completed", "queued", "running"}
                res.detail = f"ok={out.get('ok')} status={job.get('status')} paths={len(paths)}"

        elif kind == "probe":
            url = str(spec["url"])
            pr = gw.probe_source(url, str(spec.get("name") or url[:40]))
            conn = pr.get("connector") or {}
            res.extras["connector_status"] = conn.get("status")
            res.extras["summary"] = (pr.get("summary") or "")[:200]
            res.guidance_score = 2 if conn.get("status") else 0
            res.acquisition_score = 1 if conn.get("status") in {"candidate", "approved"} else 0
            res.ok = bool(conn.get("status"))
            res.detail = str(conn.get("status") or "no_connector")

        elif kind == "curl_baseline":
            url = str(spec["url"])
            dest = ROOT / "data_lake/procurement_audit/capability_curl" / sid
            dest.mkdir(parents=True, exist_ok=True)
            out_file = dest / "download.bin"
            ua = "SharpeRenaissance capability-test research@yzu.edu.tw"
            proc = subprocess.run(
                ["curl", "-fsSL", "-A", ua, "-o", str(out_file), url],
                capture_output=True,
                text=True,
                timeout=int(spec.get("timeout", 60)),
            )
            nbytes = out_file.stat().st_size if out_file.is_file() else 0
            res.guidance_score = 1
            res.acquisition_score = 3 if proc.returncode == 0 and nbytes > 0 else 0
            res.ok = proc.returncode == 0 and nbytes > 0
            res.extras["bytes"] = nbytes
            res.detail = f"curl rc={proc.returncode} bytes={nbytes}"

        else:
            res.detail = f"unknown kind {kind}"
    except Exception as exc:
        res.detail = f"error: {exc}"[:240]
        res.ok = False

    res.ms = int((time.time() - t0) * 1000)
    res.total = res.guidance_score + res.acquisition_score
    return res


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "registry_gdelt_twn",
        "category": "lab_registry",
        "kind": "query_dataset",
        "query": "GDELT Taiwan daily panel",
        "dataset_id": "gdelt_asia_daily_country_panel",
        "params": {"country": "TWN", "limit": 5},
        "min_rows": 1,
    },
    {
        "id": "registry_twse",
        "category": "lab_registry",
        "kind": "query_dataset",
        "query": "TWSE market layer",
        "dataset_id": "twse_openapi_taiwan_market_layer",
        "params": {"limit": 3},
        "min_rows": 1,
    },
    {
        "id": "registry_skynet",
        "category": "lab_registry",
        "kind": "query_dataset",
        "query": "Skynet stablecoin harvest",
        "dataset_id": "skynet_stablecoin_harvest",
        "params": {"limit": 3},
        "min_rows": 1,
    },
    {
        "id": "registry_sec",
        "category": "lab_registry",
        "kind": "query_dataset",
        "query": "SEC company tickers",
        "dataset_id": "sec_company_tickers",
        "params": {"limit": 1},
        "min_rows": 1,
    },
    {
        "id": "search_twse",
        "category": "catalog_search",
        "kind": "local_search",
        "query": "taiwan TWSE daily equity market disclosures",
        "expect_tokens": ["twse", "taiwan"],
        "min_guidance": 1,
    },
    {
        "id": "search_skynet",
        "category": "catalog_search",
        "kind": "local_search",
        "query": "certik skynet stablecoin security scores",
        "expect_tokens": ["skynet", "stablecoin"],
        "min_guidance": 1,
    },
    {
        "id": "search_usdt",
        "category": "catalog_search",
        "kind": "local_search",
        "query": "ethereum USDT on-chain transfer data",
        "expect_tokens": ["usdt", "ethereum"],
        "min_guidance": 1,
    },
    {
        "id": "search_obscure",
        "category": "index_miss",
        "kind": "local_search",
        "query": "baby diaper brand consumer survey panel dataset",
        "expect_tokens": ["survey", "consumer"],
        "min_guidance": 0,
    },
    {
        "id": "plan_twse_refresh",
        "category": "collect_plan",
        "kind": "plan_collect",
        "query": "refresh taiwan TWSE openapi market layer",
        "expect_tokens": ["twse_openapi", "twse"],
        "execute_allowed": False,
    },
    {
        "id": "plan_skynet_pipeline",
        "category": "collect_plan",
        "kind": "plan_collect",
        "query": "harvest certik skynet stablecoin leaderboard",
        "expect_tokens": ["skynet_stablecoin", "skynet"],
        "execute_allowed": False,
    },
    {
        "id": "plan_sec_url",
        "category": "collect_execute",
        "kind": "collect_fast",
        "query": "https://www.sec.gov/files/company_tickers.json",
        "execute_allowed": True,
    },
    {
        "id": "probe_sec",
        "category": "probe",
        "kind": "probe",
        "url": "https://www.sec.gov/files/company_tickers.json",
    },
    {
        "id": "probe_skynet",
        "category": "probe",
        "kind": "probe",
        "url": "https://skynet.certik.com/leaderboards/stablecoin",
    },
    {
        "id": "baseline_curl_sec",
        "category": "chatgpt_baseline",
        "kind": "curl_baseline",
        "query": "curl SEC tickers (no catalog)",
        "url": "https://www.sec.gov/files/company_tickers.json",
    },
]


def run_harness(*, execute: bool) -> dict[str, Any]:
    from scripts.research_data_mcp.bootstrap import create_stack

    gw = create_stack(ROOT).gateway
    results = [run_scenario(gw, spec, execute=execute) for spec in SCENARIOS]
    by_cat: dict[str, list[ScenarioResult]] = {}
    for row in results:
        by_cat.setdefault(row.category, []).append(row)

    def _avg(rows: list[ScenarioResult], key: str) -> float:
        if not rows:
            return 0.0
        return sum(getattr(r, key) for r in rows) / len(rows)

    summary = {
        "scenario_count": len(results),
        "execute_mode": execute,
        "totals": {
            "guidance": sum(r.guidance_score for r in results),
            "acquisition": sum(r.acquisition_score for r in results),
            "total": sum(r.total for r in results),
            "passed": sum(1 for r in results if r.ok),
        },
        "by_category": {
            cat: {
                "count": len(rows),
                "passed": sum(1 for r in rows if r.ok),
                "avg_guidance": round(_avg(rows, "guidance_score"), 2),
                "avg_acquisition": round(_avg(rows, "acquisition_score"), 2),
            }
            for cat, rows in by_cat.items()
        },
        "cluster_jobs": gw.orchestrator.stats(),
        "scenarios": [asdict(r) for r in results],
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sourcing capability harness")
    parser.add_argument("--execute", action="store_true", help="Run safe collect_fast (SEC URL)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    report = run_harness(execute=args.execute)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        t = report["totals"]
        print(f"Scenarios: {t['passed']}/{report['scenario_count']} passed")
        print(f"Scores — guidance: {t['guidance']}, acquisition: {t['acquisition']}, total: {t['total']}")
        for cat, row in report["by_category"].items():
            print(f"  {cat}: {row['passed']}/{row['count']} pass, guidance={row['avg_guidance']}, acq={row['avg_acquisition']}")
        print(f"Wrote {out_path}")
    return 0 if t["passed"] >= report["scenario_count"] - 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
