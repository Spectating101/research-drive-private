"""Resource requirements, reservations, and usage accounting for YZU workers."""
from __future__ import annotations

from typing import Any, Mapping

from ._interop_common import now_utc

RESOURCE_KEYS = ("cpu_cores", "memory_mb", "disk_mb", "network_mb", "gpu_count")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def normalize_requirements(values: Mapping[str, Any] | None) -> dict[str, float]:
    values = values or {}
    aliases = {
        "cpu": "cpu_cores", "cores": "cpu_cores", "ram_mb": "memory_mb", "memory": "memory_mb",
        "disk": "disk_mb", "storage_mb": "disk_mb", "network": "network_mb", "gpu": "gpu_count",
        "gpus": "gpu_count",
    }
    result = {key: 0.0 for key in RESOURCE_KEYS}
    for raw_key, raw_value in values.items():
        key = aliases.get(str(raw_key).strip().lower(), str(raw_key).strip().lower())
        if key in result and (number := _number(raw_value)) is not None:
            result[key] = number
    if _number(values.get("memory_gb")) is not None:
        result["memory_mb"] = float(values["memory_gb"]) * 1024
    if _number(values.get("disk_gb")) is not None:
        result["disk_mb"] = float(values["disk_gb"]) * 1024
    return result


def normalize_capacity(values: Mapping[str, Any] | None) -> dict[str, float | None]:
    values = values or {}
    result: dict[str, float | None] = {key: None for key in RESOURCE_KEYS}
    aliases = {
        "cpu": "cpu_cores", "cores": "cpu_cores", "ram_mb": "memory_mb", "memory": "memory_mb",
        "free_memory_mb": "memory_mb", "disk": "disk_mb", "free_disk_mb": "disk_mb",
        "network": "network_mb", "gpu": "gpu_count", "gpus": "gpu_count",
    }
    for raw_key, raw_value in values.items():
        key = aliases.get(str(raw_key).strip().lower(), str(raw_key).strip().lower())
        if key in result and (number := _number(raw_value)) is not None:
            result[key] = number
    if _number(values.get("memory_gb")) is not None:
        result["memory_mb"] = float(values["memory_gb"]) * 1024
    if _number(values.get("disk_gb")) is not None:
        result["disk_mb"] = float(values["disk_gb"]) * 1024
    return result


