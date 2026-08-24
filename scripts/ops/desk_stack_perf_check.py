#!/usr/bin/env python3
"""Benchmark desk stack paths vs Composer chat — isolates our bugs from agent latency."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _get(base: str, path: str, *, timeout: float) -> tuple[float, int, int]:
    url = f"{base.rstrip('/')}{path}"
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read()
    elapsed = time.perf_counter() - t0
    return elapsed, resp.status, len(body)


def _post_json(base: str, path: str, payload: dict[str, Any], *, timeout: float) -> tuple[float, int, int]:
    url = f"{base.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    elapsed = time.perf_counter() - t0
    return elapsed, resp.status, len(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Desk stack vs Composer latency check")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="Query engine base URL")
    parser.add_argument("--timeout", type=float, default=45.0, help="Per-request timeout (s)")
    parser.add_argument("--chat", action="store_true", help="Include slow /library/chat probe (Composer)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        _get(base, "/library/discover?q=warm&limit=1", timeout=min(args.timeout, 20.0))
    except Exception:
        pass

    rows: list[dict[str, Any]] = []

    def record(name: str, elapsed: float, status: int, nbytes: int, *, note: str = "") -> None:
        rows.append(
            {
                "name": name,
                "seconds": round(elapsed, 3),
                "status": status,
                "bytes": nbytes,
                "note": note,
            }
        )

    probes = [
        ("health", f"/health"),
        ("discover", f"/library/discover?q=mops&limit=6"),
        ("search", f"/library/search?q=mops&limit=6"),
        (
            "search_skip_discover",
            f"/library/search?q=mops&limit=6&skip_discover=1&email=demo@yzu.edu.tw",
        ),
        ("probe_sec_compact", None),
    ]

    for name, path in probes:
        try:
            if name == "probe_sec_compact":
                elapsed, status, nbytes = _post_json(
                    base,
                    "/library/discover/probe",
                    {"url": "https://www.sec.gov/files/company_tickers.json"},
                    timeout=args.timeout,
                )
            else:
                elapsed, status, nbytes = _get(base, path, timeout=args.timeout)
            record(name, elapsed, status, nbytes)
        except urllib.error.HTTPError as exc:
            record(name, 0.0, exc.code, 0, note=str(exc))
        except Exception as exc:  # noqa: BLE001
            record(name, 0.0, 0, 0, note=str(exc))

    if args.chat:
        try:
            elapsed, status, nbytes = _post_json(
                base,
                "/library/chat",
                {"message": "Probe https://example.com and summarize access mode in one sentence."},
                timeout=args.timeout,
            )
            record("chat_probe_composer", elapsed, status, nbytes, note="expect slow if Composer-bound")
        except Exception as exc:  # noqa: BLE001
            record("chat_probe_composer", 0.0, 0, 0, note=str(exc))

    stack = [r for r in rows if r["name"] != "chat_probe_composer"]
    slow_stack = [r for r in stack if r["seconds"] > 12.0 and not r.get("note")]
    verdict = "stack_ok"
    if slow_stack:
        verdict = "stack_slow"
    chat_row = next((r for r in rows if r["name"] == "chat_probe_composer"), None)
    if chat_row and chat_row["seconds"] > 15 and not chat_row.get("note"):
        verdict = "composer_slow" if not slow_stack else "stack_and_composer_slow"

    out = {"base": base, "verdict": verdict, "rows": rows}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"base={base} verdict={verdict}")
        for r in rows:
            note = f" ({r['note']})" if r.get("note") else ""
            print(f"  {r['name']:22s} {r['seconds']:6.3f}s  {r['bytes']:8d} B{note}")
    return 0 if verdict == "stack_ok" or verdict == "composer_slow" else 1


if __name__ == "__main__":
    sys.exit(main())
