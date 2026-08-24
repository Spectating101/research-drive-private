#!/usr/bin/env python3
"""Queue Etherscan token-page scrapes on windows_lab (SSH workers — not local optiplex)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.scrape_plan import build_generic_scrape_plan
from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab, write_status_file
from stablecoin_skynet.unified_dataset import (
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
    load_etherscan_index,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_POOL = "windows_lab"


def targets(*, skynet_harvest: Path, scrapes_root: Path) -> list[dict[str, str]]:
    rows, _ = build_unified_dataset(skynet_harvest_dir=skynet_harvest, scrapes_root=scrapes_root)
    indexed = set(load_etherscan_index(scrapes_root))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not row.get("in_skynet_leaderboard") or row.get("in_etherscan_stablecoin_list"):
            continue
        addr = str(row.get("primary_ethereum_address") or "").lower()
        if not addr or addr in indexed or addr in seen:
            continue
        seen.add(addr)
        out.append(
            {
                "slug": row.get("skynet_slug") or "",
                "address": addr,
                "name": row.get("skynet_name") or "",
                "url": f"https://etherscan.io/token/{addr}",
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skynet-harvest", type=Path, default=DEFAULT_SKYNET_HARVEST)
    parser.add_argument("--scrapes-root", type=Path, default=DEFAULT_SCRAPES_ROOT)
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to submit (0 = all)")
    parser.add_argument("--sleep-secs", type=float, default=2.0, help="Pause between submissions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pool", default=DEFAULT_POOL, help="Worker pool (default: windows_lab)")
    parser.add_argument("--skip-readiness", action="store_true", help="Submit even if remote scraper host is not ready")
    parser.add_argument("--no-auto-approve", action="store_true")
    args = parser.parse_args()

    cfg = json.loads((REPO / "config/yzu_cluster.json").read_text(encoding="utf-8"))
    readiness = probe_windows_lab(cfg, force=True)
    write_status_file(REPO, readiness)
    if args.pool == "windows_lab" and not args.skip_readiness and not readiness.get("scraper_ready"):
        print(json.dumps(readiness, indent=2), file=sys.stderr)
        print(
            "\nwindows_lab scraper hosts are not ready. "
            "Run: bash scripts/yzu_cluster/provision_windows_scraper_bundle.sh\n"
            "Or pass --skip-readiness to queue anyway (jobs will fail until provisioned).",
            file=sys.stderr,
        )
        return 2

    todo = targets(skynet_harvest=args.skynet_harvest, scrapes_root=args.scrapes_root)
    if args.limit > 0:
        todo = todo[: args.limit]

    report = {
        "targets": len(todo),
        "dry_run": args.dry_run,
        "submitted": [],
        "errors": [],
    }

    if args.dry_run:
        print(json.dumps({"targets": todo[:10], "total": len(todo)}, indent=2))
        return 0

    stack = create_stack()
    for i, item in enumerate(todo, start=1):
        plan = build_generic_scrape_plan(
            item["url"],
            mode="token",
            title=f"Etherscan token backfill {item['slug']} ({item['address'][:10]}…)",
            agent_initiated=True,
        )
        plan["pool"] = args.pool
        plan["keep_local_staging"] = True
        plan["partition_id"] = "markets.crypto-coingecko"
        plan["metadata"] = {"skynet_slug": item["slug"], "ethereum_address": item["address"]}
        try:
            submitted = stack.tools.yzu_submit_job(
                json.dumps(plan),
                title=plan["title"],
                auto_approve=not args.no_auto_approve,
            )
            job = submitted.get("job") if isinstance(submitted, dict) else {}
            job_id = job.get("id") if isinstance(job, dict) else str(submitted)
            report["submitted"].append({"slug": item["slug"], "address": item["address"], "job_id": job_id})
            print(f"[{i}/{len(todo)}] submitted {item['slug']} -> {job_id}")
        except Exception as exc:  # noqa: BLE001 — batch submit should continue
            report["errors"].append({"slug": item["slug"], "error": str(exc)})
            print(f"[{i}/{len(todo)}] FAILED {item['slug']}: {exc}")
        if i < len(todo) and args.sleep_secs > 0:
            time.sleep(args.sleep_secs)

    out = REPO / "data/exports/etherscan_skynet_backfill_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {out}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
