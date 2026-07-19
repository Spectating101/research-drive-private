#!/usr/bin/env python3
"""Backfill registry + curated index from on-disk pipeline/harvest artifacts.

Use when bytes landed before auto-promotion was wired, or to refresh locators
after a manual harvest.

Examples:
  python scripts/research_data_mcp/flywheel_backfill.py --pipeline skynet_stablecoin_harvest
  python scripts/research_data_mcp/flywheel_backfill.py --all-pipelines
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def backfill_pipeline(stack, pipeline_id: str, *, search_goal: str = "") -> dict:
    promoter = stack.orchestrator.registry_promoter
    flywheel = stack.orchestrator.collection_flywheel
    if promoter is None or flywheel is None:
        raise RuntimeError("stack missing registry_promoter or collection_flywheel")

    job = {
        "id": f"backfill_{pipeline_id}",
        "status": "completed",
        "plan": {"job_type": "registered_pipeline", "pipeline_id": pipeline_id},
        "result": {},
        "request": {"search_goal": search_goal or f"backfill {pipeline_id}"},
    }
    promoted = promoter.promote_job(job)
    if not promoted:
        return {"pipeline_id": pipeline_id, "promoted": [], "flywheel": {}}

    stack.gateway.reload_registry()
    fw = flywheel.promote_after_collect(
        job,
        promoted,
        search_goal=search_goal or f"backfill {pipeline_id}",
    )
    return {"pipeline_id": pipeline_id, "promoted": promoted, "flywheel": fw}


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill registry from on-disk harvests")
    parser.add_argument("--pipeline", action="append", default=[], help="Pipeline id (repeatable)")
    parser.add_argument("--all-pipelines", action="store_true", help="Every pipeline in procurement_registry_map.json")
    parser.add_argument("--goal", default="", help="search_goal tag for curated rows")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    map_path = ROOT / "config/procurement_registry_map.json"
    pipelines = list(args.pipeline)
    if args.all_pipelines:
        doc = json.loads(map_path.read_text(encoding="utf-8"))
        pipelines = sorted((doc.get("pipelines") or {}).keys())

    if not pipelines:
        parser.error("pass --pipeline ID or --all-pipelines")

    from scripts.research_data_mcp.bootstrap import create_stack

    stack = create_stack(ROOT)
    results = [backfill_pipeline(stack, pid, search_goal=args.goal) for pid in pipelines]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for row in results:
            promo = row.get("promoted") or []
            fw = row.get("flywheel") or {}
            print(
                f"{row['pipeline_id']}: promoted={len(promo)} "
                f"curated+={fw.get('curated_added', 0)} locators+={fw.get('locators_added', 0)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
