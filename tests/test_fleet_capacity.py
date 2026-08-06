#!/usr/bin/env python3
"""Fleet capacity is measured, and a stale heartbeat is not online."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.fleet_capacity import (  # noqa: E402
    fleet_facts_line,
    measure_fleet,
    workers_for_capability,
)


def _db(tmp_path: Path, rows: list[tuple]) -> str:
    path = tmp_path / "jobs.sqlite3"
    con = sqlite3.connect(path)
    con.execute(
        "create table cluster_workers (worker_id text, pool text, status text,"
        " capabilities text, capacity text, heartbeat_at text)"
    )
    con.executemany("insert into cluster_workers values (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(path)


def _now(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)).isoformat()


def test_stale_heartbeat_is_not_counted_online(tmp_path: Path):
    path = _db(
        tmp_path,
        [
            ("optiplex", "optiplex", "online", json.dumps(["http", "python"]),
             json.dumps({"cpu_cores": 6.0, "disk_mb": 38596.0}), _now(10)),
            ("windows-02", "windows_lab", "online", json.dumps(["http", "python"]),
             json.dumps({"cpu_cores": 16.0, "disk_mb": 128628.0}), _now(660000)),
        ],
    )
    fleet = measure_fleet(path)
    assert fleet["online_count"] == 1
    assert fleet["total_cores"] == 6.0
    stale = [w for w in fleet["workers"] if w["worker_id"] == "windows-02"][0]
    assert stale["status"] == "online"
    assert stale["online"] is False


def test_http_capable_workers_are_named_for_parallel_collection(tmp_path: Path):
    path = _db(
        tmp_path,
        [
            ("optiplex", "optiplex", "online", json.dumps(["http", "browser"]),
             json.dumps({"cpu_cores": 6.0, "disk_mb": 38596.0}), _now(5)),
            ("windows-01", "windows_lab", "online", json.dumps(["http", "python"]),
             json.dumps({"cpu_cores": 16.0, "disk_mb": 120361.0}), _now(5)),
            ("windows-03", "windows_lab", "online", json.dumps(["http", "python"]),
             json.dumps({"cpu_cores": 16.0, "disk_mb": 315597.0}), _now(5)),
        ],
    )
    fleet = measure_fleet(path)
    assert fleet["online_count"] == 3
    assert fleet["total_cores"] == 38.0
    assert workers_for_capability(fleet, "http") == ["optiplex", "windows-01", "windows-03"]
    line = fleet_facts_line(fleet)
    assert "3 online" in line
    assert "38 cores" in line
    assert "concurrently" in line


def test_missing_db_degrades_to_single_node(tmp_path: Path):
    fleet = measure_fleet(str(tmp_path / "absent.sqlite3"))
    assert fleet["available"] is False
    assert "single-node" in fleet_facts_line(fleet)
