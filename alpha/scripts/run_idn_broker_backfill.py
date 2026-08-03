#!/usr/bin/env python3
"""Backfill RapidAPI broker-summary for all IDX spike sessions (cached).

Uses free-tier budget with paced requests. Skips existing cache files.

Examples:
  python scripts/run_idn_broker_backfill.py
  python scripts/run_idn_broker_backfill.py --max-calls 200 --delay 3.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_bandar_collector import CACHE_DIR, _cache_path, fetch_broker_summary_rapidapi  # noqa: E402
from run_idn_spike_pattern_mining import MIN_PCT, START, classify_spike_row  # noqa: E402
from run_idn_spike_pattern_mining import fetch_history, load_universe  # noqa: E402

MANIFEST = REPO / "data_lake/markets/idx_broker_summary/backfill_manifest.json"
FRY_QUEUE = REPO / "data_lake/research_panels/idn_fry_episode/fry_trigger_broker_queue.json"
FREE_TIER_MONTHLY = 500


def fry_trigger_sessions() -> list[tuple[str, str]]:
    if not FRY_QUEUE.exists():
        return []
    rows = json.loads(FRY_QUEUE.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        sym = row.get("yahoo_symbol", "")
        date = row.get("date", "")
        if not sym or not date:
            continue
        key = (sym, date)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return sorted(out, key=lambda x: (x[1], x[0]))


def spike_sessions() -> list[tuple[str, str]]:
    universe = load_universe()
    px, vol_px = fetch_history(universe, START, datetime.now(UTC).strftime("%Y-%m-%d"))
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for sym in universe:
        if sym not in px.columns:
            continue
        for dt, r in px[sym].pct_change().dropna().items():
            if r * 100 < MIN_PCT:
                continue
            row = classify_spike_row(sym, __import__("pandas").Timestamp(dt), float(r), px, vol_px)
            key = (sym, row["date"])
            if key not in seen:
                seen.add(key)
                out.append(key)
    return sorted(out, key=lambda x: x[1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-calls", type=int, default=FREE_TIER_MONTHLY - 30, help="Cap live API calls this run")
    ap.add_argument("--delay", type=float, default=3.5, help="Seconds between live API calls")
    ap.add_argument("--cooldown-on-403", type=float, default=45.0, help="Pause after Cloudflare 403")
    ap.add_argument(
        "--source",
        choices=("spike", "fry", "both"),
        default="spike",
        help="Session list: liquid spike days, fry trigger queue, or union",
    )
    args = ap.parse_args()

    if args.source == "fry":
        sessions = fry_trigger_sessions()
    elif args.source == "both":
        seen: set[tuple[str, str]] = set()
        sessions = []
        for pair in spike_sessions() + fry_trigger_sessions():
            if pair not in seen:
                seen.add(pair)
                sessions.append(pair)
        sessions.sort(key=lambda x: x[1])
    else:
        sessions = spike_sessions()
    pending = [(s, d) for s, d in sessions if not _cache_path(s, d).exists()]

    print(f"Spike sessions: {len(sessions)} | cached: {len(sessions) - len(pending)} | pending: {len(pending)}")
    print(f"Will fetch up to {min(len(pending), args.max_calls)} live calls @ {args.delay}s pacing")

    ok = fail = skipped = 0
    errors: list[dict] = []
    t0 = time.time()

    for i, (sym, date) in enumerate(pending):
        if ok + fail >= args.max_calls:
            print(f"Hit --max-calls={args.max_calls}")
            break
        if i > 0:
            time.sleep(args.delay)

        result = fetch_broker_summary_rapidapi(sym, date, use_cache=True)
        success = result.get("available") and (result.get("data") or {}).get("success")
        if success:
            ok += 1
            if ok % 10 == 0:
                print(f"  [{ok+fail}/{min(len(pending), args.max_calls)}] OK {date} {sym}")
        else:
            reason = result.get("reason", "unknown")
            fail += 1
            errors.append({"symbol": sym, "date": date, "reason": reason, "body": result.get("body", "")[:200]})
            print(f"  FAIL {date} {sym} {reason}")
            if reason == "http_403":
                print(f"  Cloudflare cooldown {args.cooldown_on_403}s...")
                time.sleep(args.cooldown_on_403)
                # retry once
                result2 = fetch_broker_summary_rapidapi(sym, date, use_cache=False)
                if result2.get("available") and (result2.get("data") or {}).get("success"):
                    ok += 1
                    fail -= 1
                    errors.pop()
                    print(f"  RETRY OK {date} {sym}")

    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": args.source,
        "sessions_total": len(sessions),
        "pending_at_start": len(pending),
        "live_ok": ok,
        "live_fail": fail,
        "max_calls": args.max_calls,
        "delay_sec": args.delay,
        "elapsed_sec": round(time.time() - t0, 1),
        "cache_files": len(list(CACHE_DIR.glob("*.json"))),
        "errors_sample": errors[:20],
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone: ok={ok} fail={fail} cache_total={manifest['cache_files']} elapsed={manifest['elapsed_sec']}s")
    print(f"Wrote {MANIFEST}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
