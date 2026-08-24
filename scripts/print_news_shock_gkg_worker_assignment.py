#!/usr/bin/env python3
"""Print modulo month assignments for GDELT GKG workers."""

from __future__ import annotations

import argparse
from datetime import date


def parse_date(value: str) -> date:
    year, month, day = map(int, value.split("-"))
    return date(year, month, day)


def add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def month_windows(start: date, end: date) -> list[tuple[int, date, date]]:
    out: list[tuple[int, date, date]] = []
    cursor = date(start.year, start.month, 1)
    idx = 0
    while cursor < end:
        nxt = min(add_month(cursor), end)
        out.append((idx, cursor, nxt))
        cursor = nxt
        idx += 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2024-01-01")
    parser.add_argument(
        "--workers",
        default="optiplex,DESKTOP-VEFGGDH,DESKTOP-FGEDHGV,DESKTOP-EDHFGGV",
        help="Comma-separated worker names in modulo order.",
    )
    args = parser.parse_args()

    workers = [item.strip() for item in args.workers.split(",") if item.strip()]
    if not workers:
        raise SystemExit("at least one worker is required")

    assignments: dict[str, list[str]] = {worker: [] for worker in workers}
    for idx, start, end in month_windows(parse_date(args.start), parse_date(args.end)):
        worker = workers[idx % len(workers)]
        assignments[worker].append(f"{start.isoformat()}..{end.isoformat()}")

    for worker in workers:
        months = assignments[worker]
        print(f"{worker}: {len(months)} months")
        for month in months:
            print(f"  {month}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
