from __future__ import annotations

from typing import Any, Iterable, Mapping

from ._interop_common import now_utc, dumps, loads, ids


class RegistryMixin:
    def register(self, run_id: str, *, dataset_id: str, registry_id: str, manifest_id: str,
                 vault_path: str, archive_verified: bool, revision_id: str | None = None,
                 readiness: str = "query_ready", title: str | None = None,
                 verification_state: str = "not_checked", verification_summary: str | None = None,
                 source: Mapping[str, Any] | str | None = None, lineage_inputs: Iterable[Any] | None = None,
                 source_snapshots: Iterable[Any] = (), checksum: str | None = None,
                 method_revision: str | None = None, refresh_policy: str | None = None,
                 last_refreshed_at: str | None = None, next_refresh_at: str | None = None,
                 rows: int | None = None, fields: int | None = None, entities: int | None = None,
                 grain: str | None = None, coverage: str | None = None, at: str | None = None) -> dict[str, Any]:
        if not all((dataset_id, registry_id, manifest_id, vault_path)):
            raise ValueError("dataset_id, registry_id, manifest_id, and vault_path are required")
        if not archive_verified:
            raise ValueError("registered assets require verified archive proof")
        ready = readiness.strip().lower().replace("-", "_")
        if ready not in {"registered", "query_ready"}:
            raise ValueError("invalid readiness")
        row = self._row(run_id)
        declared = loads(row["outputs"], [])
        if declared and dataset_id not in declared:
            raise ValueError("registered dataset_id must match a declared run output")
        at = at or now_utc()
        source_obj = source if isinstance(source, Mapping) else {"label": source} if source else {}
        lineage = ids(lineage_inputs) if lineage_inputs is not None else loads(row["inputs"], [])
        with self.transaction():
            self.db.execute(
                """INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dataset_id) DO UPDATE SET registry_id=excluded.registry_id,revision_id=excluded.revision_id,
                title=excluded.title,readiness=excluded.readiness,verification_state=excluded.verification_state,
                verification_summary=excluded.verification_summary,source=excluded.source,lineage_inputs=excluded.lineage_inputs,
                source_snapshots=excluded.source_snapshots,manifest_id=excluded.manifest_id,checksum=excluded.checksum,
                method_revision=excluded.method_revision,vault_path=excluded.vault_path,archive_verified=excluded.archive_verified,
                refresh_policy=excluded.refresh_policy,last_refreshed_at=excluded.last_refreshed_at,next_refresh_at=excluded.next_refresh_at,
                rows_count=excluded.rows_count,fields_count=excluded.fields_count,entities_count=excluded.entities_count,
                grain=excluded.grain,coverage=excluded.coverage,updated_at=excluded.updated_at""",
                (dataset_id, registry_id, revision_id, title, ready, verification_state, verification_summary,
                 dumps(dict(source_obj)), dumps(lineage), dumps(ids(source_snapshots)), manifest_id, checksum,
                 method_revision, vault_path, 1, refresh_policy, last_refreshed_at, next_refresh_at, 0,
                 rows, fields, entities, grain, coverage, at),
            )
            self.db.execute(
                """UPDATE runs SET stage='registered',outputs=?,manifest_id=?,archive_verified=1,registry_id=?,
                rows_count=COALESCE(?,rows_count),fields_count=COALESCE(?,fields_count),entities_count=COALESCE(?,entities_count),
                finished_at=?,lease_expires_at=NULL,updated_at=? WHERE run_id=?""",
                (dumps([dataset_id]), manifest_id, registry_id, rows, fields, entities, at, at, run_id),
            )
            self._release_resources(run_id)
            self._event(
                run_id, "registered", "registered", at=at, worker_id=row["worker_id"], attempt=row["attempt"],
                payload={
                    "dataset_id": dataset_id, "registry_id": registry_id, "manifest_id": manifest_id,
                    "vault_path": vault_path, "archive_verified": True,
                },
            )
        return self.asset(dataset_id)

    def asset(self, dataset_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM assets WHERE dataset_id=?", (dataset_id,)).fetchone()
        if row is None:
            raise KeyError(dataset_id)
        return {
            "dataset_id": row["dataset_id"], "registry_id": row["registry_id"], "revision_id": row["revision_id"],
            "title": row["title"], "analysis_readiness": row["readiness"],
            "verification": {"state": row["verification_state"], "summary": row["verification_summary"]},
            "source": loads(row["source"], {}),
            "lineage": {
                "inputs": loads(row["lineage_inputs"], []),
                "source_snapshots": loads(row["source_snapshots"], []),
            },
            "manifest_id": row["manifest_id"], "checksum": row["checksum"],
            "method_revision": row["method_revision"], "vault_path": row["vault_path"],
            "drive_verified": bool(row["archive_verified"]), "refresh_policy": row["refresh_policy"],
            "last_refreshed_at": row["last_refreshed_at"], "next_refresh_at": row["next_refresh_at"],
            "stale": bool(row["stale"]), "row_count": row["rows_count"],
            "field_count": row["fields_count"], "entity_count": row["entities_count"],
            "grain": row["grain"], "coverage": row["coverage"], "updated_at": row["updated_at"],
        }

    def snapshot(self, run_id: str) -> dict[str, Any]:
        row = self._row(run_id)
        progress = None
        if row["progress_current"] is not None or row["progress_total"] is not None:
            progress = {
                key: value
                for key, value in (("current", row["progress_current"]), ("total", row["progress_total"]))
                if value is not None
            }
        worker = self.worker(row["worker_id"]) if row["worker_id"] else None
        events = [
            {
                "event_type": event["event_type"], "stage": event["stage"], "timestamp": event["timestamp"],
                "worker_id": event["worker_id"], "attempt": event["attempt"], "message": event["message"],
                **loads(event["payload"], {}),
            }
            for event in self.db.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY event_id", (run_id,)
            ).fetchall()
        ]
        inputs_, outputs_ = loads(row["inputs"], []), loads(row["outputs"], [])
        resource_requirements = self.requirements(run_id)
        reservation = self.reservation(run_id) if hasattr(self, "reservation") else None
        usage = self.usage(run_id) if hasattr(self, "usage") else None
        result = {
            "id": row["job_id"], "run_id": row["run_id"], "type": row["job_type"], "name": row["title"],
            "status": row["stage"], "attempt": row["attempt"], "max_attempts": row["max_attempts"],
            "retryable": bool(row["retryable"]),
            "required_capabilities": loads(row["required_capabilities"], []),
            "resource_requirements": resource_requirements,
            "resource_reservation": reservation,
            "usage": usage,
            "assigned_worker": worker, "worker_pool": row["pool"], "lease_expires_at": row["lease_expires_at"],
            "progress": progress, "inputs": inputs_, "outputs": outputs_, "manifest_id": row["manifest_id"],
            "drive_verified": bool(row["archive_verified"]), "registration_id": row["registry_id"],
            "rows": row["rows_count"], "field_count": row["fields_count"], "entity_count": row["entities_count"],
            "error": row["error"], "created_at": row["created_at"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "updated_at": row["updated_at"],
        }
        result["lifecycle"] = {
            "stage": row["stage"], "progress": progress, "worker": worker, "attempt": row["attempt"],
            "inputs": inputs_, "outputs": outputs_, "events": events, "run_id": row["run_id"],
            "started_at": row["started_at"], "finished_at": row["finished_at"],
        }
        result["execution"] = {
            "run_id": row["run_id"], "stage": row["stage"], "worker": worker, "pool": row["pool"],
            "attempt": row["attempt"], "manifest_id": row["manifest_id"],
            "archive_verified": bool(row["archive_verified"]), "registry_id": row["registry_id"],
            "rows": row["rows_count"], "fields": row["fields_count"], "entities": row["entities_count"],
            "error": row["error"], "resources": resource_requirements, "usage": usage,
        }
        return result

    def active(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """SELECT run_id FROM runs WHERE stage NOT IN('completed','registered') ORDER BY
            CASE stage WHEN 'failed' THEN 0 WHEN 'blocked' THEN 0 WHEN 'pending_approval' THEN 0 WHEN 'running' THEN 1
            WHEN 'validating' THEN 1 WHEN 'archiving' THEN 1 WHEN 'registering' THEN 1 WHEN 'assigned' THEN 2
            WHEN 'retrying' THEN 2 WHEN 'queued' THEN 3 ELSE 9 END,updated_at DESC LIMIT ?""",
            (max(0, limit),),
        ).fetchall()
        return [self.snapshot(row["run_id"]) for row in rows]
