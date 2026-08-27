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

from scripts.research_data_mcp.desk_ownership import (
    owner_filter,
    owner_id_for_create,
    require_owner,
)


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
                    state_json TEXT NOT NULL,
                    owner_id TEXT NOT NULL DEFAULT ''
                )"""
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(discover_intents)")}
            if "owner_id" not in columns:
                db.execute(
                    "ALTER TABLE discover_intents ADD COLUMN owner_id TEXT NOT NULL DEFAULT ''"
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

    def _get_locked(self, db: sqlite3.Connection, intent_id: str) -> dict[str, Any]:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM discover_intents WHERE id = ?", (intent_id,)).fetchone()
        if not row:
            raise KeyError(intent_id)
        item = dict(row)
        require_owner(item.get("owner_id"), intent_id)
        item["state"] = json.loads(item.pop("state_json") or "{}")
        return item

    def _save_locked(self, db: sqlite3.Connection, intent_id: str, state: dict[str, Any]) -> None:
        db.execute(
            "UPDATE discover_intents SET updated_at=?, state_json=? WHERE id=?",
            (_now(), json.dumps(_clone(state)), intent_id),
        )

    def _event_locked(
        self,
        db: sqlite3.Connection,
        intent_id: str,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        db.execute(
            "INSERT INTO discover_intent_events(intent_id, created_at, kind, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (intent_id, _now(), kind[:80], json.dumps(payload)),
        )

    @staticmethod
    def _collection_started(state: dict[str, Any]) -> bool:
        collection = dict(state.get("collection") or {})
        status = str(collection.get("status") or "not_started").strip() or "not_started"
        return bool(collection.get("job_id")) or status not in {"not_started"}

    def create(
        self,
        *,
        research_need: str,
        title: str = "",
        candidate: dict[str, Any] | None = None,
        session_id: str = "",
        user_email: str = "",
        owner_id: str = "",
    ) -> dict[str, Any]:
        need = str(research_need or "").strip()
        if not need:
            raise ValueError("research_need is required")
        intent_id = uuid.uuid4().hex[:16]
        stamp = _now()
        name = str(title or "").strip() or need[:120]
        assigned_owner = owner_id_for_create(owner_id)
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
                "INSERT INTO discover_intents("
                "id, created_at, updated_at, title, research_need, session_id, "
                "user_email, state_json, owner_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent_id,
                    stamp,
                    stamp,
                    name[:200],
                    need[:4000],
                    str(session_id or "")[:64],
                    str(user_email or "")[:320],
                    json.dumps(state),
                    assigned_owner,
                ),
            )
        self._event(intent_id, "created", {"candidate_key": state["candidate"].get("candidate_key")})
        return self.get(intent_id)

    def get(self, intent_id: str) -> dict[str, Any]:
        with self._db() as db:
            return self._get_locked(db, intent_id)

    def list(self, *, limit: int = 30, session_id: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 30), 200))
        sql = "SELECT id FROM discover_intents"
        clauses: list[str] = []
        args: tuple[Any, ...] = ()
        owner_clause, owner_args = owner_filter()
        if owner_clause:
            clauses.append(owner_clause)
            args += owner_args
        if session_id:
            clauses.append("session_id = ?")
            args += (session_id,)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
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
            self._event_locked(db, intent_id, kind, payload)

    def set_proposal(self, intent_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        validated = validate_proposal(proposal)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            if self._collection_started(state):
                raise ValueError("cannot replace proposal after collection submission has started")
            # A new proposal supersedes every previously reviewed route. Leaving
            # old routes executable while a replacement is pending lets stale
            # evidence advice cross a consequential authority boundary.
            state["proposal"] = validated
            state["routes"] = []
            state["selected_route_id"] = ""
            state["status"] = "proposal_ready"
            self._save_locked(db, intent_id, state)
            self._event_locked(db, intent_id, "proposal", {"proposal": state["proposal"]})
        return self.get(intent_id)

    def review_proposal(
        self,
        intent_id: str,
        *,
        decision: str,
        proposal_id: str,
        proposal_hash: str,
    ) -> dict[str, Any]:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            if self._collection_started(state):
                raise ValueError("cannot review proposal after collection submission has started")
            if state.get("status") != "proposal_ready":
                raise ValueError("Discover proposal is not ready for review")
            proposal = state.get("proposal") or {}
            if proposal_id != proposal.get("id") or proposal_hash != proposal.get("proposal_hash"):
                raise ValueError("Discover proposal changed; refresh before reviewing")
            normalized = str(decision or "").strip().lower()
            if normalized == "accept":
                state["routes"] = proposal.get("routes") or []
                state["selected_route_id"] = (
                    proposal.get("recommended_route_id") or state["routes"][0]["id"]
                )
                state["proposal"] = None
                state["status"] = "ready_for_review"
            elif normalized == "reject":
                state["proposal"] = None
                state["routes"] = []
                state["selected_route_id"] = ""
                state["status"] = "draft"
            else:
                raise ValueError("decision must be accept or reject")
            self._save_locked(db, intent_id, state)
            self._event_locked(
                db,
                intent_id,
                normalized,
                {"proposal_id": proposal_id, "proposal_hash": proposal_hash},
            )
        return self.get(intent_id)

    def select_route(self, intent_id: str, route_id: str) -> dict[str, Any]:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            if self._collection_started(state):
                raise ValueError("cannot change route after collection submission has started")
            if state.get("status") != "ready_for_review":
                raise ValueError("route selection requires a reviewed Discover proposal")
            ids = {row.get("id") for row in state.get("routes") or []}
            if route_id not in ids:
                raise ValueError("route_id is not part of this Discover intent")
            state["selected_route_id"] = route_id
            self._save_locked(db, intent_id, state)
            self._event_locked(db, intent_id, "route_selected", {"route_id": route_id})
        return self.get(intent_id)

    def reserve_submission(self, intent_id: str) -> dict[str, Any]:
        """Atomically freeze the reviewed route before a queue side effect.

        A retry of the same in-flight reservation is safe: the deterministic
        queue id will deduplicate job creation and `link_job` will finalize it.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            collection = dict(state.get("collection") or {})
            status = str(collection.get("status") or "not_started")

            if state.get("status") == "submitting" and status == "submitting":
                route_id = str(collection.get("route_id") or "")
                if not route_id or route_id != str(state.get("selected_route_id") or ""):
                    raise ValueError("Discover submission reservation is inconsistent")
                return current

            if state.get("status") != "ready_for_review":
                raise ValueError("Discover intent must be reviewed and ready before submission")
            if self._collection_started(state):
                raise ValueError("Discover collection submission has already started")
            selected = str(state.get("selected_route_id") or "")
            route = next(
                (row for row in state.get("routes") or [] if str(row.get("id") or "") == selected),
                None,
            )
            if not selected or not route:
                raise ValueError("select a reviewed acquisition route before collection")

            collection.update({
                "job_id": "",
                "status": "submitting",
                "route_id": selected,
                "registered_dataset_id": str(collection.get("registered_dataset_id") or ""),
            })
            state["collection"] = collection
            state["status"] = "submitting"
            self._save_locked(db, intent_id, state)
            self._event_locked(db, intent_id, "submission_reserved", {"route_id": selected})
        return self.get(intent_id)

    def abort_submission(self, intent_id: str, *, reason: str = "") -> dict[str, Any]:
        """Release an in-flight reservation only when no job has been linked."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            collection = dict(state.get("collection") or {})
            if collection.get("job_id"):
                return current
            if state.get("status") != "submitting" or collection.get("status") != "submitting":
                return current
            collection["status"] = "not_started"
            collection["route_id"] = ""
            state["collection"] = collection
            state["status"] = "ready_for_review"
            self._save_locked(db, intent_id, state)
            self._event_locked(
                db,
                intent_id,
                "submission_aborted",
                {"reason": str(reason or "")[:240]},
            )
        return self.get(intent_id)

    def link_job(self, intent_id: str, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            raise ValueError("collection job id is required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get_locked(db, intent_id)
            state = _clone(current["state"])
            collection = dict(state.get("collection") or {})
            existing_job_id = str(collection.get("job_id") or "").strip()
            if existing_job_id:
                if existing_job_id == job_id:
                    return current
                raise ValueError("Discover intent already has a different collection job")
            route_id = str(collection.get("route_id") or state.get("selected_route_id") or "")
            collection.update({
                "job_id": job_id,
                "status": str(job.get("status") or "pending_approval"),
                "route_id": route_id,
            })
            state["collection"] = collection
            state["status"] = "pending_approval"
            self._save_locked(db, intent_id, state)
            self._event_locked(
                db,
                intent_id,
                "job_linked",
                {"job_id": job_id, "route_id": route_id},
            )
        return self.get(intent_id)

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
