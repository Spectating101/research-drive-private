#!/usr/bin/env python3
"""Submit a full Etherscan stablecoin catalog sweep to the cluster queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.scrape_plan import build_generic_scrape_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=64)
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument("--auto-approve", action="store_true", default=True)
    args = parser.parse_args()

    stack = create_stack()
    url = "https://etherscan.io/tokens?l=Stablecoin"
    plan = build_generic_scrape_plan(
        url,
        mode="catalog",
        title=f"Etherscan stablecoin catalog sweep p{args.max_pages}",
        catalog_max_pages=args.max_pages,
        catalog_max_tokens=args.max_tokens,
        catalog_pause_ms=1500,
        agent_initiated=True,
    )
    plan["partition_id"] = "markets.crypto-coingecko"
    submitted = stack.tools.yzu_submit_job(
        json.dumps(plan),
        title=plan["title"],
        auto_approve=args.auto_approve,
    )
    print(json.dumps(submitted, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
