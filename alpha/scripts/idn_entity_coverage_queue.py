#!/usr/bin/env python3
"""Build queue of missing GDELT entity overlay months for IDX coverage fleet."""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import time_cutoff  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_entity_coverage"
OVERLAY_ROOT = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_ticker_overlay"
PROCESSED_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
BROADCAST_PANEL = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
WINDOW_RE = re.compile(r"asia_gkg_window_(\d{8})_(\d{8})")


def processed_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for panel in PROCESSED_ROOT.glob("*/daily_country_shock_panel.csv"):
        match = WINDOW_RE.match(panel.parent.name)
        if match:
            keys.add((match.group(1), match.group(2)))
    return keys


def overlay_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    manifest = OVERLAY_ROOT / "manifest.json"
    if manifest.exists():
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            if item.get("status") == "complete":
                match = WINDOW_RE.match(str(item.get("window", "")))
                if match:
                    keys.add((match.group(1), match.group(2)))
    return keys


def cluster_joined_hosts() -> list[str]:
    inv = Path("/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv")
    hosts: list[str] = []
    if not inv.exists():
        return hosts
    for line in inv.read_text(encoding="utf-8").splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4 and parts[3] == "joined":
            hosts.append(parts[0])
    return hosts


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = sorted(processed_keys() - overlay_keys())
    priority = sorted(missing, key=lambda k: k[0], reverse=True)

    holdout_cut_s = "20240101"
    if BROADCAST_PANEL.exists():
        b = pd.read_parquet(BROADCAST_PANEL, columns=["week_end"])
        b["week_end"] = pd.to_datetime(b["week_end"])
        holdout_cut_s = time_cutoff(b["week_end"]).strftime("%Y%m%d")
    missing_holdout = [k for k in missing if k[1] >= holdout_cut_s]

    queue = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "missing_total": len(missing),
        "holdout_cutoff": holdout_cut_s,
        "missing_holdout": len(missing_holdout),
        "priority_window_keys": [f"{a}_{b}" for a, b in priority],
        "cluster_joined_hosts": cluster_joined_hosts(),
        "worker_note": (
            "Entity overlay workers run on Linux (optiplex). Windows cluster nodes are probed for "
            "availability; GDELT entity scans require Python+rclone on Linux paths."
        ),
    }
    path = OUT / "overlay_queue.json"
    path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: queue[k] for k in ("missing_total", "missing_holdout", "holdout_cutoff", "cluster_joined_hosts")}, indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
