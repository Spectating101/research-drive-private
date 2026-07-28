"""Durable, non-executing Discover source refresh subscriptions.

Linked to a Discover intent / source / connector. Cadence and pause/resume/stop
are persisted honestly, but subscriptions are review records only: they never
arm a next run or submit collection jobs.
"""

from __future__ import annotations

from contextlib import contextmanager

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Any

ALLOWED_CADENCES = frozenset({"manual", "daily", "weekly", "monthly"})
ACTIVE = "active"
PAUSED = "paused"
STOPPED = "stopped"
ALLOWED_STATUS = frozenset({ACTIVE, PAUSED, STOPPED})

EXECUTION_MODE_NON = "non_executing"
EXECUTION_NOTE_NON = "Recorded for Discover History and review only; no automatic next run is enabled."


def discover_refresh_store_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/procurement_memory/discover_refresh_subscriptions.sqlite3"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value or {}))


class DiscoverRefreshStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS discover_refresh_subscriptions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    intent_id TEXT,
                    source_id TEXT,
                    connector_id TEXT,
                    candidate_key TEXT,
                    cadence TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    destination TEXT,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_discover_refresh_updated ON discover_refresh_subscriptions(updated_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_discover_refresh_intent ON discover_refresh_subscriptions(intent_id)"
            )

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        """Open a short-lived connection that always closes.

        Python 3.12+ ``Connection.__exit__`` commits/rollbacks but no longer
        closes the handle, so ``with sqlite3.connect(...)`` leaks FDs under
        desk polling (/health, job list, workers).
        """
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _armed_state(
        self,
        *,
        cadence: str,
        status: str,
        enabled: bool,
        requested_schedule: str,
        schedule_note: str,
        schedule_spec: dict[str, Any],
        last_run_at: str | None = None,
        last_job_id: str | None = None,
        after: datetime | None = None,
        clear_next: bool = False,
    ) -> dict[str, Any]:
        spec = dict(schedule_spec or {})
        spec["executable"] = False
        spec["note"] = "Schedule recorded for review only; no automatic execution is enabled."
        return {
            "execution_mode": EXECUTION_MODE_NON,
            "execution_note": EXECUTION_NOTE_NON,
            "last_run_at": last_run_at,
            "next_run_at": None,
            "last_job_id": last_job_id,
            "auto_refresh": False,
            "requested_schedule": requested_schedule,
            "schedule_note": schedule_note,
            "schedule_spec": spec,
        }

    def create(
        self,
        *,
        cadence: str = "manual",
        destination: str = "",
        intent_id: str = "",
        source_id: str = "",
        connector_id: str = "",
        candidate_key: str = "",
        enabled: bool = True,
        requested_schedule: str = "",
        schedule_note: str = "",
        timezone: str = "",
        schedule_spec: dict | None = None,
    ) -> dict[str, Any]:
        cad = str(cadence or "manual").strip().lower()
        if cad not in ALLOWED_CADENCES:
            raise ValueError(f"cadence must be one of {sorted(ALLOWED_CADENCES)}")
        source_id = str(source_id or "").strip()
        connector_id = str(connector_id or "").strip()
        intent_id = str(intent_id or "").strip()
        candidate_key = str(candidate_key or "").strip()
        if not (source_id or connector_id or candidate_key or intent_id):
            raise ValueError("subscription requires intent_id, source_id, connector_id, or candidate_key")

        sid = uuid.uuid4().hex[:16]
        stamp = _now()
        from scripts.research_data_mcp.discover_schedule_spec import build_schedule_spec

        req = str(requested_schedule or "").strip()[:240]
        note = str(schedule_note or "").strip()[:400]
        spec = build_schedule_spec(
            requested_schedule=req,
            cadence=cad,
            timezone=timezone or "",
            explicit=schedule_spec if isinstance(schedule_spec, dict) else None,
        )
        status = ACTIVE if enabled else PAUSED
        state = self._armed_state(
            cadence=cad,
            status=status,
            enabled=status == ACTIVE,
            requested_schedule=req or str(spec.get("requested_schedule") or ""),
            schedule_note=note,
            schedule_spec=spec,
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO discover_refresh_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    stamp,
                    stamp,
                    intent_id[:64],
                    source_id[:160],
                    connector_id[:160],
                    candidate_key[:320],
                    cad,
                    1 if status == ACTIVE else 0,
                    str(destination or "").strip()[:400],
                    status,
                    json.dumps(state),
                ),
            )
        return self.get(sid)

    def get(self, subscription_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM discover_refresh_subscriptions WHERE id = ?", (subscription_id,)
            ).fetchone()
        if not row:
            raise KeyError(subscription_id)
        return self._row(dict(row))

    def list(self, *, limit: int = 50, intent_id: str = "", status: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        sql = "SELECT * FROM discover_refresh_subscriptions WHERE 1=1"
        args: list[Any] = []
        if intent_id:
            sql += " AND intent_id = ?"
            args.append(intent_id)
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(sql, args).fetchall()
        return [self._row(dict(r)) for r in rows]

    def list_due(self, *, now: datetime | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Subscriptions are descriptive records, so none can become due."""
        _ = now, limit
        return []

    def _row(self, item: dict[str, Any]) -> dict[str, Any]:
        state = json.loads(item.pop("state_json") or "{}")
        status = str(item.get("status") or ACTIVE)
        enabled = bool(item.get("enabled")) and status == ACTIVE
        schedule_spec = dict(state.get("schedule_spec") or {})
        schedule_spec["executable"] = False
        out = {
            "id": item["id"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "intent_id": item.get("intent_id") or "",
            "source_id": item.get("source_id") or "",
            "connector_id": item.get("connector_id") or "",
            "candidate_key": item.get("candidate_key") or "",
            "cadence": item.get("cadence") or "manual",
            "enabled": enabled,
            "destination": item.get("destination") or "",
            "status": status,
            "execution_mode": EXECUTION_MODE_NON,
            "execution_note": EXECUTION_NOTE_NON,
            "auto_refresh": False,
            "requested_schedule": state.get("requested_schedule") or "",
            "schedule_note": state.get("schedule_note") or "",
            "schedule_spec": schedule_spec,
            "last_run_at": state.get("last_run_at") or None,
            "next_run_at": None,
            "last_job_id": state.get("last_job_id") or None,
            "last_run_status": state.get("last_run_status") or None,
            "last_run_plan": state.get("last_run_plan") or None,
            "last_run_error": state.get("last_run_error") or None,
        }
        from scripts.research_data_mcp.discover_progress import attach_subscription_progress

        return attach_subscription_progress(out)

    def _save(self, subscription_id: str, *, state_patch: dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
        current = self.get(subscription_id)
        state = {
            "execution_mode": current.get("execution_mode") or EXECUTION_MODE_NON,
            "execution_note": current.get("execution_note") or EXECUTION_NOTE_NON,
            "last_run_at": current.get("last_run_at"),
            "next_run_at": current.get("next_run_at"),
            "last_job_id": current.get("last_job_id"),
            "last_run_status": current.get("last_run_status"),
            "last_run_plan": current.get("last_run_plan"),
            "last_run_error": current.get("last_run_error"),
            "auto_refresh": bool(current.get("auto_refresh")),
            "requested_schedule": current.get("requested_schedule") or "",
            "schedule_note": current.get("schedule_note") or "",
            "schedule_spec": current.get("schedule_spec") or {},
        }
        if state_patch:
            state.update(_clone(state_patch))
        schedule_spec = dict(state.get("schedule_spec") or {})
        schedule_spec["executable"] = False
        state.update(
            {
                "execution_mode": EXECUTION_MODE_NON,
                "execution_note": EXECUTION_NOTE_NON,
                "auto_refresh": False,
                "next_run_at": None,
                "schedule_spec": schedule_spec,
            }
        )
        status = str(fields.get("status", current["status"]))
        if status not in ALLOWED_STATUS:
            raise ValueError(f"status must be one of {sorted(ALLOWED_STATUS)}")
        enabled = 1 if status == ACTIVE and fields.get("enabled", current["enabled"]) else 0
        if status in {STOPPED, PAUSED}:
            enabled = 0
        cadence = str(fields.get("cadence", current["cadence"])).strip().lower()
        if cadence not in ALLOWED_CADENCES:
            raise ValueError(f"cadence must be one of {sorted(ALLOWED_CADENCES)}")
        with self._db() as db:
            db.execute(
                """UPDATE discover_refresh_subscriptions
                   SET updated_at=?, intent_id=?, source_id=?, connector_id=?, candidate_key=?,
                       cadence=?, enabled=?, destination=?, status=?, state_json=?
                   WHERE id=?""",
                (
                    _now(),
                    str(fields.get("intent_id", current["intent_id"]) or "")[:64],
                    str(fields.get("source_id", current["source_id"]) or "")[:160],
                    str(fields.get("connector_id", current["connector_id"]) or "")[:160],
                    str(fields.get("candidate_key", current["candidate_key"]) or "")[:320],
                    cadence,
                    enabled,
                    str(fields.get("destination", current["destination"]) or "")[:400],
                    status,
                    json.dumps(_clone(state)),
                    subscription_id,
                ),
            )
        return self.get(subscription_id)

    def pause(self, subscription_id: str) -> dict[str, Any]:
        current = self.get(subscription_id)
        if current["status"] == STOPPED:
            raise ValueError("cannot pause a stopped subscription")
        if current["status"] == PAUSED:
            return current
        state = self._armed_state(
            cadence=current["cadence"],
            status=PAUSED,
            enabled=False,
            requested_schedule=current.get("requested_schedule") or "",
            schedule_note=current.get("schedule_note") or "",
            schedule_spec=current.get("schedule_spec") or {},
            last_run_at=current.get("last_run_at"),
            last_job_id=current.get("last_job_id"),
            clear_next=True,
        )
        state["execution_note"] = "Paused — next run cleared until resume."
        return self._save(subscription_id, status=PAUSED, enabled=False, state_patch=state)

    def resume(self, subscription_id: str) -> dict[str, Any]:
        current = self.get(subscription_id)
        if current["status"] == STOPPED:
            raise ValueError("cannot resume a stopped subscription; create a new one")
        if current["status"] == ACTIVE and current["enabled"]:
            return current
        state = self._armed_state(
            cadence=current["cadence"],
            status=ACTIVE,
            enabled=True,
            requested_schedule=current.get("requested_schedule") or "",
            schedule_note=current.get("schedule_note") or "",
            schedule_spec=current.get("schedule_spec") or {},
            last_run_at=current.get("last_run_at"),
            last_job_id=current.get("last_job_id"),
        )
        return self._save(subscription_id, status=ACTIVE, enabled=True, state_patch=state)

    def stop(self, subscription_id: str) -> dict[str, Any]:
        current = self.get(subscription_id)
        if current["status"] == STOPPED:
            return current
        state = self._armed_state(
            cadence=current["cadence"],
            status=STOPPED,
            enabled=False,
            requested_schedule=current.get("requested_schedule") or "",
            schedule_note=current.get("schedule_note") or "",
            schedule_spec=current.get("schedule_spec") or {},
            last_run_at=current.get("last_run_at"),
            last_job_id=current.get("last_job_id"),
            clear_next=True,
        )
        state["execution_note"] = "Stopped — no further automatic runs."
        return self._save(subscription_id, status=STOPPED, enabled=False, state_patch=state)

    def mark_run(
        self,
        subscription_id: str,
        *,
        job_id: str,
        fired_at: datetime | None = None,
        run_status: str = "submitted",
        run_plan: str = "",
        run_error: str = "",
    ) -> dict[str, Any]:
        """Record a fired refresh and arm the following next_run_at."""
        current = self.get(subscription_id)
        fired = fired_at or datetime.now(UTC)
        stamp = fired.astimezone(UTC).replace(microsecond=0).isoformat()
        state = self._armed_state(
            cadence=current["cadence"],
            status=current["status"],
            enabled=bool(current.get("enabled")),
            requested_schedule=current.get("requested_schedule") or "",
            schedule_note=current.get("schedule_note") or "",
            schedule_spec=current.get("schedule_spec") or {},
            last_run_at=stamp,
            last_job_id=str(job_id or "")[:64] or None,
            after=fired,
        )
        state["last_run_status"] = str(run_status or "submitted")[:32]
        state["last_run_plan"] = str(run_plan or "")[:80] or None
        state["last_run_error"] = str(run_error or "")[:400] or None
        return self._save(subscription_id, state_patch=state)

    def mark_run_outcome(
        self,
        subscription_id: str,
        *,
        job_id: str = "",
        run_status: str,
        run_error: str = "",
    ) -> dict[str, Any]:
        """Update last run outcome without changing next_run_at."""
        current = self.get(subscription_id)
        patch = {
            "last_run_status": str(run_status or "")[:32],
            "last_run_error": str(run_error or "")[:400] or None,
        }
        if job_id:
            patch["last_job_id"] = str(job_id)[:64]
        return self._save(subscription_id, state_patch=patch)

    def rearm(self, subscription_id: str) -> dict[str, Any]:
        """Recompute next_run_at for an active scheduled subscription (no fire)."""
        current = self.get(subscription_id)
        state = self._armed_state(
            cadence=current["cadence"],
            status=current["status"],
            enabled=bool(current.get("enabled")),
            requested_schedule=current.get("requested_schedule") or "",
            schedule_note=current.get("schedule_note") or "",
            schedule_spec=current.get("schedule_spec") or {},
            last_run_at=current.get("last_run_at"),
            last_job_id=current.get("last_job_id"),
        )
        return self._save(subscription_id, state_patch=state)
