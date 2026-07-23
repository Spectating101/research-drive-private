"""Durable, human-reviewed Discover collection intents.

An intent is the researcher-facing decision record between a Discover candidate
and a collection job.  It deliberately stores no executable code or approval
authority; Composer may create and propose routes, while a desk user chooses a
route and explicitly submits the resulting pending job.
"""

from __future__ import annotations

from contextlib import contextmanager

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Any


def discover_intent_store_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/procurement_memory/discover_intents.sqlite3"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value or {}))


def _proposal_hash(proposal: dict[str, Any]) -> str:
    body = {key: value for key, value in proposal.items() if key != "proposal_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _route(route: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise ValueError("each proposed route must be an object")
    route_id = str(route.get("id") or "").strip()
    title = str(route.get("title") or "").strip()
    if not route_id or not title:
        raise ValueError("each proposed route requires id and title")
    out = {
        "id": route_id[:120],
        "title": title[:240],
        "connector_id": str(route.get("connector_id") or "").strip()[:160],
        "candidate_key": str(route.get("candidate_key") or "").strip()[:320],
        "summary": str(route.get("summary") or "").strip()[:1200],
        "coverage": str(route.get("coverage") or "").strip()[:600],
        "grain": str(route.get("grain") or "").strip()[:240],
        "access": str(route.get("access") or "").strip()[:600],
        "cost": str(route.get("cost") or "").strip()[:600],
        "limitation": str(route.get("limitation") or "").strip()[:1200],
        "destination": str(route.get("destination") or "").strip()[:400],
        "refresh": str(route.get("refresh") or "").strip()[:400],
        "url": str(route.get("url") or route.get("source_url") or "").strip()[:800],
        "pipeline": str(route.get("pipeline") or "").strip()[:80],
    }
    # Executable generic plan stub (AI-crafted). Validated when present.
    raw_plan = route.get("collect_plan")
    if raw_plan is not None:
        from scripts.research_data_mcp.craft_collect import validate_generic_plan

        out["collect_plan"] = validate_generic_plan(raw_plan if isinstance(raw_plan, dict) else None)
        out["crafted"] = True
        out.setdefault("pipeline", "custom")
    return {key: value for key, value in out.items() if value not in ("", [], None)}


def validate_proposal(proposal: dict[str, Any] | None) -> dict[str, Any] | None:
    if proposal is None:
        return None
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    proposal_id = str(proposal.get("id") or "").strip()
    summary = str(proposal.get("summary") or "").strip()
    raw_routes = proposal.get("routes") or []
    if not proposal_id or not summary:
        raise ValueError("proposal requires id and summary")
    if not isinstance(raw_routes, list) or not raw_routes or len(raw_routes) > 8:
        raise ValueError("proposal routes must contain between 1 and 8 routes")
    routes = [_route(row) for row in raw_routes]
    ids = [row["id"] for row in routes]
    if len(ids) != len(set(ids)):
        raise ValueError("proposal route ids must be unique")
    selected = str(proposal.get("recommended_route_id") or "").strip()
    if selected and selected not in ids:
        raise ValueError("recommended_route_id must refer to a proposed route")
    out = {
        "id": proposal_id[:120],
        "summary": summary[:1600],
        "reason": str(proposal.get("reason") or "").strip()[:1600],
        "routes": routes,
        "recommended_route_id": selected,
    }
    out = {key: value for key, value in out.items() if value not in ("", [], None)}
    out["proposal_hash"] = _proposal_hash(out)
    return out


class DiscoverIntentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS discover_intents (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    research_need TEXT NOT NULL,
                    session_id TEXT,
                    user_email TEXT,
                    state_json TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS discover_intent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_discover_intents_updated ON discover_intents(updated_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_discover_intent_events_intent ON discover_intent_events(intent_id, id)")

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
        *,
        research_need: str,
        title: str = "",
        candidate: dict[str, Any] | None = None,
        session_id: str = "",
        user_email: str = "",
    ) -> dict[str, Any]:
        need = str(research_need or "").strip()
        if not need:
            raise ValueError("research_need is required")
        intent_id = uuid.uuid4().hex[:16]
        stamp = _now()
        name = str(title or "").strip() or need[:120]
        state = {
            "status": "draft",
            "candidate": _clone(candidate) if isinstance(candidate, dict) else {},
            "routes": [],
            "selected_route_id": "",
            "proposal": None,
            "collection": {"job_id": "", "status": "not_started", "registered_dataset_id": ""},
        }
        with self._db() as db:
            db.execute(
                "INSERT INTO discover_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (intent_id, stamp, stamp, name[:200], need[:4000], str(session_id or "")[:64], str(user_email or "")[:320], json.dumps(state)),
            )
        self._event(intent_id, "created", {"candidate_key": state["candidate"].get("candidate_key")})
        return self.get(intent_id)

    def get(self, intent_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM discover_intents WHERE id = ?", (intent_id,)).fetchone()
        if not row:
            raise KeyError(intent_id)
        item = dict(row)
        item["state"] = json.loads(item.pop("state_json") or "{}")
        return item

    def list(self, *, limit: int = 30, session_id: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 30), 200))
        sql = "SELECT id FROM discover_intents"
        args: tuple[Any, ...] = ()
        if session_id:
            sql += " WHERE session_id = ?"
            args = (session_id,)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args += (limit,)
        with self._db() as db:
            ids = [row[0] for row in db.execute(sql, args)]
        return [self.get(intent_id) for intent_id in ids]

    def _save(self, intent_id: str, state: dict[str, Any]) -> dict[str, Any]:
        self.get(intent_id)
        with self._db() as db:
            db.execute(
                "UPDATE discover_intents SET updated_at=?, state_json=? WHERE id=?",
                (_now(), json.dumps(_clone(state)), intent_id),
            )
        return self.get(intent_id)

    def _event(self, intent_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO discover_intent_events(intent_id, created_at, kind, payload_json) VALUES (?, ?, ?, ?)",
                (intent_id, _now(), kind[:80], json.dumps(payload)),
            )

    def set_proposal(self, intent_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        current = self.get(intent_id)
        state = _clone(current["state"])
        state["proposal"] = validate_proposal(proposal)
        state["status"] = "proposal_ready"
        out = self._save(intent_id, state)
        self._event(intent_id, "proposal", {"proposal": state["proposal"]})
        return out

    def review_proposal(self, intent_id: str, *, decision: str, proposal_id: str, proposal_hash: str) -> dict[str, Any]:
        current = self.get(intent_id)
        state = _clone(current["state"])
        proposal = state.get("proposal") or {}
        if proposal_id != proposal.get("id") or proposal_hash != proposal.get("proposal_hash"):
            raise ValueError("Discover proposal changed; refresh before reviewing")
        normalized = str(decision or "").strip().lower()
        if normalized == "accept":
            state["routes"] = proposal.get("routes") or []
            state["selected_route_id"] = proposal.get("recommended_route_id") or state["routes"][0]["id"]
            state["proposal"] = None
            state["status"] = "ready_for_review"
        elif normalized == "reject":
            state["proposal"] = None
            state["status"] = "draft"
        else:
            raise ValueError("decision must be accept or reject")
        out = self._save(intent_id, state)
        self._event(intent_id, normalized, {"proposal_id": proposal_id, "proposal_hash": proposal_hash})
        return out

    def select_route(self, intent_id: str, route_id: str) -> dict[str, Any]:
        current = self.get(intent_id)
        state = _clone(current["state"])
        ids = {row.get("id") for row in state.get("routes") or []}
        if route_id not in ids:
            raise ValueError("route_id is not part of this Discover intent")
        if state.get("collection", {}).get("job_id"):
            raise ValueError("cannot change route after collection submission")
        state["selected_route_id"] = route_id
        state["status"] = "ready_for_review"
        out = self._save(intent_id, state)
        self._event(intent_id, "route_selected", {"route_id": route_id})
        return out

    def link_job(self, intent_id: str, job: dict[str, Any]) -> dict[str, Any]:
        current = self.get(intent_id)
        state = _clone(current["state"])
        collection = dict(state.get("collection") or {})
        if collection.get("job_id"):
            raise ValueError("Discover intent already has a collection job")
        collection.update({"job_id": str(job.get("id") or ""), "status": str(job.get("status") or "pending_approval")})
        state["collection"] = collection
        state["status"] = "pending_approval"
        out = self._save(intent_id, state)
        self._event(intent_id, "job_linked", {"job_id": collection["job_id"]})
        return out

    def events(self, intent_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self.get(intent_id)
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, created_at, kind, payload_json FROM discover_intent_events WHERE intent_id=? ORDER BY id DESC LIMIT ?",
                (intent_id, max(1, min(limit, 200))),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            out.append(item)
        return out