class ResourceMixin:
    def _init_resources(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS run_resources(
          run_id TEXT PRIMARY KEY,cpu_cores REAL NOT NULL,memory_mb REAL NOT NULL,disk_mb REAL NOT NULL,
          network_mb REAL NOT NULL,gpu_count REAL NOT NULL,priority INTEGER NOT NULL DEFAULT 50,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS reservations(
          run_id TEXT PRIMARY KEY,worker_id TEXT NOT NULL,cpu_cores REAL NOT NULL,memory_mb REAL NOT NULL,
          disk_mb REAL NOT NULL,network_mb REAL NOT NULL,gpu_count REAL NOT NULL,reserved_at TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
          FOREIGN KEY(worker_id) REFERENCES workers(worker_id));
        CREATE TABLE IF NOT EXISTS run_usage(
          usage_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,worker_id TEXT,cpu_seconds REAL,
          memory_peak_mb REAL,disk_written_mb REAL,network_bytes REAL,api_calls REAL,storage_bytes REAL,
          recorded_at TEXT NOT NULL,FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_reservations_worker ON reservations(worker_id);
        CREATE INDEX IF NOT EXISTS idx_usage_run ON run_usage(run_id,usage_id);
        """)

    def _store_requirements(self, run_id: str, requirements: Mapping[str, Any] | None) -> None:
        normalized = normalize_requirements(requirements)
        priority = int((requirements or {}).get("priority") or 50)
        self.db.execute(
            "INSERT OR REPLACE INTO run_resources VALUES(?,?,?,?,?,?,?)",
            (run_id, normalized["cpu_cores"], normalized["memory_mb"], normalized["disk_mb"],
             normalized["network_mb"], normalized["gpu_count"], priority),
        )

    def requirements(self, run_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM run_resources WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return {**{key: 0.0 for key in RESOURCE_KEYS}, "priority": 50}
        return {key: row[key] for key in RESOURCE_KEYS} | {"priority": row["priority"]}

    def reserved(self, worker_id: str) -> dict[str, float]:
        row = self.db.execute(
            "SELECT COALESCE(SUM(cpu_cores),0) cpu_cores,COALESCE(SUM(memory_mb),0) memory_mb,"
            "COALESCE(SUM(disk_mb),0) disk_mb,COALESCE(SUM(network_mb),0) network_mb,"
            "COALESCE(SUM(gpu_count),0) gpu_count FROM reservations WHERE worker_id=?",
            (worker_id,),
        ).fetchone()
        return {key: float(row[key]) for key in RESOURCE_KEYS}

    def resource_fit(self, run_id: str, worker_id: str) -> dict[str, Any]:
        required = self.requirements(run_id)
        requested = {key: float(required[key]) for key in RESOURCE_KEYS}
        if not any(requested.values()):
            return {"status": "not_required", "eligible": True, "required": requested, "missing": [], "available": {}}
        worker = self.worker(worker_id)
        capacity = normalize_capacity(worker.get("capacity"))
        reserved = self.reserved(worker_id)
        available = {
            key: None if capacity[key] is None else max(0.0, float(capacity[key]) - reserved[key])
            for key in RESOURCE_KEYS
        }
        unknown = [key for key, amount in requested.items() if amount > 0 and available[key] is None]
        missing = [
            key for key, amount in requested.items()
            if amount > 0 and available[key] is not None and amount > float(available[key])
        ]
        if missing:
            status = "blocked"
        elif unknown:
            status = "unknown"
        else:
            status = "satisfied"
        return {
            "status": status, "eligible": status in {"satisfied", "not_required"},
            "required": requested, "reserved": reserved, "available": available,
            "missing": missing, "unknown": unknown,
        }

    def _resource_fit(self, run_id: str, worker_id: str) -> bool:
        return bool(self.resource_fit(run_id, worker_id)["eligible"])

    def _reserve_resources(self, run_id: str, worker_id: str, *, at: str) -> None:
        fit = self.resource_fit(run_id, worker_id)
        if not fit["eligible"]:
            raise ValueError(f"worker capacity does not satisfy run: {fit['status']}")
        required = fit["required"]
        self.db.execute(
            "INSERT OR REPLACE INTO reservations VALUES(?,?,?,?,?,?,?,?)",
            (run_id, worker_id, required["cpu_cores"], required["memory_mb"], required["disk_mb"],
             required["network_mb"], required["gpu_count"], at),
        )

    def reservation(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM reservations WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return {
            "worker_id": row["worker_id"], **{key: row[key] for key in RESOURCE_KEYS},
            "reserved_at": row["reserved_at"],
        }

    def _release_resources(self, run_id: str) -> None:
        self.db.execute("DELETE FROM reservations WHERE run_id=?", (run_id,))

    def record_usage(self, run_id: str, *, worker_id: str | None = None, cpu_seconds: float | None = None,
                     memory_peak_mb: float | None = None, disk_written_mb: float | None = None,
                     network_bytes: float | None = None, api_calls: float | None = None,
                     storage_bytes: float | None = None, at: str | None = None) -> dict[str, Any]:
        self._row(run_id)
        at = at or now_utc()
        values = [cpu_seconds, memory_peak_mb, disk_written_mb, network_bytes, api_calls, storage_bytes]
        if any(value is not None and (_number(value) is None) for value in values):
            raise ValueError("usage values must be non-negative numbers")
        self.db.execute(
            "INSERT INTO run_usage(run_id,worker_id,cpu_seconds,memory_peak_mb,disk_written_mb,network_bytes,api_calls,storage_bytes,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (run_id, worker_id, cpu_seconds, memory_peak_mb, disk_written_mb, network_bytes, api_calls, storage_bytes, at),
        )
        return self.usage(run_id)

    def usage(self, run_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT COALESCE(SUM(cpu_seconds),0) cpu_seconds,COALESCE(MAX(memory_peak_mb),0) memory_peak_mb,"
            "COALESCE(SUM(disk_written_mb),0) disk_written_mb,COALESCE(SUM(network_bytes),0) network_bytes,"
            "COALESCE(SUM(api_calls),0) api_calls,COALESCE(SUM(storage_bytes),0) storage_bytes,COUNT(*) samples "
            "FROM run_usage WHERE run_id=?", (run_id,),
        ).fetchone()
        return {
            key: row[key]
            for key in ("cpu_seconds", "memory_peak_mb", "disk_written_mb", "network_bytes", "api_calls", "storage_bytes", "samples")
        }

    def resources_rollup(self) -> dict[str, Any]:
        workers = []
        for row in self.db.execute("SELECT worker_id FROM workers ORDER BY worker_id"):
            worker = self.worker(row["worker_id"])
            workers.append({
                **worker,
                "capacity_normalized": normalize_capacity(worker.get("capacity")),
                "reserved": self.reserved(worker["id"]),
            })
        usage = self.db.execute(
            "SELECT COALESCE(SUM(cpu_seconds),0),COALESCE(SUM(network_bytes),0),"
            "COALESCE(SUM(api_calls),0),COALESCE(SUM(storage_bytes),0) FROM run_usage"
        ).fetchone()
        return {
            "workers": workers,
            "usage": {
                "cpu_seconds": usage[0], "network_bytes": usage[1],
                "api_calls": usage[2], "storage_bytes": usage[3],
            },
        }
