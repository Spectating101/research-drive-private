#!/usr/bin/env python3
"""Harvest GitHub public activity proxy for mapped stablecoin repos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stablecoin_skynet.github_activity_panel import (
    DEFAULT_CACHE_DIR,
    DEFAULT_CONFIG,
    WEEKLY_FIELDS,
    build_github_activity_weekly,
    build_repo_map,
    write_repo_map_csv,
)
from stablecoin_skynet.research_dataset import build_entities
from stablecoin_skynet.unified_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
)

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skynet-harvest", type=Path, default=DEFAULT_SKYNET_HARVEST)
    parser.add_argument("--scrapes-root", type=Path, default=DEFAULT_SCRAPES_ROOT)
    parser.add_argument("--community-dir", type=Path, default=DEFAULT_COMMUNITY_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--since", default="2021-01-01T00:00:00Z")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    unified_rows, _ = build_unified_dataset(
        skynet_harvest_dir=args.skynet_harvest,
        scrapes_root=args.scrapes_root,
        community_dir=args.community_dir,
    )
    entities = build_entities(unified_rows)
    repo_map = build_repo_map(entities, config_path=args.config, skynet_harvest_dir=args.skynet_harvest)

    weekly = build_github_activity_weekly(
        repo_map,
        since=args.since,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
    )

    out_dir = args.cache_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_repo_map_csv(out_dir / "github_repo_map.csv", repo_map)

    import csv

    weekly_path = out_dir / "github_security_activity_weekly.csv"
    with weekly_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WEEKLY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(weekly)

    print(
        json.dumps(
            {
                "mapped_repos": len(repo_map),
                "weekly_rows": len(weekly),
                "repo_map_path": str(out_dir / "github_repo_map.csv"),
                "weekly_path": str(weekly_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
