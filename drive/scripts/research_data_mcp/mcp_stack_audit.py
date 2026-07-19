#!/usr/bin/env python3
"""Audit the procurement MCP toolbox — registry, query plane, search routes, tool tiers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DEFAULT = ROOT / "docs/status/generated/mcp_stack_audit.json"

QUERY_BACKENDS = frozenset(
    {
        "local_gdelt_panel_csv",
        "local_gdelt_high_priority_csv",
        "local_jsonl_catalog",
        "coingecko_simple_price_api",
        "local_json_file",
        "local_json_glob",
        "local_jsonl_payment_ledger",
        "usdt_bigquery_catalogue",
        "local_parquet_panel",
        "collection_ops_status",
        "datacite_local_harvest_status",
    }
)


def audit_stack(gateway: Any) -> dict[str, Any]:
    from scripts.research_data_mcp.procurement_constants import (
        MCP_TOOL_ACQUIRE,
        MCP_TOOL_CORE,
        MCP_TOOL_OPS,
    )
    from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES

    reg = gateway.engine.registry
    datasets = list(reg.get("datasets") or [])
    by_readiness: dict[str, int] = {}
    by_backend: dict[str, int] = {}
    no_query_handler: list[str] = []
    for row in datasets:
        r = str(row.get("analysis_readiness") or "?")
        b = str(row.get("backend") or "?")
        by_readiness[r] = by_readiness.get(r, 0) + 1
        by_backend[b] = by_backend.get(b, 0) + 1
        if b not in QUERY_BACKENDS:
            no_query_handler.append(str(row.get("dataset_id") or ""))

    instant_ok = 0
    instant_fail: list[dict[str, str]] = []
    for row in datasets:
        if row.get("analysis_readiness") != "instant":
            continue
        did = str(row.get("dataset_id") or "")
        try:
            gateway.query_dataset(did, {"limit": 1})
            instant_ok += 1
        except Exception as exc:
            instant_fail.append({"dataset_id": did, "error": str(exc)[:120]})

    tier_union = set(MCP_TOOL_CORE) | set(MCP_TOOL_ACQUIRE) | set(MCP_TOOL_OPS)
    unlisted = [n for n in MCP_TOOL_NAMES if n not in tier_union]

    parts_path = ROOT / "config/collection_partitions.json"
    partition_count = 0
    if parts_path.is_file():
        partition_count = len(json.loads(parts_path.read_text(encoding="utf-8")).get("partitions") or [])

    queue_path = ROOT / "config/data_collection_queue.json"
    queue_enabled = 0
    queue_total = 0
    if queue_path.is_file():
        tasks = json.loads(queue_path.read_text(encoding="utf-8")).get("tasks") or []
        queue_total = len(tasks)
        queue_enabled = sum(1 for t in tasks if t.get("enabled"))

    try:
        cluster = gateway.yzu.status()
        jobs = (cluster.get("jobs") or {}) if isinstance(cluster, dict) else {}
    except Exception as exc:
        cluster = {"error": str(exc)[:200]}
        jobs = {}

    from scripts.research_data_mcp.procurement_constants import ACQUISITION_LADDER, COMPOSER_EXTERNAL_TOOLS_NOTE

    return {
        "mcp_definition": "full data procurement toolbox (not protocol-only)",
        "orchestrator": "Composer via protocol tools; Python is passive equipment",
        "acquisition_ladder": list(ACQUISITION_LADDER),
        "composer_external_tools": COMPOSER_EXTERNAL_TOOLS_NOTE,
        "registry": {
            "total": len(datasets),
            "by_readiness": by_readiness,
            "by_backend": by_backend,
            "no_query_handler_count": len(no_query_handler),
            "instant_query_smoke": {"ok": instant_ok, "failed": instant_fail},
        },
        "vault": {"partitions": partition_count},
        "queue": {"total": queue_total, "enabled_public": queue_enabled},
        "protocol_tools": {
            "total": len(MCP_TOOL_NAMES),
            "core": list(MCP_TOOL_CORE),
            "acquire": list(MCP_TOOL_ACQUIRE),
            "ops": list(MCP_TOOL_OPS),
            "unlisted": unlisted,
        },
        "cluster_jobs": jobs,
        "cluster_status": cluster if "error" not in cluster else cluster,
        "health": {
            "ok": not instant_fail and instant_ok > 0,
            "notes": [
                "Composer: start with research_discover_search — see docs/COMPOSER_PROCUREMENT.md",
                "Use research_discover_search + research_faculty_profile for profiled search.",
                "Prefer yzu_submit_job(plan); magic_procure is legacy campaign resume only.",
                "Spectator scraper_run is the durable web extraction path (not ad-hoc browser).",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit procurement MCP toolbox")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--print", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args()

    from scripts.research_data_mcp.bootstrap import create_stack

    gateway = create_stack().gateway
    report = audit_stack(gateway)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.print:
        print(json.dumps(report, indent=2))
    else:
        print(f"wrote {args.out}")
        print(f"registry={report['registry']['total']} instant_ok={report['registry']['instant_query_smoke']['ok']}")
        print(f"protocol_tools={report['protocol_tools']['total']} unlisted={len(report['protocol_tools']['unlisted'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
