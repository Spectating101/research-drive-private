"""Reliability policies for distributed YZU job execution.

This mixin keeps retries and repeated API calls safe while preventing stale workers
from receiving work. It deliberately layers over the existing durable store so the
private orchestrator can adopt the behavior without changing frontend contracts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Any, Iterable, Mapping

from ._interop_common import Claim, ids, loads, normalize_capabilities, now_utc, parse_time
from .interop_resources import RESOURCE_KEYS, normalize_requirements

RUNNABLE_WORKER_STATES = {"online", "ready", "idle"}


def _requirements(values: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_requirements(values)
    return {**normalized, "priority": int((values or {}).get("priority") or 50)}


def _same_optional(existing: Any, incoming: Any) -> bool:
    return incoming is None or existing == incoming


class ReliabilityMixin:
    """Fresh-worker claiming, idempotent writes, and priority/FIFO scheduling."""

    def worker(self, worker_id: str, *, at: str | None = None) -> dict[str, Any]:
        worker = super().worker(worker_id)
        stored_status = worker["status"]
        reference = parse_time(at) or datetime.now(timezone.utc)
        heartbeat = parse_time(worker.get("heartbeat_at"))
        age_seconds = max(0.0, (reference - heartbeat).total_seconds()) if heartbeat else None
        threshold = int(getattr(self, "worker_stale_after_seconds", 300))
        stale = (
            stored_status in RUNNABLE_WORKER_STATES
            and (heartbeat is None or (age_seconds is not None and age_seconds > threshold))
        )
        worker["stored_status"] = stored_status
        worker["freshness"] = {
            "state": "stale" if stale else "fresh" if heartbeat else "unknown",
            "age_seconds": age_seconds,
            "stale_after_seconds": threshold,
        }
        if stale:
            worker["status"] = "stale"
        return worker

    def _submission_matches(
        self,
        row: sqlite3.Row,
        *,
        job_type: str,
        title: str | None,
        required_capabilities: Iterable[str],
        inputs: Iterable[Any],
        outputs: Iterable[Any],
        max_attempts: int,
        retryable: bool,
        resource_requirements: Mapping[str, Any] | None,
    ) -> bool:
        return all((
            row["job_type"] == job_type,
            (row["title"] or None) == (title or None),
            int(row["max_attempts"]) == int(max_attempts),
            bool(row["retryable"]) == bool(retryable),
            loads(row["required_capabilities"], []) == normalize_capabilities(required_capabilities),
            loads(row["inputs"], []) == ids(inputs),
            loads(row["outputs"], []) == ids(outputs),
            self.requirements(row["run_id"]) == _requirements(resource_requirements),
        ))

    def submit(
        self,
        *,
        job_id: str,
        job_type: str,
        title: str | None = None,
        required_capabilities: Iterable[str] = (),
        inputs: Iterable[Any] = (),
        outputs: Iterable[Any] = (),
        pending_approval: bool = False,
        max_attempts: int = 3,
        retryable: bool = True,
        resource_requirements: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.db.execute("SELECT * FROM runs WHERE job_id=?", (job_id,)).fetchone()
        if existing is not None:
            if self._submission_matches(
                existing,
                job_type=job_type,
                title=title,
                required_capabilities=required_capabilities,
                inputs=inputs,
                outputs=outputs,
                max_attempts=max_attempts,
                retryable=retryable,
                resource_requirements=resource_requirements,
            ):
                return self.snapshot(existing["run_id"])
            raise ValueError("job_id already exists with a different request")

        try:
            return super().submit(
                job_id=job_id,
                job_type=job_type,
                title=title,
                required_capabilities=required_capabilities,
                inputs=inputs,
                outputs=outputs,
                pending_approval=pending_approval,
                max_attempts=max_attempts,
                retryable=retryable,
                resource_requirements=resource_requirements,
                run_id=run_id,
            )
        except sqlite3.IntegrityError:
            existing = self.db.execute("SELECT * FROM runs WHERE job_id=?", (job_id,)).fetchone()
            if existing is not None and self._submission_matches(
                existing,
                job_type=job_type,
                title=title,
                required_capabilities=required_capabilities,
                inputs=inputs,
                outputs=outputs,
                max_attempts=max_attempts,
                retryable=retryable,
                resource_requirements=resource_requirements,
            ):
                return self.snapshot(existing["run_id"])
            raise ValueError("job_id already exists with a different request") from None

    def claim(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 120,
        at: str | None = None,
        job_id: str | None = None,
        allowed_job_types: Iterable[str] | None = None,
        deny_job_id_prefixes: Iterable[str] | None = None,
    ) -> Claim | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        at = at or now_utc()
        worker = self.worker(worker_id, at=at)
        if worker["status"] not in RUNNABLE_WORKER_STATES:
            return None
        available = set(normalize_capabilities(worker["capabilities"]))
        allowed_types = {str(item).strip() for item in (allowed_job_types or ()) if str(item).strip()}
        deny_prefixes = tuple(str(item) for item in (deny_job_id_prefixes or ()) if str(item))
        expiry = (
            (parse_time(at) or datetime.now(timezone.utc)) + timedelta(seconds=lease_seconds)
        ).isoformat().replace("+00:00", "Z")

        def _claimable(row: Any) -> bool:
            if allowed_types and str(row["job_type"] or "") not in allowed_types:
                return False
            job_key = str(row["job_id"] or "")
            if any(job_key.startswith(prefix) for prefix in deny_prefixes):
                return False
            return set(loads(row["required_capabilities"], [])).issubset(available) and self._resource_fit(
                row["run_id"], worker_id
            )

        with self.transaction():
            query = """SELECT runs.*,COALESCE(run_resources.priority,50) scheduling_priority
                FROM runs LEFT JOIN run_resources USING(run_id)
                WHERE runs.stage IN('queued','retrying') AND runs.attempt<runs.max_attempts"""
            params: tuple[Any, ...] = ()
            if job_id:
                query += " AND runs.job_id=?"
                params = (job_id,)
            query += " ORDER BY scheduling_priority DESC,runs.created_at,runs.run_id"
            rows = self.db.execute(query, params).fetchall()
            selected = next((row for row in rows if _claimable(row)), None)
            if selected is None:
                return None
            attempt = int(selected["attempt"]) + 1
            self._reserve_resources(selected["run_id"], worker_id, at=at)
            self.db.execute(
                "UPDATE runs SET stage='assigned',attempt=?,worker_id=?,pool=?,lease_expires_at=?,error=NULL,updated_at=? WHERE run_id=?",
                (attempt, worker_id, worker["pool"], expiry, at, selected["run_id"]),
            )
            self._event(
                selected["run_id"], "assigned", "assigned", at=at,
                worker_id=worker_id, attempt=attempt,
                payload={"lease_expires_at": expiry, "priority": int(selected["scheduling_priority"])},
            )

        row = self._row(selected["run_id"])
        requirements = self.requirements(row["run_id"])
        return Claim(
            row["run_id"], row["job_id"], row["job_type"], attempt, worker_id,
            tuple(loads(row["required_capabilities"], [])),
            tuple(loads(row["inputs"], [])),
            tuple(loads(row["outputs"], [])),
            tuple(sorted((key, float(requirements[key])) for key in RESOURCE_KEYS)),
            expiry,
        )

    def _registration_matches(
        self,
        existing: Mapping[str, Any],
        *,
        registry_id: str,
        revision_id: str | None,
        manifest_id: str,
        vault_path: str,
        readiness: str,
        checksum: str | None,
        method_revision: str | None,
        lineage_inputs: Iterable[Any] | None,
        source_snapshots: Iterable[Any],
        rows: int | None,
        fields: int | None,
        entities: int | None,
        grain: str | None,
        coverage: str | None,
    ) -> bool:
        snapshots = list(source_snapshots)
        return all((
            existing["registry_id"] == registry_id,
            existing["manifest_id"] == manifest_id,
            existing["vault_path"] == vault_path,
            existing["analysis_readiness"] == readiness,
            existing["drive_verified"] is True,
            _same_optional(existing.get("revision_id"), revision_id),
            _same_optional(existing.get("checksum"), checksum),
            _same_optional(existing.get("method_revision"), method_revision),
            lineage_inputs is None or existing["lineage"]["inputs"] == ids(lineage_inputs),
            not snapshots or existing["lineage"]["source_snapshots"] == ids(snapshots),
            _same_optional(existing.get("row_count"), rows),
            _same_optional(existing.get("field_count"), fields),
            _same_optional(existing.get("entity_count"), entities),
            _same_optional(existing.get("grain"), grain),
            _same_optional(existing.get("coverage"), coverage),
        ))

    def register(
        self,
        run_id: str,
        *,
        dataset_id: str,
        registry_id: str,
        manifest_id: str,
        vault_path: str,
        archive_verified: bool,
        revision_id: str | None = None,
        readiness: str = "query_ready",
        title: str | None = None,
        verification_state: str = "not_checked",
        verification_summary: str | None = None,
        source: Mapping[str, Any] | str | None = None,
        lineage_inputs: Iterable[Any] | None = None,
        source_snapshots: Iterable[Any] = (),
        checksum: str | None = None,
        method_revision: str | None = None,
        refresh_policy: str | None = None,
        last_refreshed_at: str | None = None,
        next_refresh_at: str | None = None,
        rows: int | None = None,
        fields: int | None = None,
        entities: int | None = None,
        grain: str | None = None,
        coverage: str | None = None,
        at: str | None = None,
    ) -> dict[str, Any]:
        if not all((dataset_id, registry_id, manifest_id, vault_path)):
            raise ValueError("dataset_id, registry_id, manifest_id, and vault_path are required")
        if not archive_verified:
            raise ValueError("registered assets require verified archive proof")
        ready = readiness.strip().lower().replace("-", "_")
        if ready not in {"registered", "query_ready"}:
            raise ValueError("invalid readiness")

        run = self._row(run_id)
        declared = loads(run["outputs"], [])
        if declared and dataset_id not in declared:
            raise ValueError("registered dataset_id must match a declared run output")

        existing_row = self.db.execute("SELECT dataset_id FROM assets WHERE dataset_id=?", (dataset_id,)).fetchone()
        existing = self.asset(dataset_id) if existing_row is not None else None
        snapshots = list(source_snapshots)
        if existing is not None:
            matches = self._registration_matches(
                existing,
                registry_id=registry_id,
                revision_id=revision_id,
                manifest_id=manifest_id,
                vault_path=vault_path,
                readiness=ready,
                checksum=checksum,
                method_revision=method_revision,
                lineage_inputs=lineage_inputs,
                source_snapshots=snapshots,
                rows=rows,
                fields=fields,
                entities=entities,
                grain=grain,
                coverage=coverage,
            )
            # A scheduled refresh is a new, explicitly identified revision of
            # the same logical asset. Preserve strict replay fencing for
            # unversioned or same-revision writes, while allowing the new
            # verified snapshot to replace the current asset pointer.
            new_revision = bool(revision_id) and str(existing.get("revision_id") or "") != str(revision_id)
            if not matches and not new_revision:
                raise ValueError("dataset_id already exists with conflicting registration proof")
            if matches and run["stage"] == "registered":
                return existing

        if run["stage"] not in {"completed", "registering", "registered"}:
            raise ValueError("run must complete execution before registration")

        return super().register(
            run_id,
            dataset_id=dataset_id,
            registry_id=registry_id,
            manifest_id=manifest_id,
            vault_path=vault_path,
            archive_verified=archive_verified,
            revision_id=revision_id,
            readiness=ready,
            title=title,
            verification_state=verification_state,
            verification_summary=verification_summary,
            source=source,
            lineage_inputs=lineage_inputs,
            source_snapshots=snapshots,
            checksum=checksum,
            method_revision=method_revision,
            refresh_policy=refresh_policy,
            last_refreshed_at=last_refreshed_at,
            next_refresh_at=next_refresh_at,
            rows=rows,
            fields=fields,
            entities=entities,
            grain=grain,
            coverage=coverage,
            at=at,
        )
