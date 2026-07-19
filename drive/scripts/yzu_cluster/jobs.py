#!/usr/bin/env python3
"""Unified job store for YZU Cluster (agent + worker loop)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class YzuJobStore:
    ACTIVE = {"pending_approval", "queued", "running"}

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT,
                    title TEXT,
                    request_json TEXT,
                    plan_json TEXT,
                    result_json TEXT,
                    error TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    created_at TEXT,
                    level TEXT,
                    message TEXT
                )"""
            )

    def _db(self):
        return sqlite3.connect(self.path, timeout=30)

    def create(
        self,
        title: str,
        request: dict,
        plan: dict,
        *,
        status: str = "pending_approval",
        job_id: str | None = None,
    ) -> dict:
        job_id = job_id or uuid.uuid4().hex[:12]
        stamp = now()
        with self._db() as db:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, stamp, stamp, status, title, json.dumps(request), json.dumps(plan), "{}", ""),
            )
        self.event(job_id, "info", f"Job created ({status})")
        return self.get(job_id)

    def update(self, job_id: str, status: str, result: dict | None = None, error: str = "") -> dict:
        with self._db() as db:
            db.execute(
                "UPDATE jobs SET updated_at=?, status=?, result_json=?, error=? WHERE id=?",
                (now(), status, json.dumps(result or {}), error, job_id),
            )
        return self.get(job_id)

    def event(self, job_id: str, level: str, message: str) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO events(job_id, created_at, level, message) VALUES (?, ?, ?, ?)",
                (job_id, now(), level, message[:2000]),
            )

    def get(self, job_id: str) -> dict:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            events = [
                dict(item)
                for item in db.execute(
                    "SELECT created_at, level, message FROM events WHERE job_id=? ORDER BY id",
                    (job_id,),
                )
            ]
        item = dict(row)
        for field in ("request_json", "plan_json", "result_json"):
            item[field[:-5]] = json.loads(item.pop(field) or "{}")
        item["events"] = events
        return item

    def list(self, limit: int = 30, status: str = "") -> list[dict]:
        with self._db() as db:
            if status:
                ids = [
                    row[0]
                    for row in db.execute(
                        "SELECT id FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                        (status, limit),
                    )
                ]
            else:
                ids = [row[0] for row in db.execute("SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))]
        return [self.get(job_id) for job_id in ids]

    def next_queued(self) -> str | None:
        with self._db() as db:
            row = db.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def has_active(self) -> bool:
        with self._db() as db:
            row = db.execute(
                "SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone()
        return bool(row)

    def status_counts(self, *, recent_days: int = 7) -> dict[str, Any]:
        """Lifetime status totals plus recent/actionable windows.

        Top-level keys stay backward-compatible for /health consumers.
        Nested ``lifetime`` / ``actionable`` / ``semantics`` distinguish
        historical counters from live debt (do not treat failed/cancelled
        totals as current failures).
        """
        base = {
            "pending_approval": 0,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        days = max(1, int(recent_days))
        # ISO cutoff matches store timestamps (…+00:00); avoid SQLite datetime()
        # which uses a space separator and breaks lexicographic compares.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._db() as db:
            for status, n in db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status"):
                if status in base:
                    base[status] = int(n)
            failed_recent = int(
                db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status='failed' AND updated_at >= ?",
                    (cutoff,),
                ).fetchone()[0]
            )
            cancelled_recent = int(
                db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status='cancelled' AND updated_at >= ?",
                    (cutoff,),
                ).fetchone()[0]
            )
            pending_oldest = db.execute(
                "SELECT MIN(created_at) FROM jobs WHERE status='pending_approval'"
            ).fetchone()[0]
            total = int(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

        oldest_age_days: float | None = None
        if pending_oldest:
            try:
                created = datetime.fromisoformat(str(pending_oldest).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                oldest_age_days = round(
                    (datetime.now(timezone.utc) - created).total_seconds() / 86400.0, 1
                )
            except ValueError:
                oldest_age_days = None

        actionable = {
            "pending_approval": base["pending_approval"],
            "queued": base["queued"],
            "running": base["running"],
            "failed_recent_days": days,
            "failed_recent": failed_recent,
            "cancelled_recent": cancelled_recent,
            "pending_oldest_age_days": oldest_age_days,
        }
        return {
            **base,
            "total": total,
            "lifetime": dict(base),
            "actionable": actionable,
            "failed_recent": failed_recent,
            "cancelled_recent": cancelled_recent,
            "recent_days": days,
            "semantics": (
                "pending_approval/queued/running are live; "
                "failed/cancelled are lifetime totals — use failed_recent/"
                "cancelled_recent for actionable debt"
            ),
        }
