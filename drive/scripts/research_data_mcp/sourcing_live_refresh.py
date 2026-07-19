#!/usr/bin/env python3
"""Refresh live scrape exemplars + flywheel index (Zenodo search + Taiwan gov data)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.sourcing_chain import follow_plans_from_extract, harvest_links_from_extract

DEFAULT_TARGETS = [
    {
        "job_id": "live-test",
        "url": "https://zenodo.org/search?q=taiwan+election",
        "mode": "page",
        "search_goal": "taiwan election microdata",
    },
    {
        "job_id": "live-test-govtw",
        "url": "https://data.gov.tw/dataset?q=%E9%81%B8%E8%88%89",
        "mode": "page",
        "search_goal": "taiwan government open data election",
    },
]


def run_scrape(repo: Path, *, url: str, mode: str, job_id: str, timeout_ms: int) -> Path:
    out = repo / f"data_lake/spectator_engine/scrapes/{job_id}/extract.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = repo / "data_lake/spectator_engine"
    script = repo / "scripts/yzu_cluster/scrapers/generic_url_scrape.mjs"
    env = {
        **os.environ,
        "SPECTATOR_STAGING": str(staging),
        "PLAYWRIGHT_TIMEOUT_MS": str(timeout_ms),
    }
    proc = subprocess.run(
        [
            "node",
            str(script),
            "--url",
            url,
            "--mode",
            mode,
            "--out",
            str(out),
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=max(180, timeout_ms // 1000 + 90),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"scrape failed for {url}")
    line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    try:
        meta = json.loads(line)
    except json.JSONDecodeError:
        meta = {"out": str(out)}
    if not out.is_file():
        raise RuntimeError(f"extract missing after scrape: {out}")
    return out


def promote(repo: Path, *, job_id: str, url: str, search_goal: str) -> dict:
    from scripts.research_data_mcp.scrape_flywheel import promote_scrape_job

    job = {
        "id": job_id,
        "status": "completed",
        "plan": {"job_type": "scraper_run", "url": url, "script_key": "generic_url_scrape"},
    }
    return promote_scrape_job(repo, job, search_goal=search_goal)


def refresh_target(repo: Path, target: dict[str, str], *, timeout_ms: int, dry_run: bool) -> dict:
    job_id = target["job_id"]
    url = target["url"]
    mode = target.get("mode") or "page"
    goal = target.get("search_goal") or ""
    if dry_run:
        return {"job_id": job_id, "url": url, "dry_run": True}
    out = run_scrape(repo, url=url, mode=mode, job_id=job_id, timeout_ms=timeout_ms)
    extract = json.loads(out.read_text(encoding="utf-8"))
    links = harvest_links_from_extract(extract, limit=8)
    plans = follow_plans_from_extract(extract, goal=goal, limit=3)
    promo = promote(repo, job_id=job_id, url=url, search_goal=goal)
    return {
        "job_id": job_id,
        "url": url,
        "extract": str(out.relative_to(repo)),
        "link_count": len(extract.get("links") or []),
        "dataset_link_count": len(extract.get("dataset_links") or []),
        "harvest_kinds": [row.get("kind") for row in links[:6]],
        "follow_plans": plans,
        "promote": promo,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh live sourcing scrape exemplars")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    results = [
        refresh_target(repo, target, timeout_ms=args.timeout_ms, dry_run=args.dry_run)
        for target in DEFAULT_TARGETS
    ]
    if args.json:
        print(json.dumps({"targets": results}, indent=2, ensure_ascii=False))
    else:
        print("=== Live sourcing refresh ===\n")
        for row in results:
            if row.get("dry_run"):
                print(f"[dry-run] {row['job_id']}: {row['url']}")
                continue
            print(
                f"{row['job_id']}: {row.get('link_count', 0)} links, "
                f"{row.get('dataset_link_count', 0)} dataset links"
            )
            print(f"  harvest: {row.get('harvest_kinds')}")
            print(f"  follow: {row.get('follow_plans')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
