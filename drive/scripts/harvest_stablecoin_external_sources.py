#!/usr/bin/env python3
"""Harvest free external stablecoin sources into stablecoin_skynet/data/derived/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stablecoin_skynet.defillama_panel import (
    DEFAULT_CACHE_DIR as DEFILLAMA_CACHE,
    DEFAULT_MAP_CONFIG,
    build_defillama_panels,
    build_entity_defillama_map,
    fetch_stablecoin_list,
    fetch_stablecoin_prices,
)
from stablecoin_skynet.incidents_panel import DEFAULT_CURATED, build_incidents
from stablecoin_skynet.research_dataset import build_entities
from stablecoin_skynet.unified_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
)
from stablecoin_skynet.wikipedia_panel import DEFAULT_CONFIG as WIKI_CONFIG, build_pageviews_daily

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skynet-harvest", type=Path, default=DEFAULT_SKYNET_HARVEST)
    parser.add_argument("--scrapes-root", type=Path, default=DEFAULT_SCRAPES_ROOT)
    parser.add_argument("--community-dir", type=Path, default=DEFAULT_COMMUNITY_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFILLAMA_CACHE)
    parser.add_argument("--refresh", action="store_true", help="Re-download all external APIs")
    parser.add_argument("--defillama-only", action="store_true")
    parser.add_argument("--wikipedia-only", action="store_true")
    parser.add_argument("--incidents-only", action="store_true")
    args = parser.parse_args()

    unified_rows, _ = build_unified_dataset(
        skynet_harvest_dir=args.skynet_harvest,
        scrapes_root=args.scrapes_root,
        community_dir=args.community_dir,
    )
    entities = build_entities(unified_rows)
    leaderboard = [e for e in entities if e.get("in_skynet_leaderboard")]
    entity_ids = {e["entity_id"] for e in leaderboard if e.get("entity_id")}

    summary: dict[str, object] = {}

    if not args.wikipedia_only and not args.incidents_only:
        fetch_stablecoin_list(cache_dir=args.cache_dir, refresh=args.refresh)
        fetch_stablecoin_prices(cache_dir=args.cache_dir, refresh=args.refresh)
        panels = build_defillama_panels(
            leaderboard,
            cache_dir=args.cache_dir,
            map_config=DEFAULT_MAP_CONFIG,
            refresh=args.refresh,
            entity_ids=entity_ids,
        )
        entity_map = panels["entity_map"]
        map_path = args.cache_dir / "entity_map.json"
        map_path.write_text(json.dumps(entity_map, indent=2), encoding="utf-8")
        summary["defillama"] = {
            "mapped_entities": len(entity_map),
            "supply_daily_rows": len(panels["supply_daily"]),
            "peg_daily_rows": len(panels["peg_daily"]),
            "entity_map_path": str(map_path),
        }

    if not args.defillama_only and not args.incidents_only:
        daily = build_pageviews_daily(
            leaderboard,
            config_path=WIKI_CONFIG,
            refresh=args.refresh,
            entity_ids=entity_ids,
        )
        summary["wikipedia"] = {"daily_rows": len(daily)}

    if not args.defillama_only and not args.wikipedia_only:
        incidents = build_incidents(
            leaderboard,
            skynet_harvest_dir=args.skynet_harvest,
            curated_path=DEFAULT_CURATED,
            entity_ids=entity_ids,
        )
        summary["incidents"] = {"rows": len(incidents)}

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
