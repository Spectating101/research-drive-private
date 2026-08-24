#!/usr/bin/env python3
"""
Fetch SEC EDGAR company submissions JSON for a list of tickers.

Endpoint:
  https://data.sec.gov/submissions/CIK##########.json

This produces OFFLINE cached JSON files for later event extraction.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests


def _parse_tickers_file(path: Path) -> List[str]:
    tickers: List[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tickers.append(line.split()[0].strip().upper())
    return sorted(dict.fromkeys([t for t in tickers if t]))


def _load_mapping(path: Path) -> Dict[str, str]:
    obj = json.loads(path.read_text())
    mapping: Dict[str, str] = {}
    # file is dict of numeric keys -> {ticker, cik_str, title}
    for _, rec in (obj or {}).items():
        t = str(rec.get("ticker", "")).upper().strip()
        cik = rec.get("cik_str")
        if not t or cik is None:
            continue
        mapping[t] = str(int(cik)).zfill(10)
    return mapping


def _should_refresh(path: Path, *, refresh_existing: bool, stale_days: int) -> bool:
    if not path.exists():
        return True
    if bool(refresh_existing):
        return True
    if int(stale_days) <= 0:
        return False
    age_seconds = max(0.0, datetime.now(timezone.utc).timestamp() - float(path.stat().st_mtime))
    return age_seconds >= float(int(stale_days) * 86400)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch SEC submissions for tickers.")
    ap.add_argument("--tickers-file", type=Path, required=True)
    ap.add_argument("--mapping", type=Path, default=Path("data_lake/sec/company_tickers.json"))
    ap.add_argument("--out-dir", type=Path, default=Path("data_lake/sec/submissions"))
    ap.add_argument("--max-tickers", type=int, default=0, help="Cap tickers (0=all).")
    ap.add_argument("--sleep-secs", type=float, default=0.25, help="Sleep between requests.")
    ap.add_argument("--refresh-existing", action="store_true", help="Re-fetch even when a cached submission file already exists.")
    ap.add_argument(
        "--stale-days",
        type=int,
        default=0,
        help="If >0, re-fetch cached files older than this many days.",
    )
    ap.add_argument(
        "--user-agent",
        default="SharpeRenaissanceResearchBot/0.1 (research; contact: local)",
        help="SEC requires a descriptive User-Agent.",
    )
    args = ap.parse_args()

    if not args.mapping.exists():
        print(f"Missing mapping file: {args.mapping} (run sec_fetch_company_tickers.py)")
        return 2

    tickers = _parse_tickers_file(args.tickers_file)
    if int(args.max_tickers) > 0:
        tickers = tickers[: int(args.max_tickers)]
    if not tickers:
        print("No tickers provided.")
        return 2

    mapping = _load_mapping(args.mapping)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    missing = 0
    failed = 0
    for t in tickers:
        cik = mapping.get(t)
        if not cik:
            missing += 1
            continue
        out = args.out_dir / f"{t}.json"
        if not _should_refresh(out, refresh_existing=bool(args.refresh_existing), stale_days=int(args.stale_days)):
            ok += 1
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            r = requests.get(url, headers={"User-Agent": str(args.user_agent)}, timeout=60)
            if r.status_code != 200:
                failed += 1
                continue
            out.write_text(json.dumps(r.json(), indent=2) + "\n")
            ok += 1
        except Exception:
            failed += 1
        time.sleep(float(max(0.0, args.sleep_secs)))

    print(json.dumps({"saved_or_cached": ok, "missing_cik": missing, "failed": failed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
