#!/usr/bin/env python3
"""Procurement memory — goals, outcomes, and negative cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_hash(goal: str) -> str:
    return hashlib.sha256(goal.strip().lower().encode("utf-8")).hexdigest()[:16]


class ProcurementMemory:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_hash TEXT,
                    goal TEXT,
                    created_at TEXT,
                    verdict TEXT,
                    phase TEXT,
                    index_miss INTEGER,
                    advice_json TEXT,
                    research_json TEXT,
                    probe_urls_json TEXT,
                    promoted_json TEXT,
                    notes TEXT
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_goal_hash ON entries(goal_hash)")

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def remember_campaign(self, *, goal: str, payload: dict[str, Any]) -> int:
        with self._db() as db:
            cur = db.execute(
                """INSERT INTO entries(goal_hash, goal, created_at, verdict, phase, index_miss,
                   advice_json, research_json, probe_urls_json, promoted_json, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _goal_hash(goal),
                    goal[:2000],
                    _now(),
                    str(payload.get("verdict") or ""),
                    str(payload.get("phase") or ""),
                    1 if payload.get("index_miss") else 0,
                    json.dumps(payload.get("advice") or {}, ensure_ascii=False),
                    json.dumps(payload.get("research_plan") or {}, ensure_ascii=False),
                    json.dumps(payload.get("probe_urls") or [], ensure_ascii=False),
                    json.dumps(payload.get("promoted") or [], ensure_ascii=False),
                    str(payload.get("summary") or "")[:4000],
                ),
            )
            return int(cur.lastrowid)

    def similar(self, goal: str, *, limit: int = 5) -> list[dict[str, Any]]:
        gh = _goal_hash(goal)
        tokens = {t for t in goal.lower().split() if len(t) > 3}
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM entries ORDER BY id DESC LIMIT 200",
            ).fetchall()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            if item.get("goal_hash") == gh:
                scored.append((10.0, item))
                continue
            past_tokens = set(str(item.get("goal") or "").lower().split())
            overlap = len(tokens & past_tokens)
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        out: list[dict[str, Any]] = []
        for _score, item in scored[:limit]:
            item["advice"] = json.loads(item.pop("advice_json") or "{}")
            item["research_plan"] = json.loads(item.pop("research_json") or "{}")
            item["probe_urls"] = json.loads(item.pop("probe_urls_json") or "[]")
            item["promoted"] = json.loads(item.pop("promoted_json") or "[]")
            out.append(item)
        return out

    def cached_verdict(self, goal: str, *, ttl_hours: int = 168) -> dict[str, Any] | None:
        similar = self.similar(goal, limit=3)
        if not similar:
            return None
        top = similar[0]
        try:
            created = datetime.fromisoformat(str(top.get("created_at")))
            age_h = (datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age_h > ttl_hours:
                return None
        except Exception:
            pass
        return {
            "from_memory": True,
            "verdict": top.get("verdict"),
            "phase": top.get("phase"),
            "index_miss": bool(top.get("index_miss")),
            "summary": top.get("notes"),
            "probe_urls": top.get("probe_urls") or [],
            "research_plan": top.get("research_plan") or {},
        }
