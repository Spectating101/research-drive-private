#!/usr/bin/env python3
"""SSH/SCP helpers for YZU worker pools."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any


def datacite_shard_probe_argv(shard: str) -> list[str]:
    """Remote argv tail for SSH: powershell -File datacite_lane_probe.ps1."""
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:/Users/user/datacite_lane_probe.ps1",
        "-ShardName",
        shard,
    ]


def parse_datacite_lane_probe(line: str) -> dict[str, Any]:
    """Parse datacite_lane_probe.ps1 pipe output."""
    parts = [p.strip() for p in line.strip().split("|")]
    if len(parts) < 8:
        return {}
    shard, status, is_complete, committed, _pid, _task, activity, heartbeat = parts[:8]
    return {
        "shard": shard,
        "status": status,
        "complete": is_complete == "1",
        "committed": int(committed or 0),
        "activity_utc": activity or heartbeat,
    }


def ssh_run(
    target: str,
    command: str,
    *,
    key: str,
    timeout: int = 60,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    args = [
        "ssh",
        "-n",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        target,
        command,
    ]
    return subprocess.run(
        args,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def scp_pull(target: str, remote: str, local: Path, *, key: str, timeout: int = 300) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["scp", "-q", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", f"{target}:{remote}", str(local)],
        check=True,
        timeout=timeout,
    )


def scp_pull_recursive(target: str, remote_dir: str, local_dir: Path, *, key: str, timeout: int = 600) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    remote = remote_dir.replace("\\", "/")
    if not remote.endswith("/"):
        remote = f"{remote}/"
    subprocess.run(
        [
            "scp",
            "-r",
            "-q",
            "-i",
            key,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            f"{target}:{remote}*",
            str(local_dir),
        ],
        check=True,
        timeout=timeout,
    )


def scp_push(local: Path, target: str, remote: str, *, key: str, timeout: int = 120) -> None:
    subprocess.run(
        ["scp", "-q", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(local), f"{target}:{remote}"],
        check=True,
        timeout=timeout,
    )


def windows_workers(inventory: str | Path, *, joined_only: bool = True) -> list[dict[str, Any]]:
    path = Path(inventory)
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if joined_only:
        rows = [row for row in rows if row.get("status") == "joined"]
    return rows


def windows_target(worker: dict[str, Any], *, default_user: str = "user") -> str:
    user = worker.get("user") or default_user
    return f"{user}@{worker['tailscale_ip']}"


def spectator_targets(pool: dict[str, Any]) -> list[str]:
    hosts: list[str] = []
    user = pool.get("user", "spectator")
    for value in (pool.get("host"), pool.get("tailscale_ip"), f"{user}@{pool.get('tailscale_ip')}"):
        if not value:
            continue
        if "@" in str(value):
            hosts.append(str(value))
        elif str(value).replace(".", "").isdigit() or value == pool.get("tailscale_ip"):
            hosts.append(f"{user}@{value}")
        else:
            hosts.append(str(value))
    seen: set[str] = set()
    out: list[str] = []
    for host in hosts:
        if host not in seen:
            seen.add(host)
            out.append(host)
    return out


def parse_datacite_shard(shards_file: Path, shard: str) -> dict[str, str]:
    if not shards_file.exists():
        raise ValueError(f"shards file missing: {shards_file}")
    for line in shards_file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, host, created, query, _target = line.split("|", 4)
        if name == shard:
            return {"shard": name, "host": host, "created": created, "query": query}
    raise ValueError(f"unknown datacite shard: {shard}")
