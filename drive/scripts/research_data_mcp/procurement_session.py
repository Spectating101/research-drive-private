#!/usr/bin/env python3
"""Server-side procurement chat sessions — transcript + candidate state."""

from __future__ import annotations

from contextlib import contextmanager

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ProcurementSessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    title TEXT,
                    state_json TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    created_at TEXT,
                    role TEXT,
                    content TEXT,
                    artifacts_json TEXT
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")

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

    def create(self, *, title: str = "") -> dict[str, Any]:
        sid = uuid.uuid4().hex[:16]
        stamp = _now()
        with self._db() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (sid, stamp, stamp, title[:200], json.dumps(self._empty_state())),
            )
        return self.get(sid)

    def get(self, session_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        item = dict(row)
        item["state"] = json.loads(item.pop("state_json") or "{}")
        return item

    def get_or_create(self, session_id: str | None) -> dict[str, Any]:
        if session_id:
            try:
                return self.get(session_id)
            except KeyError:
                pass
        return self.create()

    def update_state(self, session_id: str, state: dict[str, Any], *, title: str = "") -> dict[str, Any]:
        stamp = _now()
        with self._db() as db:
            if title:
                db.execute(
                    "UPDATE sessions SET updated_at = ?, state_json = ?, title = ? WHERE id = ?",
                    (stamp, json.dumps(state), title[:200], session_id),
                )
            else:
                db.execute(
                    "UPDATE sessions SET updated_at = ?, state_json = ? WHERE id = ?",
                    (stamp, json.dumps(state), session_id),
                )
        return self.get(session_id)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._db() as db:
            db.execute(
                "INSERT INTO messages(session_id, created_at, role, content, artifacts_json) VALUES (?, ?, ?, ?, ?)",
                (session_id, _now(), role, content[:8000], json.dumps(artifacts or {})),
            )
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
        return {"role": role, "content": content, "artifacts": artifacts or {}}

    def messages(self, session_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT role, content, artifacts_json, created_at FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for row in reversed(rows):
            item = dict(row)
            item["artifacts"] = json.loads(item.pop("artifacts_json") or "{}")
            out.append(item)
        return out

    def transcript_for_llm(self, session_id: str, *, limit: int = 24) -> list[dict[str, str]]:
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages(session_id, limit=limit)
            if m["role"] in {"user", "assistant"}
        ]

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "candidates": [],
            "selected_index": None,
            "last_search_query": "",
            "campaign_id": None,
            "last_handle": None,
        }
