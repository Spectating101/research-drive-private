#!/usr/bin/env python3
"""
Fetch SEC ticker->CIK mapping (public file) for event-study pipelines.

Source:
  https://www.sec.gov/files/company_tickers.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch SEC company_tickers.json")
    ap.add_argument("--out", type=Path, default=Path("data_lake/sec/company_tickers.json"))
    ap.add_argument(
        "--user-agent",
        default="SharpeRenaissanceResearchBot/0.1 (research; contact: local)",
        help="SEC requires a descriptive User-Agent.",
    )
    args = ap.parse_args()

    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers={"User-Agent": str(args.user_agent)}, timeout=60)
    r.raise_for_status()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(r.json(), indent=2) + "\n")
    print(json.dumps({"out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

