#!/usr/bin/env python3
"""CLI for YZU cluster live status."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.yzu_cluster.api import YzuClusterAPI
from sharpe_kernel.paths import repo_root_from_file


def main() -> int:
    root = repo_root_from_file(__file__)
    api = YzuClusterAPI(root)
    payload = api.status()
    if "--json" in sys.argv:
        print(json.dumps(payload, indent=2))
        return 0
    disk = payload["disk"]
    dc = payload["datacite"]
    print(f"YZU cluster @ {payload['controller']}  disk_free={disk.get('free_gb')}G used={disk.get('used_pct')}")
    print(f"Windows joined: {payload['worker_pools']['windows_lab']['joined']}/{payload['worker_pools']['windows_lab']['total']}")
    print(f"DataCite total: {dc['total_percent']}%  y2025: {dc['y2025_percent']}%")
    for row in dc["y2025_shards"]:
        eta = f" eta={row['eta_hours']}h" if row.get("eta_hours") else ""
        print(f"  {row['shard']} @{row['host']}: {row['progress']:,}/{row['target']:,} ({row['percent']}%){eta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
