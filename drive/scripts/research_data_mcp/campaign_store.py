#!/usr/bin/env python3
"""Durable procurement campaigns — multi-phase goals across jobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PHASES = (
    "created",
    "index",
    "research",
    "probe",
    "recommend",
    "awaiting_approval",
    "collecting",
    "ready",
    "failed",
)


class CampaignStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    goal TEXT,
                    phase TEXT,
                    status TEXT,
                    payload_json TEXT,
                    error TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS campaign_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT,
                    created_at TEXT,
                    phase TEXT,
                    message TEXT
                )"""
            )

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def create(self, goal: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        cid = uuid.uuid4().hex[:12]
        stamp = _now()
        body = payload or {}
        with self._db() as db:
            db.execute(
                "INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, stamp, stamp, goal[:4000], "created", "active", json.dumps(body), ""),
            )
        self.event(cid, "created", "Campaign created")
        return self.get(cid)

    def update(self, campaign_id: str, *, phase: str | None = None, status: str | None = None, payload: dict | None = None, error: str = "") -> dict[str, Any]:
        current = self.get(campaign_id)
        new_phase = phase or current.get("phase")
        new_status = status or current.get("status")
        merged = dict(current.get("payload") or {})
        if payload:
            merged.update(payload)
        with self._db() as db:
            db.execute(
                "UPDATE campaigns SET updated_at=?, phase=?, status=?, payload_json=?, error=? WHERE id=?",
                (_now(), new_phase, new_status, json.dumps(merged), error[:2000], campaign_id),
            )
        if phase:
            self.event(campaign_id, new_phase, f"Phase → {new_phase}")
        return self.get(campaign_id)

    def event(self, campaign_id: str, phase: str, message: str) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO campaign_events(campaign_id, created_at, phase, message) VALUES (?, ?, ?, ?)",
                (campaign_id, _now(), phase, message[:2000]),
            )

    def get(self, campaign_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise KeyError(campaign_id)
            events = [
                dict(item)
                for item in db.execute(
                    "SELECT created_at, phase, message FROM campaign_events WHERE campaign_id=? ORDER BY id",
                    (campaign_id,),
                )
            ]
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["events"] = events
        return item

    def list(self, limit: int = 30, status: str = "") -> list[dict[str, Any]]:
        with self._db() as db:
            if status:
                ids = [
                    r[0]
                    for r in db.execute(
                        "SELECT id FROM campaigns WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                        (status, limit),
                    )
                ]
            else:
                ids = [r[0] for r in db.execute("SELECT id FROM campaigns ORDER BY updated_at DESC LIMIT ?", (limit,))]
        return [self.get(cid) for cid in ids]

    def active(self) -> list[dict[str, Any]]:
        with self._db() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM campaigns WHERE status='active' AND phase NOT IN ('ready','failed') ORDER BY updated_at ASC LIMIT 10"
                )
            ]
        return [self.get(cid) for cid in ids]
