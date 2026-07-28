"""Durable, evidence-backed financial source intelligence records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def source_intelligence_store_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/procurement_memory/source_intelligence.sqlite3"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value or {}))


class SourceIntelligenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS research_needs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    title TEXT NOT NULL, spec_json TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS source_offerings (
                    id TEXT PRIMARY KEY, need_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, candidate_key TEXT NOT NULL, title TEXT NOT NULL,
                    offering_json TEXT NOT NULL,
                    UNIQUE(need_id, candidate_key)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS source_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL
                )"""
            )

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_need(self, spec: dict[str, Any]) -> dict[str, Any]:
        body = _clone(spec)
        title = str(body.get("title") or "").strip()
        if not title:
            raise ValueError("research need title is required")
        body["fields"] = [str(value) for value in body.get("fields") or [] if str(value).strip()]
        body["point_in_time_required"] = bool(body.get("point_in_time_required", False))
        need_id = f"need_{uuid.uuid4().hex[:16]}"
        stamp = _now()
        with self._db() as db:
            db.execute(
                "INSERT INTO research_needs VALUES (?, ?, ?, ?, ?)",
                (need_id, stamp, stamp, title[:240], json.dumps(body)),
            )
        return self.get_need(need_id)

    def get_need(self, need_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute(
                "SELECT id, created_at, updated_at, title, spec_json FROM research_needs WHERE id=?", (need_id,)
            ).fetchone()
        if not row:
            raise KeyError(need_id)
        return {
            "id": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "title": row[3],
            "spec": json.loads(row[4] or "{}"),
        }

    def record_offering(self, need_id: str, offering: dict[str, Any]) -> dict[str, Any]:
        self.get_need(need_id)
        body = _clone(offering)
        candidate_key = str(body.get("candidate_key") or "").strip()
        title = str(body.get("title") or "").strip()
        if not candidate_key or not title:
            raise ValueError("offering requires candidate_key and title")
        offering_id = str(body.get("id") or f"offering_{uuid.uuid4().hex[:16]}")
        body["id"] = offering_id
        body.setdefault("coverage", {})
        body.setdefault("fields", [])
        body.setdefault("point_in_time", {"status": "unknown"})
        body.setdefault("access", {"status": "unknown"})
        body.setdefault("evidence", [])
        body.setdefault("decision", {"state": "undecided", "reason": ""})
        stamp = _now()
        with self._db() as db:
            existing = db.execute(
                "SELECT id FROM source_offerings WHERE need_id=? AND candidate_key=?", (need_id, candidate_key)
            ).fetchone()
            if existing:
                offering_id = existing[0]
                body["id"] = offering_id
                db.execute(
                    "UPDATE source_offerings SET updated_at=?, title=?, offering_json=? WHERE id=?",
                    (stamp, title[:240], json.dumps(body), offering_id),
                )
            else:
                db.execute(
                    "INSERT INTO source_offerings VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (offering_id, need_id, stamp, stamp, candidate_key[:320], title[:240], json.dumps(body)),
                )
        return self.get_offering(offering_id)

    def get_offering(self, offering_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute(
                "SELECT id, need_id, created_at, updated_at, candidate_key, title, offering_json "
                "FROM source_offerings WHERE id=?",
                (offering_id,),
            ).fetchone()
        if not row:
            raise KeyError(offering_id)
        body = json.loads(row[6] or "{}")
        body.update(
            {
                "id": row[0],
                "need_id": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "candidate_key": row[4],
                "title": row[5],
            }
        )
        body["reliability"] = self._reliability(row[0])
        return body

    def reject_offering(self, need_id: str, offering_id: str, reason: str) -> dict[str, Any]:
        offering = self.get_offering(offering_id)
        if offering["need_id"] != need_id:
            raise ValueError("offering does not belong to research need")
        offering["decision"] = {"state": "rejected", "reason": str(reason or "")[:1200]}
        return self.record_offering(need_id, offering)

    def select_route(
        self, need_id: str, offering_id: str, *, route: dict[str, Any], rationale: str = ""
    ) -> dict[str, Any]:
        offering = self.get_offering(offering_id)
        if offering["need_id"] != need_id:
            raise ValueError("offering does not belong to research need")
        selected_route = _clone(route)
        kind = str(selected_route.get("kind") or "").strip()
        if not kind:
            raise ValueError("route kind is required")
        offering["decision"] = {
            "state": "selected",
            "route": selected_route,
            "rationale": str(rationale or "")[:1200],
        }
        saved = self.record_offering(need_id, offering)
        with self._db() as db:
            db.execute(
                "INSERT INTO source_feedback(offering_id, created_at, kind, payload_json) VALUES (?, ?, ?, ?)",
                (
                    offering_id,
                    _now(),
                    "route_decision",
                    json.dumps({"route": selected_route, "rationale": str(rationale or "")[:1200]}),
                ),
            )
        return saved

    def link_job(self, need_id: str, offering_id: str, job: dict[str, Any]) -> dict[str, Any]:
        offering = self.get_offering(offering_id)
        if offering["need_id"] != need_id:
            raise ValueError("offering does not belong to research need")
        decision = dict(offering.get("decision") or {})
        if decision.get("state") != "selected":
            raise ValueError("select a route before linking collection")
        job_id = str((job or {}).get("id") or "").strip()
        if not job_id:
            raise ValueError("job id is required")
        decision["collection"] = {
            "job_id": job_id,
            "status": str((job or {}).get("status") or "pending_approval"),
            "linked_at": _now(),
        }
        offering["decision"] = decision
        saved = self.record_offering(need_id, offering)
        with self._db() as db:
            db.execute(
                "INSERT INTO source_feedback(offering_id, created_at, kind, payload_json) VALUES (?, ?, ?, ?)",
                (
                    offering_id,
                    _now(),
                    "collection_linked",
                    json.dumps({"job_id": job_id, "status": decision["collection"]["status"]}),
                ),
            )
        return saved

    def find_offering_id_by_job(self, job_id: str) -> str | None:
        wanted = str(job_id or "").strip()
        if not wanted:
            return None
        with self._db() as db:
            rows = db.execute("SELECT id, offering_json FROM source_offerings").fetchall()
        for offering_id, raw in rows:
            body = json.loads(raw or "{}")
            collection = ((body.get("decision") or {}).get("collection") or {})
            if str(collection.get("job_id") or "") == wanted:
                return str(offering_id)
        return None

    def record_collection_outcome(self, offering_id: str, outcome: dict[str, Any]) -> None:

        self.get_offering(offering_id)
        body = _clone(outcome)
        status = str(body.get("status") or "").strip()
        if status not in {"failed", "registered", "query_ready", "completed_unregistered"}:
            raise ValueError("collection outcome status is invalid")
        body["status"] = status
        body.setdefault("observed_at", _now())
        with self._db() as db:
            db.execute(
                "INSERT INTO source_feedback(offering_id, created_at, kind, payload_json) VALUES (?, ?, ?, ?)",
                (offering_id, _now(), "collection_outcome", json.dumps(body)),
            )

    def shortlist(self, need_id: str) -> dict[str, Any]:
        need = self.get_need(need_id)
        with self._db() as db:
            rows = db.execute("SELECT id FROM source_offerings WHERE need_id=?", (need_id,)).fetchall()
        offerings = [self.get_offering(row[0]) for row in rows]
        for offering in offerings:
            offering["fit"] = self._fit(need["spec"], offering)
            offering["fit_score"] = sum(item["score"] for item in offering["fit"].values())
        offerings.sort(key=lambda row: (row["decision"].get("state") == "rejected", -row["fit_score"], row["title"]))
        return {"need": need, "offerings": offerings}

    def recent_outcomes(self, offering_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT payload_json FROM source_feedback WHERE offering_id=? AND kind='collection_outcome' "
                "ORDER BY id DESC LIMIT ?",
                (offering_id, int(limit)),
            ).fetchall()
        return [json.loads(row[0] or "{}") for row in rows]

    def _reliability(self, offering_id: str) -> dict[str, Any]:

        with self._db() as db:
            rows = db.execute(
                "SELECT payload_json FROM source_feedback WHERE offering_id=? AND kind='collection_outcome' "
                "ORDER BY id DESC LIMIT 10",
                (offering_id,),
            ).fetchall()
        outcomes = [json.loads(row[0]) for row in rows]
        latest_failure = next((item for item in outcomes if item.get("status") == "failed"), None)
        successful = sum(item.get("status") in {"registered", "query_ready"} for item in outcomes)
        return {
            "observed_runs": len(outcomes),
            "successful_runs": successful,
            "recent_failure_reason": str((latest_failure or {}).get("reason") or ""),
            "state": "observed" if outcomes else "unobserved",
        }

    @staticmethod
    def _fit(spec: dict[str, Any], offering: dict[str, Any]) -> dict[str, dict[str, Any]]:
        coverage = offering.get("coverage") or {}
        fields = {str(item).lower() for item in offering.get("fields") or []}
        wanted = {str(item).lower() for item in spec.get("fields") or []}
        field_score = 25 if wanted and wanted.issubset(fields) else 12 if wanted & fields else 0
        market_score = 20 if spec.get("market") and spec.get("market") == coverage.get("market") else 8
        frequency_score = 15 if spec.get("frequency") and spec.get("frequency") == coverage.get("frequency") else 5
        pit = offering.get("point_in_time") or {}
        pit_status = str(pit.get("status") or "unknown")
        pit_score = 20 if pit_status == "verified" else 8 if pit_status == "inferred" else 0
        access = offering.get("access") or {}
        access_status = str(access.get("status") or "unknown")
        access_score = 20 if access_status == "verified" else 8 if access_status == "inferred" else 0
        return {
            "coverage": {"score": market_score + frequency_score, "state": "verified" if coverage else "unknown"},
            "fields": {"score": field_score, "state": "verified" if fields else "unknown"},
            "point_in_time": {"score": pit_score, "state": pit_status},
            "access": {"score": access_score, "state": access_status},
        }
