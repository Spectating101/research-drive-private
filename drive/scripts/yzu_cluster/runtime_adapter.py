"""Bridge the legacy YZU job queue to the PR #41 runtime contract.

The legacy queue owns ``jobs`` and ``events``.  The reference interoperability
store intentionally uses the same generic names, so this adapter routes its SQL
through a namespaced SQLite connection.  Both systems can then share one durable
database without a destructive migration.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from ._interop_common import Claim, normalize_capabilities
from .interop_contract import InteropStore


_RUNTIME_TABLES = (
    "run_resources",
    "run_usage",
    "reservations",
    "connectors",
    "workers",
    "events",
    "assets",
    "runs",
)
_TABLE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(_RUNTIME_TABLES) + r")(?![A-Za-z0-9_])"
)


class _NamespacedConnection(sqlite3.Connection):
    """Apply a private ``cluster_`` namespace to reference-store SQL."""

    @staticmethod
    def _sql(statement: str) -> str:
        return _TABLE_PATTERN.sub(lambda match: f"cluster_{match.group(1)}", statement)

    def execute(self, sql: str, parameters: Iterable[Any] = (), /):  # type: ignore[override]
        return super().execute(self._sql(sql), parameters)

    def executemany(self, sql: str, parameters, /):  # type: ignore[override]
        return super().executemany(self._sql(sql), parameters)

    def executescript(self, sql_script: str, /):  # type: ignore[override]
        return super().executescript(self._sql(sql_script))


def _canonical_capabilities(values: Iterable[Any]) -> list[str]:
    aliases = {
        "http_collect": "http",
        "datacite_harvest": "http",
        "gdelt_fetch": "http",
        "scraper_host": "browser",
        "puppeteer_scrape": "browser",
        "sqlite_upsert": "pipeline",
        "job_boards": "browser",
        "controller_ui": "controller",
        "cluster_orchestration": "controller",
    }
    normalized = [aliases.get(str(value).strip().lower(), str(value).strip().lower()) for value in values]
    return normalize_capabilities(normalized)


_JOB_CAPABILITIES = {
    "archive_upload": ("archive",),
    "bigquery_query": ("python",),
    "collection_hydrate": ("archive",),
    "collection_queue_batch": ("pipeline", "python"),
    "collection_queue_task": ("pipeline", "python"),
    "harvest_shard": ("http",),
    "http_manifest": ("http",),
    "huggingface_collect": ("http", "python"),
    "registered_pipeline": ("pipeline", "python"),
    "scraper_run": ("browser",),
    "source_probe": ("http",),
    "synthesis_execute": ("python",),
}


def _as_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, Mapping):
        for key in ("dataset_id", "asset_id", "id", "name"):
            if value.get(key) not in (None, ""):
                return [str(value[key])]
        return []
    result: list[str] = []
    for item in value:
        for candidate in _as_ids(item):
            if candidate not in result:
                result.append(candidate)
    return result


def _plan_inputs(plan: Mapping[str, Any]) -> list[str]:
    values: list[Any] = [plan.get("inputs"), plan.get("input_dataset_id"), plan.get("input_dataset_ids")]
    spec = plan.get("execution_spec")
    if isinstance(spec, Mapping):
        values.extend((spec.get("input_dataset_id"), spec.get("input_dataset_ids")))
    return _as_ids(values)


def _plan_outputs(plan: Mapping[str, Any]) -> list[str]:
    values: list[Any] = [plan.get("outputs"), plan.get("dataset_id"), plan.get("output_dataset_id")]
    spec = plan.get("execution_spec")
    if isinstance(spec, Mapping):
        values.append(spec.get("output_dataset_id"))
    return _as_ids(values)


def _controller_capacity(path: Path) -> dict[str, float]:
    """Report only capacities measured from the running controller."""

    capacity: dict[str, float] = {"gpu_count": 0.0}
    if (cpu := os.cpu_count()) is not None:
        capacity["cpu_cores"] = float(cpu)
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        capacity["memory_mb"] = round(float(page_size * page_count) / (1024 * 1024), 2)
    except (AttributeError, OSError, ValueError):
        pass
    try:
        info = os.statvfs(path.parent)
        capacity["disk_mb"] = round(float(info.f_bavail * info.f_frsize) / (1024 * 1024), 2)
    except OSError:
        pass
    return capacity


class ClusterRuntimeAdapter:
    """Expose the durable runtime contract without replacing legacy jobs."""

    def __init__(self, database_path: Path, config: Mapping[str, Any] | None = None) -> None:
        self.database_path = Path(database_path)
        self.config = dict(config or {})
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
            factory=_NamespacedConnection,
        )
        self.store = InteropStore(self.connection)
        self.controller_id = str((self.config.get("controller") or {}).get("hostname") or "optiplex")
        self.register_controller()

    def close(self) -> None:
        self.connection.close()

    def register_controller(self) -> dict[str, Any]:
        capabilities = ["controller", "orchestration", "python", "archive", "pipeline"]
        operations = self.config.get("operations") or {}
        if not operations.get("disable_local_http_collect"):
            capabilities.append("http")
        return self.store.upsert_worker(
            self.controller_id,
            pool="optiplex",
            capabilities=_canonical_capabilities(capabilities),
            capacity=_controller_capacity(self.database_path),
        )

    def join_worker(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or payload.get("id") or "").strip()
        if not worker_id:
            raise ValueError("worker_id is required")
        return self.store.upsert_worker(
            worker_id,
            pool=payload.get("pool") or payload.get("worker_pool"),
            status=str(payload.get("status") or "online"),
            capabilities=_canonical_capabilities(payload.get("capabilities") or []),
            capacity=payload.get("capacity") if isinstance(payload.get("capacity"), Mapping) else {},
            heartbeat_at=payload.get("heartbeat_at"),
        )

    def requirements(self, plan: Mapping[str, Any]) -> list[str]:
        explicit = plan.get("required_capabilities") or plan.get("capabilities") or []
        if explicit:
            return _canonical_capabilities(explicit)
        return _canonical_capabilities(_JOB_CAPABILITIES.get(str(plan.get("job_type") or ""), ("controller",)))

    def ensure(self, job: Mapping[str, Any]) -> dict[str, Any]:
        plan = job.get("plan") if isinstance(job.get("plan"), Mapping) else {}
        status = str(job.get("status") or "pending_approval")
        return self.store.submit(
            job_id=str(job["id"]),
            job_type=str(plan.get("job_type") or "legacy_job"),
            title=str(job.get("title") or plan.get("title") or ""),
            required_capabilities=self.requirements(plan),
            inputs=_plan_inputs(plan),
            outputs=_plan_outputs(plan),
            pending_approval=status == "pending_approval",
            max_attempts=int(plan.get("max_attempts") or 3),
            retryable=plan.get("retryable") is not False,
            resource_requirements=(plan.get("resource_requirements") or plan.get("resources")),
        )

    def _run_id(self, job_id: str) -> str:
        row = self.connection.execute("SELECT run_id FROM runs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return str(row[0])

    def snapshot(self, job_id: str) -> dict[str, Any]:
        return self.store.snapshot(self._run_id(job_id))

    def approve(self, job_id: str) -> dict[str, Any]:
        run_id = self._run_id(job_id)
        current = self.store.snapshot(run_id)
        if current["status"] == "pending_approval":
            return self.store.approve(run_id)
        if current["status"] in {"queued", "assigned", "running"}:
            return current
        raise ValueError(f"runtime job is {current['status']}, not pending_approval")

    def claim_next(self, worker_id: str | None = None, *, lease_seconds: int = 120) -> Claim | None:
        self.store.reap_expired()
        return self.store.claim(worker_id or self.controller_id, lease_seconds=lease_seconds)

    def claim_job(self, job_id: str, worker_id: str | None = None, *, lease_seconds: int = 120) -> Claim | None:
        """Claim one named legacy job without disturbing queue order elsewhere."""

        self.store.reap_expired()
        return self.store.claim(
            worker_id or self.controller_id,
            lease_seconds=lease_seconds,
            job_id=job_id,
        )

    def start(self, claim: Claim) -> dict[str, Any]:
        return self.store.heartbeat(
            claim.run_id,
            claim.worker_id,
            lease_seconds=120,
            next_stage="running",
            expected_attempt=claim.attempt,
        )

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        attempt: int,
        progress: Mapping[str, Any] | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        progress = progress or {}
        return self.store.heartbeat(
            self._run_id(job_id),
            worker_id,
            current=progress.get("current"),
            total=progress.get("total"),
            next_stage=stage,
            expected_attempt=attempt,
        )

    def complete(self, claim: Claim, result: Mapping[str, Any] | None) -> dict[str, Any]:
        result = dict(result or {})
        run_id = claim.run_id
        materialized = result.get("materialized") if isinstance(result.get("materialized"), Mapping) else {}
        drive = result.get("drive_finalize") if isinstance(result.get("drive_finalize"), Mapping) else {}
        outputs = _as_ids(result.get("outputs") or materialized.get("dataset_id") or claim.outputs)
        manifest_id = result.get("output_manifest_id") or result.get("manifest_id") or materialized.get("manifest_id")
        rows = result.get("rows") or materialized.get("rows") or materialized.get("row_count")
        fields = result.get("fields") or materialized.get("fields") or materialized.get("field_count")
        entities = result.get("entities") or materialized.get("entities") or materialized.get("entity_count")

        if drive:
            self.store.record(run_id, "validating", worker_id=claim.worker_id, expected_attempt=claim.attempt)
            self.store.record(
                run_id,
                "archiving",
                worker_id=claim.worker_id,
                archive_verified=bool(drive.get("ok")),
                expected_attempt=claim.attempt,
            )
            if result.get("registry_promotion"):
                self.store.record(run_id, "registering", worker_id=claim.worker_id, expected_attempt=claim.attempt)

        return self.store.record(
            run_id,
            "completed",
            worker_id=claim.worker_id,
            outputs=outputs or None,
            manifest_id=str(manifest_id) if manifest_id else None,
            archive_verified=bool(drive.get("ok")) if drive else None,
            rows=int(rows) if isinstance(rows, (int, float)) else None,
            fields=int(fields) if isinstance(fields, (int, float)) else None,
            entities=int(entities) if isinstance(entities, (int, float)) else None,
            expected_attempt=claim.attempt,
        )

    def fail(self, claim: Claim, error: str, *, retryable: bool = True) -> dict[str, Any]:
        return self.store.record(
            claim.run_id,
            "failed",
            worker_id=claim.worker_id,
            error=error,
            retryable=retryable,
            expected_attempt=claim.attempt,
        )

    def project(self, job: Mapping[str, Any]) -> dict[str, Any]:
        """Add runtime truth without changing legacy fields or status names."""

        projected = dict(job)
        try:
            runtime = self.snapshot(str(job["id"]))
        except KeyError:
            return projected
        projected["runtime"] = runtime
        for key in ("run_id", "attempt", "assigned_worker", "worker_pool", "lease_expires_at", "progress"):
            projected[key] = runtime.get(key)
        return projected
