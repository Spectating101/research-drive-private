#!/usr/bin/env python3
"""Print a compact status report for the local data collection queue."""

from __future__ import annotations

import json
import os
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
STATUS_DIR = REPO / "data_lake/data_collection_queue"
LOG_DIR = REPO / "logs/data_collection_queue"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    lock = STATUS_DIR / "queue.lock"
    print(f"status_dir: {STATUS_DIR}")
    if lock.exists():
        try:
            obj = json.loads(lock.read_text())
            pid = int(obj.get("pid", 0))
            print(f"lock: pid={pid} alive={pid_alive(pid)} started_at={obj.get('started_at')}")
        except Exception as exc:
            print(f"lock: unreadable {type(exc).__name__}: {exc}")
    else:
        print("lock: none")

    latest = STATUS_DIR / "latest.json"
    if latest.exists():
        print("\nlatest:")
        print(latest.read_text().strip())

    status = STATUS_DIR / "status.jsonl"
    if status.exists():
        rows = status.read_text(errors="ignore").splitlines()
        print(f"\nstatus lines: {len(rows)}")
        print("last 12:")
        for line in rows[-12:]:
            print(line)

    if LOG_DIR.exists():
        print("\nlogs:")
        for path in sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)[-10:]:
            print(f"- {path.relative_to(REPO)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
