from __future__ import annotations

import json
from pathlib import Path

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.worker_control import WorkerControlPlane


def _orchestrator(tmp_path: Path, schedule: dict) -> YzuOrchestrator:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest", "collection_queue_batch"]},
                "worker_pools": {},
                "storage": {},
                "schedules": [schedule],
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def _windows_control(orchestrator: YzuOrchestrator) -> WorkerControlPlane:
    control = WorkerControlPlane(orchestrator, token="secret-token")
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    return control


def test_scheduled_http_procurement_is_claimable_by_windows_worker(tmp_path: Path) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        {
            "id": "sec_daily",
            "enabled": True,
            "interval_hours": 24,
            "auto_approve": True,
            "plan": {
                "title": "Daily SEC ticker refresh",
                "job_type": "http_manifest",
                "dataset_id": "sec_company_tickers_snapshot",
                "connector_id": "sec_edgar",
                "url": "https://www.sec.gov/files/company_tickers.json",
            },
        },
    )

    emitted = orchestrator.scheduler_tick()
    assert emitted is not None
    assert emitted["job"]["status"] == "queued"
    assert emitted["job"]["runtime"]["status"] == "queued"

    claim = _windows_control(orchestrator).claim({"worker_id": "windows-01"})
    assert claim is not None
    assert claim["plan"]["job_type"] == "http_manifest"
    assert claim["plan"]["dataset_id"] == "sec_company_tickers_snapshot"


def test_batch_schedule_stays_queued_for_http_only_windows_worker(tmp_path: Path) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        {
            "id": "legacy_batch",
            "enabled": True,
            "interval_hours": 24,
            "auto_approve": True,
            "plan": {
                "title": "Legacy collection queue",
                "job_type": "collection_queue_batch",
            },
        },
    )

    emitted = orchestrator.scheduler_tick()
    assert emitted is not None
    claim = _windows_control(orchestrator).claim({"worker_id": "windows-01"})
    assert claim is None
    assert orchestrator.runtime.snapshot(emitted["job"]["id"])["status"] == "queued"
