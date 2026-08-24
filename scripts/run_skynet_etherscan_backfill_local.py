#!/usr/bin/env python3
"""Run Skynet Etherscan token backfill locally via xvfb + Chrome (no queue)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DISPATCH = REPO / "scripts/yzu_cluster/workers/scraper_dispatch.sh"
DEFAULT_REPORT = REPO / "data/exports/etherscan_skynet_backfill_report.json"
SCRAPES = REPO / "data_lake/spectator_engine/scrapes"


def load_targets(report: Path) -> list[dict[str, str]]:
    if report.is_file():
        data = json.loads(report.read_text(encoding="utf-8"))
        rows = data.get("submitted") or []
        if rows:
            return [{"slug": r["slug"], "address": r["address"]} for r in rows if r.get("slug") and r.get("address")]
    from stablecoin_skynet.unified_dataset import DEFAULT_SCRAPES_ROOT, DEFAULT_SKYNET_HARVEST, build_unified_dataset, load_etherscan_index

    indexed = set(load_etherscan_index(DEFAULT_SCRAPES_ROOT))
    unified, _ = build_unified_dataset(skynet_harvest_dir=DEFAULT_SKYNET_HARVEST, scrapes_root=DEFAULT_SCRAPES_ROOT)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in unified:
        if not row.get("in_skynet_leaderboard") or row.get("in_etherscan_stablecoin_list"):
            continue
        addr = str(row.get("primary_ethereum_address") or "").lower()
        if not addr or addr in indexed or addr in seen:
            continue
        seen.add(addr)
        out.append({"slug": row["skynet_slug"], "address": addr})
    return out


def already_harvested(out_dir: Path, address: str) -> bool:
    token_json = out_dir / "tokens" / f"{address.lower()}.json"
    if not token_json.is_file():
        return False
    try:
        data = json.loads(token_json.read_text(encoding="utf-8"))
        detail = data.get("detail") or {}
        return not detail.get("blocked") and (detail.get("page_text_len") or 0) > 400
    except json.JSONDecodeError:
        return False


def scrape_one(slug: str, address: str, *, pause_secs: float) -> dict:
    out_dir = SCRAPES / f"backfill_{slug}"
    if already_harvested(out_dir, address):
        return {"slug": slug, "address": address, "status": "skipped", "out": str(out_dir)}

    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("PLAYWRIGHT_CHANNEL", "chrome")
    env.setdefault("PLAYWRIGHT_HEADLESS", "false")
    env["SPECTATOR_STAGING"] = str(REPO / "data_lake/spectator_engine")

    cmd = [
        "bash",
        str(DISPATCH),
        "yzu_cluster/scrapers/generic_url_scrape.mjs",
        "--",
        "--url",
        f"https://etherscan.io/token/{address}",
        "--mode",
        "token",
        "--out",
        str(out_dir),
    ]
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=180)
    ok = proc.returncode == 0
    if pause_secs > 0:
        import time

        time.sleep(pause_secs)
    return {
        "slug": slug,
        "address": address,
        "status": "ok" if ok else "error",
        "out": str(out_dir),
        "stdout": (proc.stdout or "")[-500:],
        "stderr": (proc.stderr or "")[-500:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-local", action="store_true", help="Allow running scrapes on this machine (not recommended)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--pause-secs", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.force_local:
        print(
            "Local Etherscan backfill is disabled — use the cluster queue instead:\n"
            "  PYTHONPATH=. .venv/bin/python scripts/submit_skynet_etherscan_backfill.py --limit 5\n"
            "Jobs run on windows_lab via SSH; this machine only orchestrates.\n"
            "Pass --force-local to run xvfb+Chrome here anyway.",
            file=sys.stderr,
        )
        return 2

    targets = load_targets(args.report)
    if args.limit > 0:
        targets = targets[: args.limit]

    print(f"targets={len(targets)} (xvfb-run + Chrome via scraper_dispatch)", flush=True)
    if args.dry_run:
        print(json.dumps(targets[:10], indent=2))
        return 0

    results: list[dict] = []
    for i, item in enumerate(targets, start=1):
        print(f"[{i}/{len(targets)}] {item['slug']} {item['address']}", flush=True)
        try:
            results.append(scrape_one(item["slug"], item["address"], pause_secs=args.pause_secs))
        except subprocess.TimeoutExpired:
            results.append({"slug": item["slug"], "address": item["address"], "status": "timeout"})

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": "local_xvfb_chrome",
        "targets": len(targets),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "skipped": sum(1 for r in results if r.get("status") == "skipped"),
        "errors": [r for r in results if r.get("status") not in {"ok", "skipped"}],
        "results": results,
    }
    out = REPO / "data/exports/etherscan_skynet_backfill_local_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("targets", "ok", "skipped", "errors")}, indent=2))
    print(f"wrote {out}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
