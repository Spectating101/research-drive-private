"""Lease-aware worker runner for the YZU interoperability store."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ._interop_common import Claim
from .interop_contract import InteropStore

Handler = Callable[["JobContext"], Mapping[str, Any] | None]


@dataclass
class JobContext:
    store: InteropStore
    claim: Claim
    lease_seconds: int

    def heartbeat(self, *, current: float | None = None, total: float | None = None,
                  stage: str | None = None, at: str | None = None) -> dict[str, Any]:
        return self.store.heartbeat(
            self.claim.run_id,
            self.claim.worker_id,
            lease_seconds=self.lease_seconds,
            current=current,
            total=total,
            next_stage=stage,
            at=at,
            expected_attempt=self.claim.attempt,
        )

    def usage(self, **values: Any) -> dict[str, Any]:
        return self.store.record_usage(
            self.claim.run_id,
            worker_id=self.claim.worker_id,
            expected_attempt=self.claim.attempt,
            **values,
        )


class WorkerRunner:
    def __init__(self, store: InteropStore, worker_id: str, handlers: Mapping[str, Handler], *, lease_seconds: int = 120) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.store = store
        self.worker_id = worker_id
        self.handlers = dict(handlers)
        self.lease_seconds = lease_seconds

    def run_once(self, *, at: str | None = None) -> dict[str, Any] | None:
        claim = self.store.claim(self.worker_id, lease_seconds=self.lease_seconds, at=at)
        if claim is None:
            return None
        handler = self.handlers.get(claim.job_type)
        if handler is None:
            return self.store.record(
                claim.run_id,
                "blocked",
                worker_id=self.worker_id,
                error=f"unsupported job type: {claim.job_type}",
                retryable=False,
                message="No worker handler is registered for this job type.",
                at=at,
                expected_attempt=claim.attempt,
            )

        context = JobContext(self.store, claim, self.lease_seconds)
        context.heartbeat(stage="running", at=at)
        try:
            result = dict(handler(context) or {})
        except Exception as exc:
            return self.store.record(
                claim.run_id,
                "failed",
                worker_id=self.worker_id,
                error=f"{type(exc).__name__}: {exc}",
                retryable=True,
                at=at,
                expected_attempt=claim.attempt,
            )

        usage = result.get("usage")
        if isinstance(usage, Mapping):
            self.store.record_usage(
                claim.run_id,
                worker_id=self.worker_id,
                cpu_seconds=usage.get("cpu_seconds"),
                memory_peak_mb=usage.get("memory_peak_mb"),
                disk_written_mb=usage.get("disk_written_mb"),
                network_bytes=usage.get("network_bytes"),
                api_calls=usage.get("api_calls"),
                storage_bytes=usage.get("storage_bytes"),
                at=usage.get("timestamp") or at,
                expected_attempt=claim.attempt,
            )

        progress = result.get("progress") if isinstance(result.get("progress"), Mapping) else {}
        completed = self.store.record(
            claim.run_id,
            str(result.get("stage") or "completed"),
            worker_id=self.worker_id,
            current=progress.get("current"),
            total=progress.get("total"),
            outputs=result.get("outputs") or claim.outputs,
            manifest_id=result.get("manifest_id"),
            archive_verified=result.get("archive_verified", result.get("drive_verified")),
            rows=result.get("rows") or result.get("row_count"),
            fields=result.get("fields") or result.get("field_count"),
            entities=result.get("entities") or result.get("entity_count"),
            error=result.get("error"),
            retryable=result.get("retryable"),
            message=result.get("message"),
            payload=result.get("detail") if isinstance(result.get("detail"), Mapping) else None,
            at=at,
            expected_attempt=claim.attempt,
        )

        connector_state = None
        connector_probe = result.get("connector_probe")
        if isinstance(connector_probe, Mapping):
            connector_id = str(
                connector_probe.get("connector_id") or connector_probe.get("source_id") or ""
            ).strip()
            if not connector_id:
                raise ValueError("connector_probe requires connector_id")
            connector_state = self.store.record_probe(connector_id, connector_probe)

        connector_sync = result.get("connector_sync")
        if isinstance(connector_sync, Mapping):
            connector_id = str(
                connector_sync.get("connector_id") or connector_sync.get("source_id") or ""
            ).strip()
            if not connector_id:
                raise ValueError("connector_sync requires connector_id")
            connector_state = self.store.record_sync(
                connector_id,
                state_token=connector_sync.get("state_token") or connector_sync.get("cursor"),
                last_synced_at=connector_sync.get("last_synced_at") or connector_sync.get("timestamp"),
                quota_remaining=connector_sync.get("quota_remaining"),
            )

        registration = result.get("registration")
        if not isinstance(registration, Mapping):
            if connector_state is not None:
                completed["connector"] = connector_state
            return completed

        dataset_id = str(registration.get("dataset_id") or (completed.get("outputs") or [""])[0])
        asset = self.store.register(
            claim.run_id,
            dataset_id=dataset_id,
            registry_id=str(registration.get("registry_id") or registration.get("registration_id") or ""),
            revision_id=registration.get("revision_id"),
            manifest_id=str(registration.get("manifest_id") or result.get("manifest_id") or ""),
            vault_path=str(registration.get("vault_path") or registration.get("gdrive_path") or ""),
            archive_verified=bool(
                registration.get("archive_verified", registration.get("drive_verified", result.get("archive_verified")))
            ),
            readiness=str(registration.get("readiness") or "query_ready"),
            title=registration.get("title") or registration.get("name"),
            verification_state=str(registration.get("verification_state") or "not_checked"),
            verification_summary=registration.get("verification_summary"),
            source=registration.get("source"),
            lineage_inputs=registration.get("lineage_inputs") or claim.inputs,
            source_snapshots=registration.get("source_snapshots") or [],
            checksum=registration.get("checksum"),
            method_revision=registration.get("method_revision"),
            refresh_policy=registration.get("refresh_policy"),
            rows=registration.get("rows") or registration.get("row_count") or result.get("rows") or result.get("row_count"),
            fields=registration.get("fields") or registration.get("field_count") or result.get("fields") or result.get("field_count"),
            entities=registration.get("entities") or registration.get("entity_count") or result.get("entities") or result.get("entity_count"),
            grain=registration.get("grain"),
            coverage=registration.get("coverage"),
            at=at,
            expected_attempt=claim.attempt,
        )
        response = {"job": self.store.snapshot(claim.run_id), "asset": asset}
        if connector_state is not None:
            response["connector"] = connector_state
        return response
