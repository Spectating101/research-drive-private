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
        )
        registration = result.get("registration")
        if not isinstance(registration, Mapping):
            return completed

        dataset_id = str(registration.get("dataset_id") or (completed.get("outputs") or [""])[0])
        asset = self.store.register(
            claim.run_id,
            dataset_id=dataset_id,
            registry_id=str(registration.get("registry_id") or registration.get("registration_id") or ""),
            revision_id=registration.get("revision_id"),
            manifest_id=str(registration.get("manifest_id") or result.get("manifest_id") or ""),
            vault_path=str(registration.get("vault_path") or registration.get("gdrive_path") or ""),
            archive_verified=bool(registration.get("archive_verified", registration.get("drive_verified", result.get("archive_verified")))),
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
        )
        return {"job": self.store.snapshot(claim.run_id), "asset": asset}
