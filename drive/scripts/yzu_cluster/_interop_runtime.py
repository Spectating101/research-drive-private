from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from ._interop_common import TERMINAL, now_utc, parse_time, stage, dumps, ids


class RuntimeMixin:
    def heartbeat(self, run_id: str, worker_id: str, *, lease_seconds: int = 120,
                  current: float | None = None, total: float | None = None,
                  next_stage: str | None = None, at: str | None = None) -> dict[str, Any]:
        at = at or now_utc()
        row = self._row(run_id)
        if row["worker_id"] != worker_id:
            raise PermissionError("worker does not own run")
        if row["stage"] in TERMINAL:
            raise ValueError("cannot heartbeat terminal run")
        state = stage(next_stage or row["stage"])
        self._transition(row["stage"], state)
        if total is not None and total <= 0:
            raise ValueError("progress total must be positive")
        expiry = (
            (parse_time(at) or datetime.now(timezone.utc)) + timedelta(seconds=lease_seconds)
        ).isoformat().replace("+00:00", "Z")
        with self.transaction():
            self.db.execute(
                """UPDATE runs SET stage=?,lease_expires_at=?,progress_current=COALESCE(?,progress_current),
                progress_total=COALESCE(?,progress_total),started_at=COALESCE(started_at,?),updated_at=? WHERE run_id=?""",
                (state, expiry, current, total, at if state == "running" else None, at, run_id),
            )
            self.db.execute(
                "UPDATE workers SET heartbeat_at=?,updated_at=?,status='online' WHERE worker_id=?",
                (at, at, worker_id),
            )
            self._event(
                run_id, state, state if next_stage else "heartbeat", at=at, worker_id=worker_id,
                attempt=row["attempt"],
                payload={"lease_expires_at": expiry, "progress": {"current": current, "total": total}},
            )
        return self.snapshot(run_id)

    def record(self, run_id: str, next_stage: str, *, event_type: str | None = None,
               worker_id: str | None = None, current: float | None = None, total: float | None = None,
               outputs: Iterable[Any] | None = None, manifest_id: str | None = None,
               archive_verified: bool | None = None, registry_id: str | None = None,
               rows: int | None = None, fields: int | None = None, entities: int | None = None,
               error: str | None = None, retryable: bool | None = None, message: str | None = None,
               payload: Mapping[str, Any] | None = None, at: str | None = None) -> dict[str, Any]:
        at = at or now_utc()
        state = stage(next_stage)
        row = self._row(run_id)
        self._transition(row["stage"], state)
        if worker_id and row["worker_id"] not in (None, worker_id):
            raise PermissionError("worker does not own run")
        if total is not None and total <= 0:
            raise ValueError("progress total must be positive")
        finished = at if state in TERMINAL else None
        with self.transaction():
            self.db.execute(
                """UPDATE runs SET stage=?,progress_current=COALESCE(?,progress_current),progress_total=COALESCE(?,progress_total),
                outputs=COALESCE(?,outputs),manifest_id=COALESCE(?,manifest_id),archive_verified=COALESCE(?,archive_verified),
                registry_id=COALESCE(?,registry_id),rows_count=COALESCE(?,rows_count),fields_count=COALESCE(?,fields_count),
                entities_count=COALESCE(?,entities_count),error=COALESCE(?,error),retryable=COALESCE(?,retryable),
                started_at=COALESCE(started_at,?),finished_at=COALESCE(?,finished_at),
                lease_expires_at=CASE WHEN ? THEN NULL ELSE lease_expires_at END,updated_at=? WHERE run_id=?""",
                (state, current, total, dumps(ids(outputs)) if outputs is not None else None, manifest_id,
                 int(archive_verified) if archive_verified is not None else None, registry_id, rows, fields, entities, error,
                 int(retryable) if retryable is not None else None, at if state == "running" else None, finished,
                 int(state in TERMINAL), at, run_id),
            )
            if state in TERMINAL:
                self._release_resources(run_id)
            self._event(
                run_id, state, event_type or state, at=at, worker_id=worker_id or row["worker_id"],
                attempt=row["attempt"], message=message, payload=payload,
            )
        return self.snapshot(run_id)

    def retry(self, run_id: str, *, at: str | None = None) -> dict[str, Any]:
        row = self._row(run_id)
        if row["stage"] not in {"failed", "blocked"}:
            raise ValueError("only failed or blocked runs may retry")
        if not row["retryable"] or row["attempt"] >= row["max_attempts"]:
            raise ValueError("run is not retryable")
        at = at or now_utc()
        with self.transaction():
            self._release_resources(run_id)
            self.db.execute(
                "UPDATE runs SET stage='retrying',worker_id=NULL,pool=NULL,lease_expires_at=NULL,error=NULL,finished_at=NULL,updated_at=? WHERE run_id=?",
                (at, run_id),
            )
            self._event(run_id, "retrying", "retrying", at=at, attempt=row["attempt"])
        return self.snapshot(run_id)

    def reap_expired(self, *, at: str | None = None) -> list[str]:
        at = at or now_utc()
        when = parse_time(at) or datetime.now(timezone.utc)
        rows = self.db.execute(
            "SELECT * FROM runs WHERE stage IN('assigned','running','validating','archiving','registering') "
            "AND lease_expires_at IS NOT NULL"
        ).fetchall()
        expired = [row for row in rows if (parse_time(row["lease_expires_at"]) or when) <= when]
        for row in expired:
            state_ = "retrying" if row["retryable"] and row["attempt"] < row["max_attempts"] else "failed"
            with self.transaction():
                self._release_resources(row["run_id"])
                self.db.execute(
                    """UPDATE runs SET stage=?,worker_id=NULL,pool=NULL,lease_expires_at=NULL,error='worker lease expired',
                    finished_at=CASE WHEN ?='failed' THEN ? ELSE NULL END,updated_at=? WHERE run_id=?""",
                    (state_, state_, at, at, row["run_id"]),
                )
                self._event(
                    row["run_id"], state_, "lease_expired", at=at, worker_id=row["worker_id"],
                    attempt=row["attempt"], message="worker lease expired",
                )
        return [row["run_id"] for row in expired]
