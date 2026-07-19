from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.yzu_cluster.jobs import YzuJobStore
from scripts.yzu_cluster.runtime_adapter import ClusterRuntimeAdapter


def _legacy_job(store: YzuJobStore, job_id: str = "collect-usdt") -> dict:
    return store.create(
        "Collect USDT history",
        {},
        {
            "job_type": "http_manifest",
            "inputs": ["usdt_contracts"],
            "dataset_id": "raw_usdt_history",
        },
        status="queued",
        job_id=job_id,
    )


def test_runtime_tables_do_not_replace_legacy_events(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    job = _legacy_job(legacy)
    legacy.event(job["id"], "info", "legacy event")

    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    snapshot = runtime.ensure(job)

    with sqlite3.connect(database) as db:
        legacy_columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        runtime_columns = {row[1] for row in db.execute("PRAGMA table_info(cluster_events)")}

    assert {"job_id", "level", "message"}.issubset(legacy_columns)
    assert {"run_id", "stage", "event_type", "attempt"}.issubset(runtime_columns)
    assert snapshot["id"] == job["id"]
    assert legacy.get(job["id"])["events"][-1]["message"] == "legacy event"


def test_runtime_claims_only_fresh_capable_workers_and_fences_attempts(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = _legacy_job(legacy)
    runtime.ensure(job)

    claim = runtime.claim_next()
    assert claim is not None
    runtime.start(claim)
    runtime.complete(claim, {"outputs": ["raw_usdt_history"]})
    assert runtime.snapshot(job["id"])["status"] == "completed"

    with pytest.raises(PermissionError, match="stale execution attempt"):
        runtime.heartbeat(job["id"], claim.worker_id, attempt=claim.attempt + 1)


def test_runtime_requires_a_real_capability_for_browser_work(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = legacy.create(
        "Collect source through browser",
        {},
        {"job_type": "scraper_run", "url": "https://example.test"},
        status="queued",
        job_id="browser-collect",
    )
    runtime.ensure(job)

    assert runtime.claim_next() is None
    assert runtime.snapshot(job["id"])["status"] == "queued"
