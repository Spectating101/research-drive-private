#!/usr/bin/env python3
"""Unified job store for YZU Cluster (agent + worker loop)."""

from __future__ import annotations

from contextlib import contextmanager

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()



def _failure_bucket(title: str, error: str) -> str:
    blob = f"{title} {error}".lower()
    if any(x in blob for x in ("canary", "smoke", "probe-controller", "windows claim procure")):
        return "ops_canary"
    if "discover refresh twse" in blob or "twse_official" in blob:
        return "discover_spam"
    if "no artifact zip" in blob:
        return "collect_no_artifact"
    if "importerror" in blob or "modulenotfound" in blob:
        return "code_bug"
    if "no downloadable items" in blob:
        return "bad_manifest"
    return "other"


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

    def set_plan(self, job_id: str, plan: dict) -> dict:
        """Replace the stored plan (used after approve-time revalidation)."""
        with self._db() as db:
            db.execute(
                "UPDATE jobs SET updated_at=?, plan_json=? WHERE id=?",
                (now(), json.dumps(plan or {}), job_id),
            )
        return self.get(job_id)

    def update(
        self,
        job_id: str,
        status: str,
        result: dict | None = None,
        error: str = "",
        *,
        expected_status: str | None = None,
    ) -> dict:
        """Update one legacy projection, optionally using optimistic fencing.

        Runtime reconciliation runs in a separate process from the worker-control
        server. A stale reconciliation must not overwrite a completion payload
        committed after the reconciliation read the job.
        """
        where = "WHERE id=?"
        params: list[object] = [now(), status, json.dumps(result or {}), error, job_id]
        if expected_status is not None:
            where += " AND status=?"
            params.append(expected_status)
        with self._db() as db:
            db.execute(
                f"UPDATE jobs SET updated_at=?, status=?, result_json=?, error=? {where}",
                tuple(params),
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
            failed_rows = db.execute(
                "SELECT title, COALESCE(error, '') FROM jobs WHERE status='failed' AND updated_at >= ?",
                (cutoff,),
            ).fetchall()
            buckets: dict[str, int] = {}
            for title, error in failed_rows:
                bucket = _failure_bucket(str(title or ""), str(error or ""))
                buckets[bucket] = buckets.get(bucket, 0) + 1
            ops_noise = int(buckets.get("ops_canary", 0) + buckets.get("discover_spam", 0))
            failed_actionable = max(0, failed_recent - ops_noise)
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
            "failed_actionable": failed_actionable,
            "failed_ops_noise": ops_noise,
            "failed_buckets": buckets,
            "cancelled_recent": cancelled_recent,
            "pending_oldest_age_days": oldest_age_days,
        }
        return {
            **base,
            "total": total,
            "lifetime": dict(base),
            "actionable": actionable,
            "failed_recent": failed_recent,
            "failed_actionable": failed_actionable,
            "failed_ops_noise": ops_noise,
            "failed_buckets": buckets,
            "cancelled_recent": cancelled_recent,
            "recent_days": days,
            "semantics": (
                "pending_approval/queued/running are live; "
                "failed/cancelled are lifetime totals — use failed_actionable "
                "(excludes canary/discover spam) for desk debt"
            ),
        }
