from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any, Iterable, Iterator, Mapping
from uuid import uuid4

ALIASES = {
    "approval_required": "pending_approval", "needs_approval": "pending_approval",
    "submitted": "queued", "pending": "queued", "claimed": "assigned", "starting": "assigned",
    "retry": "retrying", "executing": "running", "collecting": "running",
    "testing": "validating", "verifying": "validating", "uploading": "archiving",
    "materializing": "registering", "complete": "completed", "success": "completed",
    "succeeded": "completed", "stalled": "blocked", "cancelled": "blocked",
    "canceled": "blocked", "error": "failed",
}
ORDER = {"pending_approval": 0, "queued": 1, "assigned": 2, "retrying": 2, "running": 3,
         "validating": 4, "archiving": 5, "registering": 6, "completed": 7,
         "registered": 8, "blocked": 90, "failed": 91, "unknown": -1}
TERMINAL = {"completed", "registered", "blocked", "failed"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def stage(value: Any) -> str:
    key = str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    return ALIASES.get(key, key or "unknown")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def ids(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or ():
        if isinstance(value, (str, int, float)):
            item = str(value)
        elif isinstance(value, Mapping):
            item = next(
                (str(value[key]) for key in ("dataset_id", "asset_id", "id", "name", "uri", "path")
                 if value.get(key) not in (None, "")),
                "",
            )
        else:
            item = ""
        if item and item not in result:
            result.append(item)
    return result


def normalize_capabilities(values: Iterable[Any] | None) -> list[str]:
    aliases = {
        "python3": "python", "py": "python", "requests": "http", "download": "http",
        "cdp": "browser", "puppeteer": "browser", "playwright": "browser",
        "rclone": "archive", "gdrive": "archive", "etl": "pipeline",
    }
    normalized = {str(value).strip().lower().replace("-", "_") for value in values or () if str(value).strip()}
    return sorted({aliases.get(value, value) for value in normalized})


@dataclass(frozen=True)
class Claim:
    run_id: str
    job_id: str
    job_type: str
    attempt: int
    worker_id: str
    required_capabilities: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    resource_requirements: tuple[tuple[str, float], ...]
    lease_expires_at: str


class BaseStore:
    def __init__(self, database: str | sqlite3.Connection = ":memory:") -> None:
        self.owns = not isinstance(database, sqlite3.Connection)
        self.db = sqlite3.connect(database, timeout=30, isolation_level=None) if self.owns else database
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS workers(
          worker_id TEXT PRIMARY KEY,pool TEXT,status TEXT NOT NULL,capabilities TEXT NOT NULL,
          capacity TEXT NOT NULL,heartbeat_at TEXT,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(
          run_id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,job_type TEXT NOT NULL,title TEXT,
          stage TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,
          retryable INTEGER NOT NULL DEFAULT 1,required_capabilities TEXT NOT NULL,inputs TEXT NOT NULL,
          outputs TEXT NOT NULL,worker_id TEXT,pool TEXT,lease_expires_at TEXT,progress_current REAL,
          progress_total REAL,manifest_id TEXT,archive_verified INTEGER NOT NULL DEFAULT 0,registry_id TEXT,
          rows_count INTEGER,fields_count INTEGER,entities_count INTEGER,error TEXT,created_at TEXT NOT NULL,
          started_at TEXT,finished_at TEXT,updated_at TEXT NOT NULL,
          FOREIGN KEY(worker_id) REFERENCES workers(worker_id));
        CREATE TABLE IF NOT EXISTS events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,stage TEXT NOT NULL,
          event_type TEXT NOT NULL,timestamp TEXT NOT NULL,worker_id TEXT,attempt INTEGER,message TEXT,
          payload TEXT NOT NULL,FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS assets(
          dataset_id TEXT PRIMARY KEY,registry_id TEXT NOT NULL,revision_id TEXT,title TEXT,readiness TEXT NOT NULL,
          verification_state TEXT NOT NULL,verification_summary TEXT,source TEXT NOT NULL,lineage_inputs TEXT NOT NULL,
          source_snapshots TEXT NOT NULL,manifest_id TEXT NOT NULL,checksum TEXT,method_revision TEXT,vault_path TEXT NOT NULL,
          archive_verified INTEGER NOT NULL,refresh_policy TEXT,last_refreshed_at TEXT,next_refresh_at TEXT,stale INTEGER NOT NULL,
          rows_count INTEGER,fields_count INTEGER,entities_count INTEGER,grain TEXT,coverage TEXT,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_runs_stage ON runs(stage,created_at);
        CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id,event_id);
        """)

    def close(self) -> None:
        if self.owns:
            self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def worker(self, worker_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if row is None:
            raise KeyError(worker_id)
        return {
            "id": row["worker_id"], "pool": row["pool"], "status": row["status"],
            "capabilities": loads(row["capabilities"], []), "capacity": loads(row["capacity"], {}),
            "heartbeat_at": row["heartbeat_at"], "updated_at": row["updated_at"],
        }

    def upsert_worker(self, worker_id: str, *, pool: str | None = None, status: str = "online",
                      capabilities: Iterable[str] = (), capacity: Mapping[str, Any] | None = None,
                      heartbeat_at: str | None = None) -> dict[str, Any]:
        if not worker_id:
            raise ValueError("worker_id is required")
        at = heartbeat_at or now_utc()
        self.db.execute(
            """INSERT INTO workers VALUES(?,?,?,?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET
            pool=excluded.pool,status=excluded.status,capabilities=excluded.capabilities,capacity=excluded.capacity,
            heartbeat_at=excluded.heartbeat_at,updated_at=excluded.updated_at""",
            (worker_id, pool, status, dumps(normalize_capabilities(capabilities)), dumps(dict(capacity or {})), at, at),
        )
        return self.worker(worker_id)

    def submit(self, *, job_id: str, job_type: str, title: str | None = None,
               required_capabilities: Iterable[str] = (), inputs: Iterable[Any] = (), outputs: Iterable[Any] = (),
               pending_approval: bool = False, max_attempts: int = 3, retryable: bool = True,
               resource_requirements: Mapping[str, Any] | None = None,
               run_id: str | None = None) -> dict[str, Any]:
        if not job_id or not job_type:
            raise ValueError("job_id and job_type are required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        at, run_id = now_utc(), run_id or f"run-{uuid4().hex}"
        state = "pending_approval" if pending_approval else "queued"
        with self.transaction():
            self.db.execute(
                """INSERT INTO runs(run_id,job_id,job_type,title,stage,max_attempts,retryable,
                required_capabilities,inputs,outputs,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, job_id, job_type, title, state, max_attempts, int(retryable),
                 dumps(normalize_capabilities(required_capabilities)), dumps(ids(inputs)), dumps(ids(outputs)), at, at),
            )
            self._store_requirements(run_id, resource_requirements)
            self._event(run_id, state, state, at=at)
        return self.snapshot(run_id)

    def approve(self, run_id: str) -> dict[str, Any]:
        if self._row(run_id)["stage"] != "pending_approval":
            raise ValueError("run is not pending approval")
        return self.record(run_id, "queued", event_type="approved")

    def claim(self, worker_id: str, *, lease_seconds: int = 120, at: str | None = None) -> Claim | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        at = at or now_utc()
        worker = self.worker(worker_id)
        if worker["status"] not in {"online", "ready", "idle"}:
            return None
        available = set(normalize_capabilities(worker["capabilities"]))
        expiry = (
            (parse_time(at) or datetime.now(timezone.utc)) + timedelta(seconds=lease_seconds)
        ).isoformat().replace("+00:00", "Z")
        with self.transaction():
            rows = self.db.execute(
                "SELECT * FROM runs WHERE stage IN('queued','retrying') AND attempt<max_attempts ORDER BY created_at,run_id"
            ).fetchall()
            selected = next(
                (
                    row for row in rows
                    if set(loads(row["required_capabilities"], [])).issubset(available)
                    and self._resource_fit(row["run_id"], worker_id)
                ),
                None,
            )
            if selected is None:
                return None
            attempt = int(selected["attempt"]) + 1
            self._reserve_resources(selected["run_id"], worker_id, at=at)
            self.db.execute(
                "UPDATE runs SET stage='assigned',attempt=?,worker_id=?,pool=?,lease_expires_at=?,error=NULL,updated_at=? WHERE run_id=?",
                (attempt, worker_id, worker["pool"], expiry, at, selected["run_id"]),
            )
            self._event(
                selected["run_id"], "assigned", "assigned", at=at, worker_id=worker_id, attempt=attempt,
                payload={"lease_expires_at": expiry},
            )
        row = self._row(selected["run_id"])
        requirements = self.requirements(row["run_id"])
        return Claim(
            row["run_id"], row["job_id"], row["job_type"], attempt, worker_id,
            tuple(loads(row["required_capabilities"], [])), tuple(loads(row["inputs"], [])),
            tuple(loads(row["outputs"], [])),
            tuple(sorted((key, float(value)) for key, value in requirements.items() if key != "priority")),
            expiry,
        )

    def _store_requirements(self, run_id: str, requirements: Mapping[str, Any] | None) -> None:
        del run_id, requirements

    def _resource_fit(self, run_id: str, worker_id: str) -> bool:
        del run_id, worker_id
        return True

    def _reserve_resources(self, run_id: str, worker_id: str, *, at: str) -> None:
        del run_id, worker_id, at

    def _release_resources(self, run_id: str) -> None:
        del run_id

    def requirements(self, run_id: str) -> dict[str, Any]:
        del run_id
        return {}

    def _row(self, run_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return row

    def _transition(self, current: str, nxt: str) -> None:
        current, nxt = stage(current), stage(nxt)
        if current == nxt:
            return
        if current == "registered":
            raise ValueError("registered runs are immutable")
        if current == "completed" and nxt != "registered":
            raise ValueError("completed execution may only advance to registered")
        if current in {"failed", "blocked"} and nxt != "retrying":
            raise ValueError("failed or blocked runs must retry before advancing")
        if nxt in {"failed", "blocked"}:
            return
        if ORDER.get(nxt, -1) < ORDER.get(current, -1):
            raise ValueError(f"stage regression is not allowed: {current} -> {nxt}")

    def _event(self, run_id: str, state: str, event_type: str, *, at: str,
               worker_id: str | None = None, attempt: int | None = None,
               message: str | None = None, payload: Mapping[str, Any] | None = None) -> None:
        self.db.execute(
            "INSERT INTO events(run_id,stage,event_type,timestamp,worker_id,attempt,message,payload) VALUES(?,?,?,?,?,?,?,?)",
            (run_id, stage(state), event_type, at, worker_id, attempt, message, dumps(dict(payload or {}))),
        )
