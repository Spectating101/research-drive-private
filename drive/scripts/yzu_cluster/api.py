#!/usr/bin/env python3
"""YZU Cluster API — live acquisitions, workers, and cluster status."""

from __future__ import annotations

import csv
import re
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research_query_engine import ops_status
from scripts.yzu_cluster.partition_lanes import partition_lanes


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _stage(progress: float, running: bool, complete: bool) -> str:
    if complete or progress >= 100:
        return "complete"
    if running and progress > 0:
        return "running"
    if running:
        return "starting"
    return "idle"


def _tone(stage: str) -> str:
    return {"complete": "green", "running": "blue", "starting": "amber", "setup": "red", "idle": "amber"}.get(stage, "blue")


def _runtime_worker_index(runtime: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map runtime worker_id -> worker payload from runtime_health()."""
    if not isinstance(runtime, dict):
        return {}
    cluster = runtime.get("cluster") if isinstance(runtime.get("cluster"), dict) else runtime
    workers = cluster.get("workers") if isinstance(cluster, dict) else None
    if not isinstance(workers, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        wid = str(worker.get("id") or worker.get("worker_id") or "").strip()
        if wid:
            out[wid] = worker
    return out


def _inventory_runtime_id(row: dict[str, Any]) -> str | None:
    """Best-effort map inventory notes/hostname to runtime worker_id (windows-01…)."""
    notes = str(row.get("notes") or "")
    match = re.search(r"\b(windows-\d+)\b", notes, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def _effective_worker_status(
    *,
    inventory_status: str,
    runtime_worker: dict[str, Any] | None,
    idle_grace_seconds: int = 86400,
) -> dict[str, Any]:
    """Honest desk status: joined inventory ≠ live heartbeat.

    Thin Windows workers often heartbeat only while executing jobs, so age > 300s
    is usually idle — not dead. Probe/diag leftovers stay stale.
    """
    inv = str(inventory_status or "").strip() or "unknown"
    if not runtime_worker:
        return {
            "inventory_status": inv,
            "effective_status": inv if inv != "joined" else "joined_unseen",
            "runtime_id": None,
            "freshness": None,
        }
    freshness = runtime_worker.get("freshness") if isinstance(runtime_worker.get("freshness"), dict) else {}
    age = freshness.get("age_seconds")
    state = str(freshness.get("state") or runtime_worker.get("status") or "unknown")
    wid = str(runtime_worker.get("id") or runtime_worker.get("worker_id") or "")
    effective = state
    if state == "stale" and isinstance(age, (int, float)) and age <= idle_grace_seconds:
        effective = "idle"
    elif state == "fresh" or str(runtime_worker.get("status") or "") == "online":
        effective = "online"
    return {
        "inventory_status": inv,
        "effective_status": effective,
        "runtime_id": wid or None,
        "freshness": freshness or {
            "state": state,
            "age_seconds": age,
        },
    }



class YzuClusterAPI:
    CACHE_TTL_SECONDS = 90

    def __init__(self, repo_root: Path, agent: Any | None = None, orchestrator: Any | None = None):
        self.repo_root = repo_root
        self.agent = agent
        self.orchestrator = orchestrator
        self.cfg = json.loads((repo_root / "config/yzu_cluster.json").read_text(encoding="utf-8"))
        self.key = Path(self.cfg["worker_pools"]["windows_lab"]["ssh_key"])
        self._cache_path = repo_root / "data_lake/yzu_cluster/shard_cache.json"

    def _read_shard_cache(self) -> tuple[list[dict[str, Any]], str, bool]:
        if not self._cache_path.exists():
            return [], "", False
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            return [], "", False
        age = time.time() - float(payload.get("ts_unix", 0))
        fresh = age <= self.CACHE_TTL_SECONDS
        return list(payload.get("shards") or []), str(payload.get("cached_at", "")), fresh

    def _write_shard_cache(self, shards: list[dict[str, Any]]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps({"ts_unix": time.time(), "cached_at": _now(), "shards": shards}, indent=2),
            encoding="utf-8",
        )

    def _merge_shard_rows(self, rows: list[dict[str, Any]], cached: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not cached:
            return rows
        by_shard = {s["shard"]: s for s in cached}
        merged: list[dict[str, Any]] = []
        for row in rows:
            if row.get("status") in {"unreachable", "cached_pending", "unknown"} and row["shard"] in by_shard:
                merged.append(by_shard[row["shard"]])
            else:
                merged.append(row)
        return merged

    def disk(self) -> dict[str, Any]:
        try:
            line = subprocess.check_output(["df", "-BG", str(self.repo_root)], text=True).splitlines()[-1].split()
            return {"free_gb": line[3].rstrip("G"), "used_pct": line[4], "total_gb": line[1].rstrip("G")}
        except Exception as exc:
            return {"error": str(exc)}

    def windows_workers(self) -> list[dict[str, Any]]:
        inv = Path(self.cfg["worker_pools"]["windows_lab"]["inventory"])
        if not inv.exists():
            return []
        with inv.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _ssh_probe_shard(self, host: str, shard: str, timeout: int = 20) -> tuple[bool, dict[str, Any]]:
        from scripts.yzu_cluster.pools import datacite_shard_probe_argv, parse_datacite_lane_probe

        try:
            out = subprocess.check_output(
                [
                    "ssh",
                    "-n",
                    "-i",
                    str(self.key),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    f"user@{host}",
                    *datacite_shard_probe_argv(shard),
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                stderr=subprocess.DEVNULL,
            )
            line = [x.strip() for x in out.splitlines() if x.strip()][-1]
            parsed = parse_datacite_lane_probe(line)
            return bool(parsed), parsed
        except Exception:
            return False, {}

    def _ssh_probe(self, host: str, ps: str, timeout: int = 20) -> tuple[bool, str]:
        try:
            out = subprocess.check_output(
                [
                    "ssh",
                    "-n",
                    "-i",
                    str(self.key),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    f"user@{host}",
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    ps,
                ],
                text=True,
                timeout=timeout,
                stderr=subprocess.DEVNULL,
            )
            return True, out.strip()
        except Exception as exc:
            return False, str(exc)[:240]

    def datacite_shards(self, live: bool = False) -> list[dict[str, Any]]:
        cached, _cached_at, fresh = self._read_shard_cache()
        if not live and cached:
            return cached

        shards_file = self.repo_root / "scripts/data_catalog/datacite_y2025_parallel_shards.list"
        if not shards_file.exists():
            return cached or []
        rows: list[dict[str, Any]] = []
        for line in shards_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            shard, host, _created, _query, target_s = line.split("|", 4)
            target = int(target_s)
            progress = 0
            rate = 0.0
            status = "unknown"
            updated_at = ""
            if host == "local":
                base = self.repo_root / "data_lake/dataset_catalog/index_v3" / shard
                comp = base / "datacite.complete.json"
                if comp.exists():
                    progress = int(json.loads(comp.read_text()).get("committed_records", 0))
                    status = "complete"
                else:
                    cp = json.loads((base / "datacite.checkpoint.json").read_text()) if (base / "datacite.checkpoint.json").exists() else {}
                    hb = json.loads((base / "datacite.heartbeat.json").read_text()) if (base / "datacite.heartbeat.json").exists() else {}
                    chunks = len(list(base.glob("datacite_*.jsonl.gz")))
                    progress = int(cp.get("committed_records", 0)) + chunks * 50000 + int(hb.get("uncommitted_records", 0))
                    rate = float(hb.get("records_per_second", 0))
                    updated_at = str(hb.get("updated_at", ""))
                    status = "running"
            elif live:
                ok, probe = self._ssh_probe_shard(host, shard)
                if ok:
                    if probe.get("complete"):
                        status = "complete"
                        progress = int(probe.get("committed") or target)
                    else:
                        progress = int(probe.get("committed") or 0)
                        updated_at = str(probe.get("activity_utc") or "")
                        lane_status = str(probe.get("status") or "unknown")
                        status = "running" if lane_status in {"running", "idle"} else lane_status
                else:
                    status = "unreachable"
            else:
                status = "cached_pending"
            pct = round(100 * progress / target, 1) if target else 0
            eta_h = round((target - progress) / rate / 3600, 1) if rate > 0 and status == "running" else None
            rows.append(
                {
                    "shard": shard,
                    "host": host,
                    "status": status,
                    "progress": progress,
                    "target": target,
                    "percent": pct,
                    "rate_per_sec": rate,
                    "eta_hours": eta_h,
                    "updated_at": updated_at,
                }
            )
        if live and rows:
            merged = self._merge_shard_rows(rows, cached)
            if any(r.get("status") not in {"unreachable", "cached_pending", "unknown"} for r in merged):
                self._write_shard_cache(merged)
            return merged
        elif not live and cached:
            return cached
        return rows

    def datacite_summary(self, live: bool = False) -> dict[str, Any]:
        index_root = self.repo_root / "data_lake/dataset_catalog/index_v3"
        completed = []
        committed = 0
        for lane_dir in sorted(index_root.glob("y*")):
            comp = lane_dir / "datacite.complete.json"
            if comp.exists():
                n = int(json.loads(comp.read_text()).get("committed_records", 0))
                completed.append({"lane": lane_dir.name, "records": n})
                committed += n
        shards = self.datacite_shards(live=live)
        y2025_target = sum(s["target"] for s in shards)
        y2025_progress = sum(s["progress"] if s["status"] != "complete" else s["target"] for s in shards)
        y2025_pct = round(100 * y2025_progress / y2025_target, 1) if y2025_target else 0
        total_target = 129_292_246
        total_progress = committed + y2025_progress
        _c, cached_at, cache_fresh = self._read_shard_cache()
        return {
            "completed_lanes": completed,
            "y2025_shards": shards,
            "y2025_percent": y2025_pct,
            "y2025_progress": y2025_progress,
            "y2025_target": y2025_target,
            "total_progress": total_progress,
            "total_target": total_target,
            "total_percent": round(100 * total_progress / total_target, 1) if total_target else 0,
            "shard_cache_at": cached_at,
            "shard_cache_fresh": cache_fresh and not live,
        }

    def gdelt_summary(self) -> dict[str, Any]:
        ok_dir = self.repo_root / "data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023"
        ok_count = len(list(ok_dir.glob("*.ok.json"))) if ok_dir.exists() else 0
        pending_big = len(
            list((self.repo_root / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk").glob("*/asia_gkg_filtered.csv.gz"))
        )
        fleet_running = bool(subprocess.run(["pgrep", "-f", "run_news_shock_gkg_queue_fleet"], capture_output=True).returncode == 0)
        return {"ok_months": ok_count, "pending_upload_months": pending_big, "fleet_running": fleet_running}

    def job_stats(self) -> dict[str, Any]:
        if self.orchestrator:
            return self.orchestrator.stats()
        if self.agent and getattr(self.agent, "store", None):
            return self.agent.store.status_counts()
        return {
            "pending_approval": 0,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "total": 0,
            "lifetime": {
                "pending_approval": 0,
                "queued": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
            },
            "actionable": {
                "pending_approval": 0,
                "queued": 0,
                "running": 0,
                "failed_recent_days": 7,
                "failed_recent": 0,
                "cancelled_recent": 0,
                "pending_oldest_age_days": None,
            },
            "failed_recent": 0,
            "cancelled_recent": 0,
            "recent_days": 7,
            "semantics": (
                "pending_approval/queued/running are live; "
                "failed/cancelled are lifetime totals — use failed_recent/"
                "cancelled_recent for actionable debt"
            ),
        }

    def acquisitions(self, live: bool = False) -> list[dict[str, Any]]:
        dc = self.datacite_summary(live=live)
        gdelt = self.gdelt_summary()
        cq = ops_status.collection_queue_status(self.repo_root)
        items: list[dict[str, Any]] = []

        y2025_running = any(s["status"] == "running" for s in dc["y2025_shards"])
        y2025_done = dc["y2025_percent"] >= 100
        items.append(
            {
                "id": "datacite",
                "name": "DataCite",
                "subtitle": "DOI metadata harvest",
                "scope": "2011–2026 · all dataset DOIs",
                "stage": _stage(dc["total_percent"], y2025_running, y2025_done and len(dc["completed_lanes"]) >= 3),
                "tone": _tone(_stage(dc["total_percent"], y2025_running, dc["total_percent"] >= 99)),
                "progress": dc["total_percent"],
                "amount": f"{_fmt_num(dc['total_progress'])} / {_fmt_num(dc['total_target'])} records",
                "worker": f"{len(dc['y2025_shards'])} shards",
                "destination": "GDrive · dataset_catalog/datacite",
                "updated_at": (max((s.get("updated_at") or "") for s in dc["y2025_shards"]) if dc["y2025_shards"] else "") or _now(),
                "detail": dc,
            }
        )

        gdelt_pct = min(100, round(100 * gdelt["ok_months"] / 72, 1)) if gdelt["ok_months"] else 0
        items.append(
            {
                "id": "gdelt",
                "name": "GDELT Asia GKG",
                "subtitle": "News shock backbone",
                "scope": "2018–2023 · monthly windows",
                "stage": "running" if gdelt["fleet_running"] else ("complete" if gdelt_pct >= 95 else "idle"),
                "tone": _tone("running" if gdelt["fleet_running"] else "complete"),
                "progress": gdelt_pct,
                "amount": f"{gdelt['ok_months']} uploaded · {gdelt['pending_upload_months']} local pending",
                "worker": "GDELT fleet",
                "destination": "Local + GDrive",
                "updated_at": _now(),
                "detail": gdelt,
            }
        )

        enabled = cq.get("enabled_tasks") or []
        lock = cq.get("lock") or {}
        items.append(
            {
                "id": "collection_queue",
                "name": "Public collection queue",
                "subtitle": "Unattended local procurement",
                "scope": f"{len(enabled)} enabled tasks",
                "stage": "running" if lock.get("alive") else "idle",
                "tone": "blue" if lock.get("alive") else "amber",
                "progress": 0,
                "amount": ", ".join(enabled[:4]) + ("…" if len(enabled) > 4 else ""),
                "worker": "optiplex",
                "destination": "data_lake/",
                "updated_at": (cq.get("latest") or {}).get("finished_at", _now()),
                "detail": cq,
            }
        )

        for pid, meta in self.cfg.get("pipelines", {}).items():
            pattern = Path(meta["command"][-1]).name
            running = subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0
            items.append(
                {
                    "id": f"pipeline_{pid}",
                    "name": meta.get("label", pid),
                    "subtitle": "Registered pipeline",
                    "scope": pattern,
                    "stage": "running" if running else "idle",
                    "tone": "green" if running else "amber",
                    "progress": 100 if running else 0,
                    "amount": "active" if running else "stopped",
                    "worker": meta.get("pool", "optiplex"),
                    "destination": "cluster",
                    "updated_at": _now(),
                    "detail": {"pipeline_id": pid, "running": running},
                }
            )

        items.extend(partition_lanes(self.repo_root))
        return items

    def workers(self, live: bool = True) -> dict[str, Any]:
        joined = [w for w in self.windows_workers() if w.get("status") == "joined"]
        runtime = self.orchestrator.runtime_health() if self.orchestrator else None
        by_id = _runtime_worker_index(runtime)
        nodes = []
        for w in joined:
            ip = w.get("tailscale_ip", "")
            ok = False
            if live and ip:
                ok, _ = self._ssh_probe(ip, "hostname", timeout=8)
            runtime_id = _inventory_runtime_id(w)
            runtime_worker = by_id.get(runtime_id or "") if runtime_id else None
            honesty = _effective_worker_status(
                inventory_status=str(w.get("status") or ""),
                runtime_worker=runtime_worker,
            )
            nodes.append(
                {
                    "hostname": w.get("hostname", ""),
                    "tailscale_ip": ip,
                    "status": honesty["effective_status"],
                    "inventory_status": honesty["inventory_status"],
                    "runtime_id": honesty["runtime_id"],
                    "freshness": honesty["freshness"],
                    "ssh_ok": ok if live else None,
                    "pool": "windows_lab",
                }
            )
        # Surface probe/diag leftovers separately so they are not mistaken for lab capacity.
        junk = [
            worker
            for wid, worker in by_id.items()
            if wid.startswith("probe-") or wid.endswith("-diag")
        ]
        return {
            "windows_lab": nodes,
            "datacite_shards": self.datacite_shards(live=live),
            "local_controller": {"hostname": self.cfg["controller"]["hostname"], "pool": "optiplex"},
            "spectator": self.cfg["worker_pools"].get("spectator", {}),
            "storage": self.cfg.get("storage", {}),
            "runtime": runtime,
            "runtime_junk": junk,
            "semantics": {
                "inventory_joined": "configured for routing",
                "online": "heartbeat within stale threshold",
                "idle": "joined worker with recent-but-expired heartbeat (typical when no job running)",
                "stale": "heartbeat older than idle grace, or probe leftover",
                "joined_unseen": "inventory joined but never seen in runtime store",
            },
        }

    def status(self, live: bool = False) -> dict[str, Any]:
        dc = self.datacite_summary(live=live)
        runtime = self.orchestrator.runtime_health() if self.orchestrator else None
        return {
            "cluster": self.cfg["name"],
            "controller": self.cfg["controller"]["hostname"],
            "generated_at": _now(),
            "disk": self.disk(),
            "worker_pools": {
                "windows_lab": {
                    "joined": len([w for w in self.windows_workers() if w.get("status") == "joined"]),
                    "total": len(self.windows_workers()),
                    "note": "joined is inventory; see /yzu/workers for effective online/idle/stale",
                }
            },
            "datacite": dc,
            "gdelt": self.gdelt_summary(),
            "jobs": self.job_stats(),
            "storage": self.cfg.get("storage", {}),
            "runtime": runtime,
            "live": live,
        }

    def activity(self, live: bool = False) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        for shard in self.datacite_shards(live=live):
            if shard.get("updated_at"):
                events.append(
                    {
                        "ts": shard["updated_at"],
                        "message": f"DataCite {shard['shard']} @ {shard['host']}: {_fmt_num(shard['progress'])} ({shard['percent']}%)",
                        "live": shard["status"] == "running",
                    }
                )
        if self.agent:
            store = self.orchestrator.store if self.orchestrator else self.agent.store
            for job in store.list(12):
                events.append(
                    {
                        "ts": job.get("updated_at", ""),
                        "message": f"Job {job['id']}: {job['title']} — {job['status']}",
                        "live": job["status"] in {"queued", "running"},
                    }
                )
                for ev in (job.get("events") or [])[-1:]:
                    events.append(
                        {
                            "ts": ev.get("created_at", job.get("updated_at", "")),
                            "message": f"Job {job['id']}: {ev.get('message', '')}",
                            "live": job["status"] in {"queued", "running"},
                        }
                    )
        events.sort(key=lambda row: row.get("ts", ""), reverse=True)
        return events[:20]
