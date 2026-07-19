"""Framework-neutral API facade for the YZU interoperability store."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from ._interop_common import normalize_capabilities
from .interop_contract import InteropStore

JOB_CAPABILITIES = {
    "archive_upload": ["archive"],
    "collect_manifest": ["http"],
    "harvest_shard": ["http"],
    "http_manifest": ["http"],
    "pipeline": ["pipeline", "python"],
    "registered_pipeline": ["pipeline", "python"],
    "scraper_run": ["browser"],
}


def _required(payload: Mapping[str, Any]) -> list[str]:
    defaults = JOB_CAPABILITIES.get(str(payload.get("type") or payload.get("job_type") or "").lower(), [])
    explicit = payload.get("required_capabilities") or payload.get("capabilities") or []
    return normalize_capabilities([*defaults, *explicit])


def _attempt(payload: Mapping[str, Any]) -> int | None:
    value = payload.get("attempt", payload.get("expected_attempt"))
    return int(value) if value is not None else None


class InteropAPI:
    """Methods map directly onto thin HTTP route handlers."""

    def __init__(self, store: InteropStore) -> None:
        self.store = store

    def submit_job(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("id") or payload.get("job_id") or "").strip()
        job_type = str(payload.get("type") or payload.get("job_type") or "").strip()
        job = self.store.submit(
            job_id=job_id,
            job_type=job_type,
            title=payload.get("title") or (payload.get("plan") or {}).get("title"),
            required_capabilities=_required(payload),
            inputs=payload.get("inputs") or [],
            outputs=payload.get("outputs") or [],
            pending_approval=bool(payload.get("pending_approval") or payload.get("approval_required")),
            max_attempts=int(payload.get("max_attempts") or 3),
            retryable=payload.get("retryable") is not False,
            resource_requirements=payload.get("resource_requirements") or payload.get("resources"),
            run_id=payload.get("run_id"),
        )
        return {"job": job}

    def approve_job(self, run_id: str) -> dict[str, Any]:
        return {"job": self.store.approve(run_id)}

    def upsert_connector(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {"connector": self.store.upsert_connector(payload)}

    def connector(self, connector_id: str) -> dict[str, Any]:
        return {"connector": self.store.connector(connector_id)}

    def connectors(self) -> dict[str, Any]:
        return {"connectors": self.store.list_connectors()}

    def record_connector_probe(self, connector_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {"connector": self.store.record_probe(connector_id, payload)}

    def record_connector_sync(self, connector_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "connector": self.store.record_sync(
                connector_id,
                state_token=payload.get("state_token") or payload.get("cursor"),
                last_synced_at=payload.get("last_synced_at") or payload.get("timestamp"),
                quota_remaining=payload.get("quota_remaining"),
            )
        }

    def join_worker(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("id") or payload.get("worker_id") or "").strip()
        worker = self.store.upsert_worker(
            worker_id,
            pool=payload.get("pool") or payload.get("worker_pool"),
            status=str(payload.get("status") or "online"),
            capabilities=payload.get("capabilities") or [],
            capacity=payload.get("capacity") or {},
            heartbeat_at=payload.get("heartbeat_at"),
        )
        return {"worker": worker}

    def claim_job(self, worker_id: str, *, lease_seconds: int = 120, at: str | None = None) -> dict[str, Any]:
        claim = self.store.claim(worker_id, lease_seconds=lease_seconds, at=at)
        return {"job": self.store.snapshot(claim.run_id) if claim else None}

    def heartbeat(self, run_id: str, worker_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        progress = payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {}
        job = self.store.heartbeat(
            run_id,
            worker_id,
            lease_seconds=int(payload.get("lease_seconds") or 120),
            current=progress.get("current", payload.get("progress_current")),
            total=progress.get("total", payload.get("progress_total")),
            next_stage=payload.get("stage"),
            at=payload.get("timestamp") or payload.get("at"),
            expected_attempt=_attempt(payload),
        )
        return {"job": job}

    def record_event(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        progress = payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {}
        job = self.store.record(
            run_id,
            str(payload.get("stage") or payload.get("event_type") or "unknown"),
            event_type=payload.get("event_type"),
            worker_id=payload.get("worker_id"),
            current=progress.get("current", payload.get("progress_current")),
            total=progress.get("total", payload.get("progress_total")),
            outputs=payload.get("outputs"),
            manifest_id=payload.get("manifest_id"),
            archive_verified=payload.get("archive_verified", payload.get("drive_verified")),
            registry_id=payload.get("registry_id") or payload.get("registration_id"),
            rows=payload.get("rows") or payload.get("row_count"),
            fields=payload.get("fields") or payload.get("field_count"),
            entities=payload.get("entities") or payload.get("entity_count"),
            error=payload.get("error"),
            retryable=payload.get("retryable"),
            message=payload.get("message"),
            payload=payload.get("detail") if isinstance(payload.get("detail"), Mapping) else None,
            at=payload.get("timestamp") or payload.get("at"),
            expected_attempt=_attempt(payload),
        )
        return {"job": job}

    def retry_job(self, run_id: str, *, at: str | None = None) -> dict[str, Any]:
        return {"job": self.store.retry(run_id, at=at)}

    def reap_expired(self, *, at: str | None = None) -> dict[str, Any]:
        return {"requeued_or_failed": self.store.reap_expired(at=at)}

    def record_usage(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "usage": self.store.record_usage(
                run_id,
                worker_id=payload.get("worker_id"),
                cpu_seconds=payload.get("cpu_seconds"),
                memory_peak_mb=payload.get("memory_peak_mb"),
                disk_written_mb=payload.get("disk_written_mb"),
                network_bytes=payload.get("network_bytes"),
                api_calls=payload.get("api_calls"),
                storage_bytes=payload.get("storage_bytes"),
                at=payload.get("timestamp") or payload.get("at"),
                expected_attempt=_attempt(payload),
            )
        }

    def register_output(self, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        asset = self.store.register(
            run_id,
            dataset_id=str(payload.get("dataset_id") or payload.get("output_dataset_id") or ""),
            registry_id=str(payload.get("registry_id") or payload.get("registration_id") or ""),
            revision_id=payload.get("revision_id"),
            manifest_id=str(payload.get("manifest_id") or ""),
            vault_path=str(payload.get("vault_path") or payload.get("gdrive_path") or ""),
            archive_verified=bool(payload.get("archive_verified") or payload.get("drive_verified")),
            readiness=str(payload.get("readiness") or payload.get("analysis_readiness") or "query_ready"),
            title=payload.get("title") or payload.get("name"),
            verification_state=str(payload.get("verification_state") or "not_checked"),
            verification_summary=payload.get("verification_summary"),
            source=payload.get("source"),
            lineage_inputs=payload.get("lineage_inputs") or payload.get("inputs"),
            source_snapshots=payload.get("source_snapshots") or [],
            checksum=payload.get("checksum"),
            method_revision=payload.get("method_revision"),
            refresh_policy=payload.get("refresh_policy"),
            last_refreshed_at=payload.get("last_refreshed_at"),
            next_refresh_at=payload.get("next_refresh_at"),
            rows=payload.get("rows") or payload.get("row_count"),
            fields=payload.get("fields") or payload.get("field_count"),
            entities=payload.get("entities") or payload.get("entity_count"),
            grain=payload.get("grain"),
            coverage=payload.get("coverage"),
            at=payload.get("timestamp") or payload.get("at"),
            expected_attempt=_attempt(payload),
        )
        return {"asset": asset, "job": self.store.snapshot(run_id)}

    def jobs(self, *, limit: int = 100) -> dict[str, Any]:
        return {"jobs": self.store.active(limit=limit)}

    def health(self) -> dict[str, Any]:
        workers = [
            self.store.worker(row["worker_id"])
            for row in self.store.db.execute("SELECT worker_id FROM workers ORDER BY worker_id")
        ]
        stages = Counter(row["stage"] for row in self.store.db.execute("SELECT stage FROM runs"))
        pool_counts: dict[str, dict[str, int]] = {}
        for worker in workers:
            pool = worker.get("pool") or "unassigned"
            pool_counts.setdefault(pool, {"total": 0, "online": 0, "stale": 0})
            pool_counts[pool]["total"] += 1
            if worker.get("status") in {"online", "ready", "idle"}:
                pool_counts[pool]["online"] += 1
            elif worker.get("status") == "stale":
                pool_counts[pool]["stale"] += 1
        active = sum(count for state, count in stages.items() if state not in {"completed", "registered"})
        connectors = self.store.list_connectors()
        access_counts = Counter(item["access_state"] for item in connectors)
        resources = self.store.resources_rollup()
        busy = sum(
            1
            for _row in self.store.db.execute(
                "SELECT DISTINCT worker_id FROM runs WHERE worker_id IS NOT NULL "
                "AND stage NOT IN('completed','registered','failed','blocked')"
            )
        )
        return {
            "cluster": {
                "workers": resources["workers"], "worker_pools": pool_counts, "usage": resources["usage"],
            },
            "desk": {
                "connectors": {"total": len(connectors), **dict(access_counts)},
                "jobs": {"active": active, **dict(stages)},
                "worker_pools": {
                    "total": len(workers),
                    "busy": busy,
                    "stale": sum(1 for worker in workers if worker.get("status") == "stale"),
                },
            },
        }
