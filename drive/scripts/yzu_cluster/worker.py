#!/usr/bin/env python3
"""Background worker for YZU Cluster job queue + Discover refresh cadence."""

from __future__ import annotations

import argparse
import signal
import threading
import time

from scripts.research_data_mcp.bootstrap import create_stack


def main() -> int:
    parser = argparse.ArgumentParser(description="YZU Cluster job worker")
    parser.add_argument("--poll", type=float, default=2.0, help="seconds between queue polls")
    parser.add_argument("--once", action="store_true", help="process at most one queued job then exit")
    args = parser.parse_args()

    stack = create_stack()
    stop = False

    def _handle(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    print(
        f"yzu_worker db={stack.jobs.orchestrator.store.path} poll={args.poll}s schedules={len(stack.jobs.orchestrator.schedules())}",
        flush=True,
    )

    def _cadence_loop() -> None:
        """Fire due Discover refresh subscriptions even while a job is executing."""
        while not stop:
            try:
                tick_out = stack.gateway.discover_refresh_tick(limit=5, auto_approve_safe=True)
                fired = tick_out.get("fired") or []
                if fired:
                    print(
                        f"discover_refresh fired={len(fired)} "
                        f"ids={[f.get('subscription_id', '')[:8] for f in fired]}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"discover_refresh tick error: {exc}", flush=True)
            # Sleep in 0.5s slices so SIGTERM stops promptly
            deadline = time.time() + max(float(args.poll), 1.0)
            while not stop and time.time() < deadline:
                time.sleep(0.5)

    cadence_thread = threading.Thread(target=_cadence_loop, name="discover-refresh-cadence", daemon=True)
    cadence_thread.start()

    while not stop:
        job = stack.jobs.tick()
        if isinstance(job, dict) and job.get("id"):
            print(f"job {job['id']} -> {job.get('status', 'scheduled')}", flush=True)
        if args.once:
            stop = True
            break
        time.sleep(args.poll)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
