#!/usr/bin/env python3
"""Publish curated stablecoin trust ↔ engagement research dataset."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from stablecoin_skynet.gdelt_panel import DEFAULT_OVERLAY_ROOT
from stablecoin_skynet.research_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    publish_research_dataset,
)

def _repo_root() -> Path:
    """Sharpe-Renaissance root (parent of stablecoin_skynet/), not drive/ when invoked via symlink."""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, here.parent.parent):
        if (candidate / "stablecoin_skynet").is_dir():
            return candidate
    return here.parent


REPO = _repo_root()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: data/datasets/stablecoin_trust_engagement/YYYYMMDD)",
    )
    parser.add_argument("--skynet-harvest", type=Path, default=DEFAULT_SKYNET_HARVEST)
    parser.add_argument("--scrapes-root", type=Path, default=DEFAULT_SCRAPES_ROOT)
    parser.add_argument("--community-dir", type=Path, default=DEFAULT_COMMUNITY_DIR)
    parser.add_argument("--gdelt-overlay", type=Path, default=DEFAULT_OVERLAY_ROOT)
    parser.add_argument("--no-gdelt", action="store_true", help="Skip GDELT entity/sector panels")
    parser.add_argument("--no-external", action="store_true", help="Skip DeFiLlama/Wikipedia/incidents")
    parser.add_argument("--refresh-external", action="store_true", help="Re-download external APIs")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub activity proxy merge")
    parser.add_argument("--refresh-github", action="store_true", help="Re-fetch GitHub API (needs GITHUB_TOKEN)")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = args.out_dir or (REPO / "data" / "datasets" / "stablecoin_trust_engagement" / stamp)

    manifest = publish_research_dataset(
        out_dir,
        skynet_harvest_dir=args.skynet_harvest,
        scrapes_root=args.scrapes_root,
        community_dir=args.community_dir,
        gdelt_overlay_root=args.gdelt_overlay,
        include_gdelt=not args.no_gdelt,
        include_external=not args.no_external,
        refresh_external=args.refresh_external,
        include_github=not args.no_github,
        refresh_github=args.refresh_github,
    )

    latest_link = REPO / "data" / "datasets" / "stablecoin_trust_engagement" / "latest"
    if latest_link.is_symlink() or latest_link.exists():
        if latest_link.is_symlink() or latest_link.is_file():
            latest_link.unlink()
        elif latest_link.is_dir() and not latest_link.is_symlink():
            pass
    try:
        latest_link.symlink_to(out_dir.resolve(), target_is_directory=True)
    except OSError:
        pass

    print(json.dumps({"out_dir": str(out_dir), "counts": manifest.get("counts")}, indent=2))


if __name__ == "__main__":
    main()
